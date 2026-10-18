"""
anonymize_v6.py - sixth anonymization step of the Vermont Google reviews (PPIA Homework 1)

Input : review-Vermont-anon-v5.json   (JSON lines, produced by kanonymity.py)
Output: review-Vermont-anon-v6.json   (JSON lines, one review per line)

What changes compared to v5 (PLAN.md, step 6):
 1. the `state` field is removed. It is constant ("Vermont" in every row),
    so it carries zero information and no identifying power - in the
    published schema it is pure noise (and ~11 useless bytes per row).
    The dataset being Vermont-only is documented in the README instead.
No other field changes; no rows are removed; counters are printed.

Run:  python anonymize_v6.py            (optional: --in FILE --out FILE)
"""
import argparse, json, os

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v5.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v6.json'))
    return ap.parse_args()

def transform_row(row):
    """Drop the constant `state` field, keep everything else in order."""
    row.pop('state', None)
    return row

# ------------------------------------------------------------------ main
def convert_file(infile, outfile):
    """Read the v5 JSON lines file, drop `state`, write the v6 file."""
    stats = dict(read=0, written=0, removed=0)
    with open(infile, encoding='utf-8') as f, \
         open(outfile, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            row = transform_row(json.loads(line))
            stats['read'] += 1
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
            stats['written'] += 1
    return stats

def main():
    a = parse_args()
    stats = convert_file(a.infile, a.out)
    print(stats)
    print('output:', a.out)

if __name__ == '__main__':
    main()
