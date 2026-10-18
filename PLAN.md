# Anonymization plan — PPIA Homework 1

Objectives and implementation hints for the rest of the project.
Starting point: `review-Vermont-anon-v1.json` (841,978 reviews, produced by
`anonymize_v1.py`). All field and variable names are in English.

---

## 0. Overview

Features are listed in the order they were implemented. "Step" = one script
producing one new JSON version.

| Step | Feature | Script / output | Status |
|------|---------|-----------------|--------|
| 0 | Anonymous baseline: drop direct identifiers, derived fields, spending model | `anonymize_v1.py` → v1 | Done |
| 1 | Drop the time of day, keep the month | `anonymize_v2.py` → v2 | Done |
| 2 | Lengths → 3 categories (short / medium / long) | `anonymize_v3.py` → v3 | Done |
| 3 | `spent`: outlier clipping (5 % rule) + tier rounding + rarity merging | `anonymize_v4.py` → v4 | Done |
| 4 | Data-loss tests, alarm thresholds, `results.csv` | `utility_tests.py` | Done |
| 5 | k-anonymity: replace `gmap_id` by its categories (recoding ladder) | `kanonymity.py` → v5 | Done |
| 6 | Logarithmic scale for the prices | option of a future step | **To do** |
| 7 | Try several options and discuss them in the study | uses `utility_tests.py` | **To do** |

---

## Conventions to follow in every script

1. **Mandatory counting**: each script prints the number of rows read,
   written and **removed** (and the reason: outliers, groups < k, etc.).
   Example output:
   `{'read': 841978, 'written': 841978, 'removed': 0}`.
   No removal may ever be silent.
2. **One JSON per big step**: for every major modification we write a new
   file instead of overwriting the previous one, so data is never lost and
   we can always go back. Each version must be reproducible from the
   previous one by a dedicated script.
3. **Small functions called from `main()`**: keep the code as readable as
   possible (see `anonymize_v2.py` / `anonymize_v3.py` / `anonymize_v4.py`).

---

# PART A — Implemented (in implementation order)

## Step 0 — `anonymize_v1.py`: anonymous baseline → v1

Reads the raw Google reviews (and the place metadata) and produces the first
anonymous dataset:

- `user_id` and `name` are removed (direct identifiers);
- the Unix timestamp becomes `date` (YYYY-MM-DD) and `time` (HH:MM) in
  Vermont local time;
- the review text is replaced by `comment_length`, the pictures by `pics_num`;
- the owner response is replaced by `has_resp`, `resp_length`,
  `resp_delay_hours`;
- `gmap_id`, `rating` and `category` are kept;
- `spent` is drawn from a realistic log-normal spending model based on the
  place categories (`SPEND_PROFILES` in the script);
- exact duplicate reviews (same user, place and time) are written once.

## Step 1 — `anonymize_v2.py`: coarser time → v2

- drops the `time` field (HH:MM);
- generalizes `date` from YYYY-MM-DD to **YYYY-MM** (month precision).

**Why**: the exact hour and day are quasi-identifiers that are too fine.
Month precision strongly reduces the re-identification risk while keeping
temporal analysis possible (seasonality, trends).

**Possible refinement for step 7**: if the month is still too fine, consider
the quarter (`YYYY-Qn`) or the year.

## Step 2 — `anonymize_v3.py`: lengths in 3 categories → v3

Replaces the exact character counts by ordered categories, because a length
like 472 characters is close to unique. Three classes, the middle one being
the "relevant" comments (bounds measured on v2):

| Category | Bound | Justification (measured) |
|----------|-------|---------------------------|
| `short` | < 50 chars | carries little information; 60.25 % of reviews (many are 0 = no text) and 26 % of responses |
| `medium` | 50–500 | the useful core of the distribution (p50 = 26, p75 = 107, p90 = 266) |
| `long` | > 500 | verbose outliers; only 3.51 % of reviews and 2.7 % of responses |

**Why 500**: p95 = 414 and p99 = 887 for reviews, p95 = 390 for responses —
500 captures the tail without cutting into the body. **Alternative for
step 7: 750**, which shrinks the `long` class to 1.5 % of reviews.

**Variant kept for step 7**: a scale in steps of 50
(`comment_length // 50`). Caveat: each bin beyond 400 chars holds < 1 % of
the reviews, so individually they violate the 5 % rule — the argument for
folding everything above into a single `long` class.

