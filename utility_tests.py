"""
utility_tests.py - utility and data-loss tests for the anonymized reviews
                   (PLAN.md, objective 4)

Compares a baseline version (default: v1) with the current version
(default: v4) and reports how much information the anonymization cost:

 - removed rows (versions keep the same rows in the same order, so they are
   compared index by index; a count mismatch is reported loudly)
 - spent error: exact matches, median relative error, mean absolute error,
   median log10 error (the price of outlier clipping + tier rounding)
 - rating distribution preservation (total variation distance, 0 = identical)
 - date generalization: distinct days in baseline vs distinct months in current
 - comment length: exact counts vs 3 categories, median length per category
 - k-anonymity health: share of rows in a QI group of size >= k (default k=3,5,10)

Alarm thresholds (PLAN.md objective 4): the variant is REJECTED if more than
--removed-alarm (10%) of the rows were removed, or if the median relative
error on spent exceeds --error-alarm (20%). WARN at half those levels,
OK otherwise.

Every run is appended to results.csv (one row per tested variant), which
feeds the study discussion (PLAN.md objective 5).

Run:  python utility_tests.py --label v4
      (optional: --baseline FILE --current FILE --qi F1,F2 --ks 3,5,10
                 --results results.csv --removed-alarm 0.10 --error-alarm 0.20)
"""
import argparse
import csv
import json
import math
import os
from collections import Counter

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', default=os.path.join(here, 'review-Vermont-anon-v1.json'),
                    help='version to compare against (row-for-row)')
    ap.add_argument('--current', default=os.path.join(here, 'review-Vermont-anon-v4.json'),
                    help='version being tested')
    ap.add_argument('--label', default='v4', help='variant name in results.csv')
    ap.add_argument('--qi', default='date,gmap_id,rating,spent',
                    help='comma-separated quasi-identifier fields for the k-health check')
    ap.add_argument('--ks', default='3,5,10', help='k values for the k-health check')
    ap.add_argument('--results', default=os.path.join(here, 'results.csv'))
    ap.add_argument('--removed-alarm', type=float, default=0.10,
                    help='REJECT above this share of removed rows (default 0.10)')
    ap.add_argument('--error-alarm', type=float, default=0.20,
                    help='REJECT above this median relative error on spent (default 0.20)')
    return ap.parse_args()

def median(sorted_vals):
    """Median of an already sorted list."""
    n = len(sorted_vals)
    mid = n // 2
    return sorted_vals[mid] if n % 2 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2

def to_hashable(value):
    """Lists (e.g. category) become tuples so a QI key can be hashed."""
    return tuple(value) if isinstance(value, list) else value

# ------------------------------------------------------------------ paired scan
def paired_scan(baseline, current):
    """Stream both versions in lockstep and collect the utility metrics."""
    m = dict(n=0, paired=True, removed=0,
             spent_exact=0, spent_abs_err=[], spent_rel_err=[], spent_log_err=[],
             rating_base=Counter(), rating_cur=Counter(),
             days_base=set(), months_cur=Counter(),
             cat_lengths={})                    # category -> [baseline lengths]
    with open(baseline, encoding='utf-8') as fb, open(current, encoding='utf-8') as fc:
        for lb, lc in zip(fb, fc):
            rb, rc = json.loads(lb), json.loads(lc)
            m['n'] += 1

            base, cur = rb.get('spent') or 0, rc.get('spent') or 0
            err = abs(cur - base)
            m['spent_abs_err'].append(err)
            if err == 0:
                m['spent_exact'] += 1
            m['spent_rel_err'].append(err / base if base > 0 else (0.0 if cur == 0 else 1.0))
            m['spent_log_err'].append(abs(math.log10(cur + 1) - math.log10(base + 1)))

            m['rating_base'][rb.get('rating')] += 1
            m['rating_cur'][rc.get('rating')] += 1
            m['days_base'].add(rb['date'])
            m['months_cur'][rc['date']] += 1

            cat = rc.get('comment_length_cat')
            if cat is not None:
                m['cat_lengths'].setdefault(cat, []).append(rb.get('comment_length') or 0)

        if fb.readline() or fc.readline():      # leftover lines: counts differ
            m['paired'] = False
    return m

def removed_rate(baseline, n_paired):
    """Share of baseline rows that did not make it to the current version."""
    with open(baseline, encoding='utf-8') as f:
        n_base = sum(1 for _ in f)
    return n_base, max(0, n_base - n_paired) / n_base

