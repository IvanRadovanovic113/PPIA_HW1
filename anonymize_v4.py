"""
anonymize_v4.py - fourth anonymization step of the Vermont Google reviews (PPIA Homework 1)

Input : review-Vermont-anon-v3.json   (JSON lines, produced by anonymize_v3.py, next to this script)
Output: review-Vermont-anon-v4.json   (JSON lines, one review per line, next to this script)

What changes compared to v3 (PLAN.md, objectives 3b then 6 - in this order,
because outliers would break the rounding):

 1. Outliers (3b): spent is clipped to the [q05, q95] range of its SPEND
    PROFILE (same profiles as anonymize_v1: $200 is common at a restaurant
    but rare at a gas station, so quantiles are per profile, not global).
    The car-dealer profile alone reaches q95 = $37,289, max = $133,916.
 2. Rounding (6): spent is rounded to the nearest tier of a growing ladder
    [0, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000]; anything
    above the last tier is clamped to it (e.g. 1987.31 -> 2000, 22000 -> 10000).
 3. Rarity check (6): tiers holding fewer than MERGE_MIN_SHARE (5% rule of
    PLAN.md objective 3) of the rows are merged into their nearest surviving
    neighbour, rarest first, until every surviving tier passes the rule.

No rows are removed; all counters are printed (nothing is ever silent).

Run:  python anonymize_v4.py     (optional: --in FILE --out FILE --merge-min 0.05)
"""
import argparse
import json
import os
from collections import Counter

from anonymize_v1 import spend_profile

TIERS = [0, 5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000]
MERGE_MIN_SHARE = 0.05          # 5% rule: a tier below this share is too identifying

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v3.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v4.json'))
    ap.add_argument('--merge-min', type=float, default=MERGE_MIN_SHARE,
                    help='minimum share of rows per tier (default: 0.05 = 5%% rule)')
    return ap.parse_args()

def profile_key(categories):
    """Spend profile of a review, as a hashable key (mixture tuple from v1)."""
    return tuple(spend_profile(categories or []))

def quantile(sorted_vals, p):
    """p-th quantile of an already sorted list (index-based, like v1's price)."""
    return sorted_vals[min(int(len(sorted_vals) * p), len(sorted_vals) - 1)]

def load_profile_quantiles(infile):
    """Pass 1: collect all spent values per profile and compute (q05, q95)."""
    vals = {}
    with open(infile, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            vals.setdefault(profile_key(row.get('category')), []).append(row.get('spent') or 0)
    return {key: (quantile(sorted(v), 0.05), quantile(sorted(v), 0.95))
            for key, v in vals.items()}

def clip_to_quantiles(spent, q05, q95):
    """Bottom/top-coding: clamp spent into its profile's [q05, q95] range."""
    return min(max(spent, q05), q95)

def round_to_tier(spent):
    """Round to the nearest tier of the ladder; clamp above the last tier."""
    if spent <= 0:
        return 0
    best = TIERS[0]
    for tier in TIERS:
        if abs(spent - tier) < abs(spent - best):
            best = tier
    return best

def quantize(spent, quantiles, profile):
    """Full v4 transformation of one spent value: coding then rounding."""
    q05, q95 = quantiles[profile]
    return round_to_tier(clip_to_quantiles(spent, q05, q95))

def count_tiers(infile, quantiles):
    """Pass 2: quantize every spent value and count rows per tier."""
    counts = Counter()
    with open(infile, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            counts[quantize(row.get('spent') or 0, quantiles, profile_key(row.get('category')))] += 1
    return counts

def merge_rare_tiers(counts, min_share):
    """Merge every tier below min_share into its nearest surviving neighbour.

    Rarest tier first; "nearest" is by tier value, ties go to the neighbour
    with more rows. Returns {original tier -> surviving tier}.
    """
    counts = dict(counts)
    total = sum(counts.values())
    min_rows = min_share * total
    mapping = {tier: tier for tier in counts}
    while True:
        rare = [t for t, n in counts.items() if n < min_rows]
        if not rare:
            return mapping
        t = min(rare, key=lambda tier: (counts[tier], tier))
        neighbours = [u for u in counts if u != t]
        target = min(neighbours, key=lambda u: (abs(u - t), -counts[u]))
        counts[target] += counts.pop(t)
        for tier in mapping:
            if mapping[tier] == t:
                mapping[tier] = target

# ------------------------------------------------------------------ main
def convert_file(infile, outfile, quantiles, mapping):
    """Pass 3: apply coding + rounding + merged tiers and write the v4 file."""
    stats = dict(read=0, written=0, removed=0, coded_low=0, coded_high=0, merged_rows=0)
    tier_counts = Counter()
    with open(infile, encoding='utf-8') as f, \
         open(outfile, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            row = json.loads(line)
            stats['read'] += 1
            spent = row.get('spent') or 0
            q05, q95 = quantiles[profile_key(row.get('category'))]
            coded = clip_to_quantiles(spent, q05, q95)
            if coded < spent:
                stats['coded_low'] += 1
            elif coded > spent:
                stats['coded_high'] += 1
            tier = round_to_tier(coded)
            final = mapping[tier]
            if final != tier:
                stats['merged_rows'] += 1
            row['spent'] = final
            tier_counts[final] += 1
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
            stats['written'] += 1
    return stats, tier_counts

def main():
    a = parse_args()
    quantiles = load_profile_quantiles(a.infile)
    mapping = merge_rare_tiers(count_tiers(a.infile, quantiles), a.merge_min)
    stats, tier_counts = convert_file(a.infile, a.out, quantiles, mapping)
    print(stats)
    print('tiers kept:', sorted(tier_counts))
    total = sum(tier_counts.values())
    for tier in sorted(tier_counts):
        print(f'  {tier:6}: {tier_counts[tier]:7} ({tier_counts[tier] / total * 100:5.2f}%)')
    print('output:', a.out)

if __name__ == '__main__':
    main()