Note: among the `short` reviews, the ones with no text at all
(`comment_length = 0`, ~25 % of the total) are a separate case; option to
discuss — splitting them into a fourth `none` class makes the field more
honest but slightly less anonymous.

## Step 3 — `anonymize_v4.py`: prices → v4

`spent = 1987.31` with two decimals is a near-unique identifier. Three
passes, in this order (outliers would break the rounding):

1. **Outlier clipping (5 % rule)**: values are clamped to the [q05, q95]
   range of their spend profile ($200 is common at a restaurant but rare at
   a gas station; the car-dealer profile alone reaches q95 = $37,289,
   max = $133,916). Measured: 38,798 rows clipped low, 38,745 high
   (~4.6 % each).
2. **Rounding**: to the nearest tier of a growing ladder
   `[0, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000]`; anything
   above the last tier is clamped to it (e.g. 1987.31 → 2000,
   22000 → 10000).
3. **Rarity check (5 % rule)**: tiers holding fewer than 5 % of the rows are
   merged into their nearest surviving neighbour, rarest first. Measured:
   65,078 rows (7.7 %) landed in a merged tier; final ladder
   **0 / 10 / 25 / 50 / 100 / 250 / 500**, every tier between 7.3 % and
   21.5 % of the rows.

**Alternative kept for step 7**: **ordered bands** instead of rounding —
`0–10`, `10–50`, `50–200`, `200+`… More anonymous, less precise.

## Step 4 — `utility_tests.py`: data-loss tests → `results.csv`

Compares a baseline version (default v1) with the current version (default
v4), row for row, and reports the utility cost of the pipeline:

| Metric | Meaning |
|--------|---------|
| Rate of removed rows | if the strategy is suppression |
| % of rows in a QI group ≥ k | health of the k-anonymity (k = 3, 5, 10) |
| Error on `spent` | exact matches, median relative, mean absolute, median log10 |
| Date generalization | 3,939 distinct days → 177 distinct months |
| Rating preservation | total variation distance (0 = identical) |
| Lengths per category | count and median original length per category |

Alarm thresholds (CLI-configurable): **REJECT** above 10 % removed rows or
20 % median relative error on `spent`; **WARN** at half those levels;
otherwise OK. Every run is appended to `results.csv` (one row per tested
variant) — the table that feeds the study discussion.

### Measured results (baseline = v1, QI = `date,gmap_id,rating,spent`)

| Metric | v2 | v3 | v4 |
|--------|----|----|----|
| removed rows | 0 % | 0 % | 0 % |
| spent median relative error | 0 % | 0 % | **19.20 %** |
| spent exact values | 100 % | 100 % | 7.81 % |
| spent median log10 error | 0 | 0 | 0.0816 |
| rating total variation distance | 0 | 0 | 0 |
| rows in a QI group ≥ 3 | 4.15 % | 4.15 % | 37.45 % |
| rows in a QI group ≥ 5 | 3.08 % | 3.08 % | 20.66 % |
| rows in a QI group ≥ 10 | 1.90 % | 1.90 % | 8.08 % |
| Verdict (10 % / 20 % alarms) | OK | OK | **WARN** |

Reading of these numbers for the study:

- the k-health barely moves between v2 and v3 (lengths were never in the QI
  key) and jumps at v4: discretizing `spent` alone multiplies by ~9 the
  share of rows living in a group ≥ 3;
- v4 gets a WARN because the median relative error on `spent` (19.20 %)
  sits just under the 20 % alarm but above the 10 % warning level. On a
  log10 scale the same error is only 0.082 — the concrete argument for the
  logarithmic tiers of the next part;
- `rating` and the row count are preserved exactly (sanity checks pass);
- with the full QI key, 72 % of groups are still singletons at v4 — the
  k-anonymity work of the next part must now focus on `gmap_id`/`category`.

## Step 5 — `kanonymity.py`: k-anonymity on the place dimension → v5

**Idea (team decision)**: the exact place is the most identifying
quasi-identifier (72 % of full-QI groups were singletons at v4), so
`gmap_id` is replaced by the CATEGORIES of the corresponding gmap_id. Two
places with the same published categories become indistinguishable.

**Recoding ladder** — every published place group must hold at least k
reviews (default k = 5):

- level 0: the full sorted category list of the gmap_id (places with the
  same categories merge);
- level 1: the first (primary) category only, counted among the places that
  did not pass level 0;
- level 2: suppressed (`category` → null) — the place information is dropped
  but the review itself is kept.