# ------------------------------------------------------------------ k-anonymity health
def qi_groups(current, qi_fields):
    """Count rows per quasi-identifier combination."""
    counts = Counter()
    with open(current, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            counts[tuple(to_hashable(row.get(field)) for field in qi_fields)] += 1
    return counts

def k_health(counts, ks):
    """Share of rows living in a group of size >= k, for each k."""
    total = sum(counts.values())
    return {k: sum(n for n in counts.values() if n >= k) / total for k in ks}

# ------------------------------------------------------------------ distances
def total_variation(counter_a, counter_b):
    """Total variation distance between two histograms (0 = identical)."""
    keys = set(counter_a) | set(counter_b)
    total_a = sum(counter_a.values()) or 1
    total_b = sum(counter_b.values()) or 1
    return 0.5 * sum(abs(counter_a[k] / total_a - counter_b[k] / total_b) for k in keys)

# ------------------------------------------------------------------ report
def build_metrics(a, m, groups, ks):
    """All metrics of one tested variant, as one flat dict."""
    n_base, removed = removed_rate(a.baseline, m['n'])
    rel_errs = sorted(m['spent_rel_err'])
    abs_errs = sorted(m['spent_abs_err'])
    log_errs = sorted(m['spent_log_err'])
    health = k_health(groups, ks)
    singletons = sum(1 for n in groups.values() if n == 1)
    return {
        'label': a.label,
        'qi': a.qi,
        'n_baseline': n_base,
        'n_current': m['n'],
        'paired': m['paired'],
        'removed_pct': removed * 100,
        'spent_exact_pct': m['spent_exact'] / m['n'] * 100,
        'spent_median_rel_err_pct': median(rel_errs) * 100,
        'spent_mean_abs_err': sum(abs_errs) / len(abs_errs),
        'spent_median_log10_err': median(log_errs),
        'rating_tvd': total_variation(m['rating_base'], m['rating_cur']),
        'days_baseline': len(m['days_base']),
        'months_current': len(m['months_cur']),
        'groups': len(groups),
        'singleton_groups_pct': singletons / len(groups) * 100,
        **{f'rows_ge_k{k}_pct': health[k] * 100 for k in ks},
    }

def verdict(metrics, a):
    """OK / WARN / REJECT according to the alarm thresholds of objective 4."""
    if metrics['removed_pct'] > 100 * a.removed_alarm or \
       metrics['spent_median_rel_err_pct'] > 100 * a.error_alarm:
        return 'REJECT'
    if metrics['removed_pct'] > 50 * a.removed_alarm or \
       metrics['spent_median_rel_err_pct'] > 50 * a.error_alarm:
        return 'WARN'
    return 'OK'

def print_report(metrics, m, ks):
    """Human-readable report of one tested variant."""
    print(f"--- utility report: {metrics['label']} ---")
    print(f"rows: baseline {metrics['n_baseline']}, current {metrics['n_current']}"
          f" (paired: {metrics['paired']})")
    print(f"removed rows: {metrics['removed_pct']:.2f}%")
    print(f"spent: exact {metrics['spent_exact_pct']:.2f}%"
          f" | median rel err {metrics['spent_median_rel_err_pct']:.2f}%"
          f" | mean abs err ${metrics['spent_mean_abs_err']:.2f}"
          f" | median log10 err {metrics['spent_median_log10_err']:.4f}")
    print(f"rating distribution: total variation distance {metrics['rating_tvd']:.6f}")
    print(f"date: {metrics['days_baseline']} distinct days -> "
          f"{metrics['months_current']} distinct months")
    for cat in ('short', 'medium', 'long'):
        lengths = sorted(m['cat_lengths'].get(cat, []))
        if lengths:
            print(f"comment_length_cat '{cat}': {len(lengths):7} rows"
                  f" | median original length {median(lengths):.0f} chars")
    print(f"QI groups ({metrics['qi']}): {metrics['groups']} groups,"
          f" {metrics['singleton_groups_pct']:.2f}% singletons")
    for k in ks:
        print(f"  rows in a group >= {k}: {metrics[f'rows_ge_k{k}_pct']:.2f}%")

def append_results(results_file, metrics, ks):
    """One row per tested variant, header written on first use (objective 5)."""
    fields = list(metrics)
    for k in ks:
        col = f'rows_ge_k{k}_pct'
        if col not in fields:
            fields.append(col)
    new_file = not os.path.exists(results_file)
    with open(results_file, 'a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            writer.writeheader()
        writer.writerow(metrics)

# ------------------------------------------------------------------ main
def main():
    a = parse_args()
    ks = [int(k) for k in a.ks.split(',')]
    qi_fields = a.qi.split(',')

    m = paired_scan(a.baseline, a.current)
    groups = qi_groups(a.current, qi_fields)
    metrics = build_metrics(a, m, groups, ks)
    metrics['verdict'] = verdict(metrics, a)

    print_report(metrics, m, ks)
    print(f"verdict: {metrics['verdict']}"
          f" (alarms: removed > {100 * a.removed_alarm:.0f}%,"
          f" spent median rel err > {100 * a.error_alarm:.0f}%)")
    append_results(a.results, metrics, ks)
    print('results appended to:', a.results)

if __name__ == '__main__':
    main()
