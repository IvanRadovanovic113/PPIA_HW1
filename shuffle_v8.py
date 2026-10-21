"""
shuffle_v8.py - random row order for the published data (PPIA Homework 1)

Input : review-Vermont-anon-v7.json.gz   (k-anonymous data, k = 5 on all QI)
Output: review-Vermont-anon-v8.json      (same rows, random order)
        review-Vermont-anon-v8.json.gz   (compressed copy, the one to commit)

Why: every step so far kept the row order of the original scrape, where the
reviews of one place are stored one after the other (and sorted by time).
Even with gmap_id removed, an attacker could rebuild "this block of rows is
one place" from the position of the rows, and link a block back to a real
place by its size and its sequence of dates/ratings. Shuffling the rows
removes that hidden information; no value of any row is changed.

The shuffle uses random.SystemRandom (the operating system's secure random
generator) on purpose, without a seed: with a fixed seed written in this
public script, anyone could recompute the permutation and undo it.
(--seed exists only for testing and must not be used for the release.)

Checks printed at the end:
 - same number of rows, and exactly the same rows (as a multiset);
 - share of neighbouring rows with the same category / the same QI values,
   before and after (after the shuffle it should match pure chance).

Run:  python shuffle_v8.py        (optional: --in FILE --out FILE --seed N)
"""
import argparse
import gzip
import json
import os
import random
from collections import Counter

QI = ['category', 'date', 'rating', 'comment_length_cat',
      'pics_num', 'has_resp', 'resp_length_cat', 'resp_delay_hours']

def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v7.json.gz'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v8.json'))
    ap.add_argument('--seed', type=int, default=None, help='TESTING ONLY - makes the shuffle reversible')
    return ap.parse_args()

def read_lines(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as f:
        return [line if line.endswith('\n') else line + '\n' for line in f if line.strip()]

def neighbours(lines):
    """% of consecutive pairs with the same category, and with the same full QI tuple."""
    rows = [json.loads(l) for l in lines]
    same_cat = sum(1 for a, b in zip(rows, rows[1:]) if a['category'] == b['category'])
    same_qi = sum(1 for a, b in zip(rows, rows[1:]) if all(a[q] == b[q] for q in QI))
    pairs = len(rows) - 1
    cats = Counter(r['category'] for r in rows)
    chance = sum((c / len(rows)) ** 2 for c in cats.values())   # expected if random
    return 100 * same_cat / pairs, 100 * same_qi / pairs, 100 * chance

def main():
    a = parse_args()
    lines = read_lines(a.infile)
    print(f'read {len(lines):,} rows from {a.infile}')
    before_cat, before_qi, chance = neighbours(lines)

    shuffled = lines[:]
    if a.seed is None:
        random.SystemRandom().shuffle(shuffled)
    else:
        print(f'WARNING: --seed {a.seed} makes the order reproducible - do not publish this file')
        random.Random(a.seed).shuffle(shuffled)

    # checks: nothing lost, nothing changed, only the order
    assert len(shuffled) == len(lines), 'row count changed'
    assert Counter(shuffled) == Counter(lines), 'rows changed'
    moved = sum(1 for x, y in zip(lines, shuffled) if x != y)
    after_cat, after_qi, _ = neighbours(shuffled)

    with open(a.out, 'w', encoding='utf-8', newline='\n') as o:
        o.writelines(shuffled)
    with gzip.open(a.out + '.gz', 'wt', encoding='utf-8', newline='\n') as o:
        o.writelines(shuffled)

    print(f'rows: {len(shuffled):,} (same rows, same values)   rows at a different position: {100 * moved / len(lines):.2f}%')
    print('neighbouring rows with the same ...      before    after   (random chance)')
    print(f'  category                              {before_cat:6.2f}%  {after_cat:6.2f}%   ({chance:.2f}%)')
    print(f'  all 8 quasi-identifiers               {before_qi:6.2f}%  {after_qi:6.2f}%')
    print(f'written: {a.out}  and  {a.out}.gz')

if __name__ == '__main__':
    main()