### Measured results (k = 5)

| Metric | Value |
|--------|-------|
| rows kept at level 0 (full categories) | 840,681 (99.85 %) |
| rows at level 1 (first category) | 266 |
| rows at level 2 (place suppressed) | 1,031 (incl. the 192 null-category rows) |
| place groups published | 3,807, smallest = 5 rows = k |
| rows in a full-QI group ≥ 5 (date, category, rating, spent) | **48.04 %** (was 20.66 % at v4 with gmap_id) |
| rows in a full-QI group ≥ 3 / ≥ 10 | 62.47 % / 31.48 % |
| Verdict (`utility_tests.py --label v5`) | WARN (same spent error as v4) |

No rows are removed; the group below-k check found none.

**What this step does NOT do yet**: full-QI k-anonymity. 62.87 % of
(date, category, rating, spent) groups are still singletons — mostly
because a (month, rating, spent) combination can still be unique for one
category group. Pushing k further means generalizing `date` (month →
quarter → year) and `rating` (exact → {1–2, 3, 4–5}) — those axes are
part of the step 7 variant grid.

---

# PART B — To do

## Step 6 — Logarithmic scale for the prices

**Why**: spending is log-normal (the v1 model already draws
`median * exp(N(0, spread))`). On a linear scale everything small is
squeezed near 0 and the large amounts stretch the axis. On a log scale,
every **order of magnitude** carries the same weight. The step-4 tests
already showed it: a 19.20 % linear error is only 0.082 in log10.

### Implementation hints

1. **Logarithmic tiers**: round to the nearest power of ten —
   `spent → 10^round(log10(spent))` gives 1, 10, 100, 1000, 10000 $.
   Finer: steps of `±0.5` in log10 → 1, 3, 10, 30, 100, 300…
2. **Derived variable**: add `log_spent = round(log10(spent), 1)` as a
   numeric QI — 0.1 in log10 ≈ a factor 1.26, a natural generalization.
3. **Visualization**: every `spent` histogram in the study should use a
   logarithmic x-axis (matplotlib: `ax.set_xscale('log')`), otherwise the
   plots are unreadable.
4. **Consistency with step 3**: log tiers (1, 3, 10, 30…) replace the
   linear tiers advantageously for large amounts; keep fine tiers (1, 5, 10)
   below $20 where the data is dense.

## Step 7 — Try several options and discuss them in the study

Grid of variants to compare (each cell = one run, judged by
`utility_tests.py`, logged in `results.csv`):

| Axis | Options |
|------|---------|
| Date precision | month / quarter / year |
| k | 3 / 5 / 10 |
| Retained QIs | with or without `rating`, with or without `category` |
| `spent` | exact / rounded / linear tiers / log tiers |
| Length categories | 500 vs 750 for the `long` bound; steps of 50; a `none` class for 0 |
| Outliers | with / without the 5 % rule |
| Strategy for groups < k | suppression / generalization |

**Implementation hint**: write the variants as configuration functions
(one parameter dict per variant), not copied code. Run in a loop, collect
the step-4 metrics, then discuss: utility ↔ k curves, cost of each axis,
final recommendation.

---

## Target pipeline

```
raw_data (review-Vermont.json + meta-Vermont.json)
        |  anonymize_v1.py   step 0 (done)
        v
review-Vermont-anon-v1.json
        |  anonymize_v2.py   step 1 (done): time dropped, date -> month
        v
review-Vermont-anon-v2.json
        |  anonymize_v3.py   step 2 (done): lengths -> 3 categories
        v
review-Vermont-anon-v3.json
        |  anonymize_v4.py   step 3 (done): outlier clipping, tier rounding
        v
review-Vermont-anon-v4.json
        |  kanonymity.py     step 5 (done): gmap_id -> recoded categories
        v
review-Vermont-anon-v5.json       <- current version
        |  steps 6-7 (to do): log tiers, variant grid, discussion
        v
results.csv
```

## Points to discuss in the study

- Data loss vs value of k: where do we put the cursor?
- Can `gmap_id` be kept, or must we switch to categories?
- Top-coding as "category" vs "clipping": false values or information loss?
- Linear vs logarithmic tiers for `spent`: effect on analytical utility
  (19.20 % linear error vs 0.082 log10 error at v4).
- Limit of k-anonymity itself: vulnerable to similarity attacks
  (l-diversity, t-closeness) — mention at least.
