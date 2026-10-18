# How to read `results.csv`

`results.csv` is the comparison table of the anonymization pipeline. It is
produced by `utility_tests.py`: every run adds **one row per tested
variant**. Each row reports how much information one version of the
dataset (`n_current`) lost compared to the **baseline v1** (841,978
reviews), row by row — the versions keep the same reviews in the same
order, so every metric below is computed on matched pairs.

Current content:

| label | QI key used for the k-health columns | verdict |
|-------|---------------------------------------|---------|
| v2 | `date, gmap_id, rating, spent` | OK |
| v3 | `date, gmap_id, rating, spent` | OK |
| v4 | `date, gmap_id, rating, spent` | WARN |
| v5 | `date, category, rating, spent` | WARN |

The columns fall into three blocks: data integrity, `spent` precision, and
k-anonymity health.

---

## Block 1 — Data integrity: "did I lose rows or break a field?"

| Column | How to read it |
|--------|----------------|
| `n_baseline`, `n_current` | Row counts of both versions. If they differ, the variant removed rows. |
| `paired` | `True` = the two files match row for row, so all paired metrics are meaningful. `False` = row counts differ; treat the `spent` error columns as unavailable. |
| `removed_pct` | Share of baseline reviews missing from the current version. The pipeline never removes rows: every version shows 0.0. |
| `rating_tvd` | Total variation distance between the `rating` distributions of the two versions (0 = strictly identical). This is a **sanity check**: the pipeline never touches `rating`, so anything but 0.0 means a bug. |
| `days_baseline` → `months_current` | Date generalization: 3,939 distinct days in v1 became 177 distinct months from v2 on. The drop itself is the intended information loss (step 1). |

## Block 2 — `spent` precision: "what did anonymizing the prices cost?"

These columns only change when the price treatment changes (v4 introduced
outlier clipping + tier rounding).

| Column | How to read it |
|--------|----------------|
| `spent_exact_pct` | Share of reviews whose amount is **exactly** the baseline value. 100.0 until v3 (prices untouched), 7.81 from v4 on (almost every amount was clipped or rounded). |
| `spent_median_rel_err_pct` | **The alarm metric**: median relative error on the amount. 19.2 from v4 on — under the 20 % alarm, but above the 10 % warning level, hence the WARN verdicts. |
| `spent_mean_abs_err` | Mean absolute error in dollars ($367.12) — the figure to quote as "on average we are off by X dollars". |
| `spent_median_log10_err` | The same median error on a log10 scale (0.08). Read it multiplicatively: the median amount is known within a factor 10^0.08 ≈ 1.2, i.e. ±20 %. This is the concrete argument for the logarithmic tiers (PLAN.md, step 7). |

## Block 3 — k-anonymity health: "how distinguishable is one review?"

Computed on the current version only, over the quasi-identifier combination
given in the `qi` column. For every row: a review "lives" in the group of
all reviews sharing its QI values — the attacker's view.

| Column | How to read it |
|--------|----------------|
| `qi` | The QI fields used for this row's k-columns. **Read it before comparing rows** — v2–v4 use `gmap_id` while v5 uses `category` (v5 no longer contains `gmap_id`). k-columns are only directly comparable between rows with the same `qi`. |
| `groups` | Number of distinct QI combinations. |
| `singleton_groups_pct` | Share of groups containing a single review. **Lower is better**: an attacker knowing those QI values identifies the review with certainty. |
| `rows_ge_k3_pct`, `rows_ge_k5_pct`, `rows_ge_k10_pct` | Share of reviews living in a group of at least k reviews (k = 3, 5, 10). **Higher is better** — this is the actual privacy metric. |

---

## The verdict

`verdict` applies the alarm thresholds of PLAN.md (objective 4), all
CLI-configurable (`--removed-alarm`, `--error-alarm`):

- **REJECT** — more than 10 % of rows removed, or the median relative
  error on `spent` above 20 %. The variant must not be used.
- **WARN** — a metric is above half of an alarm level (from v4 on, the
  `spent` error at 19.2 % is just under the 20 % alarm but above the 10 %
  warning level). Usable, but worth discussing in the study.
- **OK** — everything comfortably below the thresholds.

---

## Reading the current table

| Question | Where to look | What it says |
|----------|---------------|--------------|
| Did any step drop reviews? | `removed_pct` | No — 0.0 everywhere; the pipeline only transforms. |
| Did the steps distort ratings? | `rating_tvd` | No — 0.0 everywhere; sanity check passes. |
| What did discretizing `spent` buy? | `rows_ge_k*` between v3 and v4 | Rows in a group ≥ 3 jump from 4.15 % to 37.45 % — one decision, most of the privacy gain so far. |
| What did replacing `gmap_id` by categories buy? | `rows_ge_k*` between v4 and v5 (mind the different `qi`) | 20.66 % → 48.04 % of rows in a group ≥ 5, at zero cost on the other metrics. |
| What still needs work? | `singleton_groups_pct` (62.87 % at v5) and the WARN verdicts | Further generalization of `date` / `rating` (step 8 grid), and log tiers to cut the `spent` error. |

## Pitfalls

- **Different `qi` across rows**: v5 has no `gmap_id`, so its k-columns use
  `category` instead. To compare v4 and v5 strictly on the same key,
  regenerate the v4 row with
  `python utility_tests.py --label v4 --qi date,category,rating,spent`.
- **Rounding**: all floats are rounded to 2 decimals for readability; the
  verdicts are computed on the same rounded values (the alarm margins here
  are far wider than a hundredth).
- **One row per run**: re-running a label adds a new row; the file is a
  log, not a table keyed by label. Clean it (`rm results.csv`) when
  regenerating a full comparison.
