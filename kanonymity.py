"""
kanonymity.py - k-anonymity pass on the place dimension (PLAN.md, step 5)

Input : review-Vermont-anon-v4.json   (JSON lines, produced by anonymize_v4.py)
Output: review-Vermont-anon-v5.json   (JSON lines, one review per line)

Idea (per the team's plan): the exact place is the most identifying
quasi-identifier (72% of full-QI groups were singletons at v4), so the
`gmap_id` is replaced by the CATEGORIES of the corresponding gmap_id.
Two places with the same published categories are indistinguishable.

Recoding ladder for the place dimension - every published place group must
hold at least k reviews (default k = 5):
 - level 0: the full sorted category list of the gmap_id (places with the
   same categories merge; 99.87% of reviews are already fine at this level
   for k = 5);
 - level 1: the first (primary) category only, counted among the places
   that did not pass level 0;
 - level 2: suppressed (category -> null) - the place information is dropped
   but the review itself is kept.

No rows are removed; every counter is printed (nothing is ever silent).

Measured effect (k = 5): rows in a full-QI group (date, category, rating,
spent) of size >= 5 go from 20.66% (v4, with gmap_id) to ~48% (v5).

Run:  python kanonymity.py            (optional: --in FILE --out FILE --k 5)
"""
import argparse
import json
import os
from collections import Counter

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v4.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v5.json'))
    ap.add_argument('--k', type=int, default=5, help='minimum reviews per place group')
    return ap.parse_args()

def category_key(categories):
    """Hashable identity of a category list (sorted, None-safe)."""
    return tuple(sorted(categories)) if categories else None

# ------------------------------------------------------------------ pass 1: place statistics
def load_places(infile):
    """Reviews per gmap_id and the categories of each gmap_id."""
    reviews = Counter()
    places = {}
    with open(infile, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            g = row['gmap_id']
            reviews[g] += 1
            if g not in places:
                places[g] = row.get('category')
    return reviews, places

def assign_place_groups(reviews, places, k):
    """Recoding ladder: full categories -> first category -> suppressed.

    Returns {gmap_id: (published categories or None, level)} where level is
    0 (full list), 1 (first category) or 2 (suppressed). Levels 1 and 2 are
    computed among the places that did not pass the previous level only.
    """
    # level 0: the full category list, shared by every place with the same categories
    tuple_rows = Counter()
    for g, cats in places.items():
        tuple_rows[category_key(cats)] += reviews[g]
    groups, remaining = {}, []
    for g, cats in places.items():
        if cats and tuple_rows[category_key(cats)] >= k:
            groups[g] = (sorted(cats), 0)
        else:
            remaining.append(g)
    # level 1: the first (primary) category, counted among the remaining places only
    first_rows = Counter()
    for g in remaining:
        if places[g]:
            first_rows[places[g][0]] += reviews[g]
    for g in remaining:
        cats = places[g]
        if cats and first_rows[cats[0]] >= k:
            groups[g] = ([cats[0]], 1)
        else:
            groups[g] = (None, 2)          # level 2: place information dropped
    return groups

# ------------------------------------------------------------------ pass 2: conversion
def convert_file(infile, outfile, groups):
    """Drop gmap_id, publish the recoded categories, write the v5 file."""
    stats = dict(read=0, written=0, removed=0,
                 level0_full_categories=0, level1_first_category=0,
                 level2_suppressed=0)
    group_rows = Counter()
    with open(infile, encoding='utf-8') as f, \
         open(outfile, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            row = json.loads(line)
            stats['read'] += 1
            published, level = groups[row.pop('gmap_id')]
            row['category'] = published
            group_rows[category_key(published)] += 1
            stats[f'level{level}_' + ('full_categories', 'first_category', 'suppressed')[level]] += 1
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
            stats['written'] += 1
    return stats, group_rows

# ------------------------------------------------------------------ main
def main():
    a = parse_args()
    reviews, places = load_places(a.infile)
    groups = assign_place_groups(reviews, places, a.k)
    stats, group_rows = convert_file(a.infile, a.out, groups)

    print(stats)
    print(f'place groups: {len(group_rows)}'
          f' | smallest: {min(group_rows.values())} rows'
          f' | largest: {max(group_rows.values())} rows')
    below = {g: n for g, n in group_rows.items() if n < a.k}
    if below:
        print(f'WARNING: {len(below)} place groups below k={a.k}:', below)
    print('output:', a.out)

if __name__ == '__main__':
    main()
