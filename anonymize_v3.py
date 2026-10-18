"""
anonymize_v3.py - third anonymization step of the Vermont Google reviews (PPIA Homework 1)

Input : review-Vermont-anon-v2.json   (JSON lines, produced by anonymize_v2.py, next to this script)
Output: review-Vermont-anon-v3.json   (JSON lines, one review per line, next to this script)

What changes compared to v2 (PLAN.md, objective 3a):
 1. comment_length (exact character count, too identifying) becomes
    comment_length_cat with 3 ordered categories:
      "short"  < 50 chars    - carries little information (60% of reviews,
                               many of them 0 = no text at all)
      "medium" 50-500 chars  - the informative core of the distribution
      "long"   > 500 chars   - verbose outliers (~3.5% of reviews; p95=414,
                               p99=887 measured on v2, hence the 500 bound)
 2. resp_length becomes resp_length_cat with the same 3 bounds
    (null stays null when there is no response; 2.7% of responses are "long")
No rows are removed; category counts are printed.

Run:  python anonymize_v3.py            (optional: --in FILE --out FILE)
"""
import argparse
import json
import os
from collections import Counter

SHORT_MAX = 50    # below this: "short"
LONG_MIN = 500    # above this: "long"

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v2.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v3.json'))
    return ap.parse_args()

def length_category(n):
    """Map an exact character count to its ordered category."""
    if n is None:
        return None
    if n < SHORT_MAX:
        return 'short'
    if n <= LONG_MIN:
        return 'medium'
    return 'long'

def transform_row(row):
    """Replace the exact length fields by their 3-level categories, keep order."""
    out = {}
    for key, value in row.items():
        if key == 'comment_length':
            out['comment_length_cat'] = length_category(value or 0)
        elif key == 'resp_length':
            out['resp_length_cat'] = length_category(value)
        else:
            out[key] = value
    return out

# ------------------------------------------------------------------ main
def convert_file(infile, outfile):
    """Read the v2 JSON lines file, categorize the lengths, write the v3 file."""
    stats = dict(read=0, written=0, removed=0)
    cat_counts = {'comment_length_cat': Counter(), 'resp_length_cat': Counter()}
    with open(infile, encoding='utf-8') as f, \
         open(outfile, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            row = transform_row(json.loads(line))
            stats['read'] += 1
            stats['written'] += 1
            for field in cat_counts:
                cat_counts[field][row[field]] += 1
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
    return stats, cat_counts

def main():
    a = parse_args()
    stats, cat_counts = convert_file(a.infile, a.out)
    print(stats)
    for field, counts in cat_counts.items():
        total = sum(counts.values())
        print(field + ':')
        for cat in ('short', 'medium', 'long', None):
            if cat in counts:
                n = counts[cat]
                print(f'  {str(cat):6}: {n:7} ({n / total * 100:5.2f}%)')
    print('output:', a.out)

if __name__ == '__main__':
    main()
