# Vermont Google Reviews — Anonymization Pipeline (PPIA Homework 1)

This project anonymizes ~842k Google reviews of places in Vermont (USA)
before any analysis, following the k-anonymity approach described in
[PLAN.md](PLAN.md).

## Objective

The raw reviews contain direct identifiers (user id, name, free text) and
fine-grained quasi-identifiers (exact timestamp, precise amounts). The goal
is to publish a dataset where:

- no direct identifier survives;
- every combination of quasi-identifiers is shared by enough records to
  resist re-identification (k-anonymity, 5 % rarity rule);
- the data remains useful for analysis (ratings, spending, temporal trends).

## Pipeline

Each step is one script that reads the previous JSON-lines file and writes
the next one — nothing is overwritten, so we can always go back. Every
script prints its counters (rows read / written / removed); no data is ever
silently dropped.

```
raw_data/review-Vermont.json + meta-Vermont.json
        |  anonymize_v1.py
        v
review-Vermont-anon-v1.json    (841,978 reviews)
        |  anonymize_v2.py
        v
review-Vermont-anon-v2.json
        |  anonymize_v3.py
        v
review-Vermont-anon-v3.json
        |  anonymize_v4.py
        v
review-Vermont-anon-v4.json        <- current version
        |
        |  kanonymity.py
        v
review-Vermont-anon-v5.json
        |  anonymize_v6.py
        v
review-Vermont-anon-v6.json        <- current version
```

## The versions

### v1 — `anonymize_v1.py`: raw → anonymous baseline

Reads the raw Google reviews (and the metadata of the places) and produces
the first anonymous dataset. For each review:

- `user_id` and `name` are removed (direct identifiers);
- the Unix timestamp becomes `date` (YYYY-MM-DD) and `time` (HH:MM) in
  Vermont local time;
- the review text is replaced by `comment_length` (character count);
- the pictures are replaced by `pics_num` (count);
- the owner response is replaced by `has_resp`, `resp_length`,
  `resp_delay_hours`;
- `gmap_id`, `rating` and `category` are kept;
- `spent` is drawn from a realistic log-normal spending model based on the
  place categories (see `SPEND_PROFILES` in the script);
- exact duplicate reviews (same user, place and time) are written once.

### v2 — `anonymize_v2.py`: coarser time

- drops the `time` field (HH:MM);
- generalizes `date` from YYYY-MM-DD to **YYYY-MM** (month precision).

### v3 — `anonymize_v3.py`: lengths in 3 categories

Replaces the exact character counts by ordered categories, because a length
like 472 characters is close to unique:

- `comment_length` → `comment_length_cat`: `short` (< 50), `medium`
  (50–500), `long` (> 500);
- `resp_length` → `resp_length_cat`: same bounds, `null` stays `null`.

### v4 — `anonymize_v4.py`: prices clipped, rounded, rarity-checked

`spent = 1987.31` with two decimals is a near-unique identifier. In order:

1. **Outlier clipping (5 % rule)**: values are clamped to the [q05, q95]
   range of their spend profile ($200 is common at a restaurant but rare at
   a gas station).
2. **Rounding**: to the nearest tier of a growing ladder
   (0, 10, 25, 50, 100, 250, 500...).
3. **Rarity check**: tiers holding less than 5 % of the rows are merged
   into their nearest surviving neighbour. Final ladder:
   **0 / 10 / 25 / 50 / 100 / 250 / 500**, every tier between 7.3 % and
   21.5 % of the rows.

### v5 — `kanonymity.py`: k-anonymity on the place dimension

The exact place (`gmap_id`) is the most identifying quasi-identifier, so
it is replaced by the **categories of the corresponding gmap_id**: two
places with the same published categories are indistinguishable. A
recoding ladder guarantees that every published place group holds at
least k reviews (default k = 5):

- level 0: the full sorted category list (99.85 % of reviews);
- level 1: the first (primary) category only;
- level 2: suppressed (`category` → null), the review is kept.

No rows are removed; the smallest published place group holds exactly k
reviews.

### v6 — `anonymize_v6.py`: drop the constant `state` column

The `state` field was `"Vermont"` in every row: zero information, zero
identifying power — pure schema noise. It is removed; this dataset being
Vermont-only is documented here instead. All metrics are identical to v5
(a constant column can always be dropped for free).

### `utility_tests.py`: data-loss tests

Compares a baseline version (default v1) with the current version
(default v4) and reports the utility cost of the pipeline: removed rows,
error on `spent` (relative and log10), rating distribution preservation
(total variation distance), date generalization, and k-anonymity health
(share of rows in a QI group of size ≥ k). The variant gets a verdict —
OK / WARN / REJECT — from the alarm thresholds (default: reject above
10 % removed rows or 20 % median error on spent). Every run is appended
to `results.csv`, one row per tested variant. See [RESULTS.md](RESULTS.md)
for how to read that file.

## Output fields (current version, v6)

| Field | Description |
|-------|-------------|
| `date` | review month, YYYY-MM |
| `rating` | 1–5 stars, may be null |
| `comment_length_cat` | `short` / `medium` / `long` |
| `pics_num` | number of pictures |
| `has_resp` | does the place owner have a response |
| `resp_length_cat` | `short` / `medium` / `long` / `null` |
| `resp_delay_hours` | hours between review and response, or `null` |
| `category` | recoded categories of the place (full list, first category, or `null`) — `gmap_id` is gone |
| `spent` | amount spent in USD, tier value |

Note: this dataset covers Vermont (USA) places only — the former constant
`state` column was dropped in v6.

## How to run

```bash
python anonymize_v2.py            # v1 -> v2
python anonymize_v3.py            # v2 -> v3
python anonymize_v4.py            # v3 -> v4
python kanonymity.py              # v4 -> v5 (optional: --k 5)
python anonymize_v6.py            # v5 -> v6
python utility_tests.py --label v6 --current review-Vermont-anon-v6.json \
       --qi date,category,rating,spent     # data-loss report + results.csv
```

Each script accepts `--in FILE` and `--out FILE` to override the default
paths; `anonymize_v4.py` also accepts `--merge-min` (rarity threshold,
default 0.05 = the 5 % rule).

The scripts need Python 3.9+ and no external dependency. `anonymize_v1.py`
optionally uses `tzdata` on Windows for time-zone conversions.
