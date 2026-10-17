"""
anonymize_v2.py - second anonymization step of the Vermont Google reviews (PPIA Homework 1)

Input : review-Vermont-anon-v1.json   (JSON lines, produced by anonymize_v1.py, next to this script)
Output: review-Vermont-anon-v2.json   (JSON lines, one review per line, next to this script)

What changes compared to v1 (coarser quasi-identifiers, k-anonymity friendly):
 1. the "time" field (HH:MM, Vermont local time) is removed
 2. the "date" field is generalized from YYYY-MM-DD to YYYY-MM (month precision)
Everything else is kept unchanged, in the same order.

Run:  python anonymize_v2.py            (optional: --in FILE --out FILE)
"""
import argparse, json, os

# ------------------------------------------------------------------ helpers
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v1.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v2.json'))
    return ap.parse_args()

def drop_time(row):
    """Remove the 'time' field (HH:MM, Vermont local time)."""
    row.pop('time', None)

def generalize_date(row):
    """Truncate 'date' from YYYY-MM-DD to YYYY-MM (month precision)."""
    if 'date' in row and len(row['date']) >= 7:
        row['date'] = row['date'][:7]

def transform_row(row):
    """Apply all v2 transformations to one review, in place."""
    drop_time(row)
    generalize_date(row)

# ------------------------------------------------------------------ main
def convert_file(infile, outfile):
    """Read the v1 JSON lines file, transform each review, write the v2 file."""
    stats = dict(read=0, written=0)
    with open(infile, encoding='utf-8') as f, \
         open(outfile, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            row = json.loads(line)
            stats['read'] += 1
            transform_row(row)
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
