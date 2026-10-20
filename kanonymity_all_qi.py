"""
kanonymity_all_qi.py - k-anonymity on ALL quasi-identifiers together (PPIA Homework 1)

Input : review-Vermont-anon-v6.json   (JSON lines, produced by anonymize_v6.py)
Output: review-Vermont-anon-v7.json   (JSON lines, one review per line)

Why: kanonymity.py enforces k only on the place (category) dimension, but
k-anonymity is a property of the COMBINATION of quasi-identifiers. Measured
on v6, only ~57% of reviews are in a group of >= 3 when all quasi-identifiers
are combined. This script generalizes the quasi-identifiers and then applies
local suppression until EVERY review is in a group of at least k (default 3).

Quasi-identifiers (what an attacker can know or see on the public review):
    category, date, rating, comment_length_cat,
    pics_num, has_resp, resp_length_cat, resp_delay_hours
`spent` is NOT a quasi-identifier: it is synthetic, an attacker cannot know
it in advance. It is the sensitive attribute and is left untouched here.

Step 1 - global generalization (every review):
  date              'YYYY-MM'      -> 'YYYY-Qn'           (quarter)
  category          list of names  -> one broad group      (12 groups + 'Services & other')
                    based on the FIRST (primary) category: an explicit fixes
                    table first, then whole-word keyword rules in priority order
                    (e.g. 'Animal hospital' -> Pets, not Health)
  pics_num          0, 1, 2, 3, ... -> 0, 1, 2, '3+'
  resp_delay_hours  hours          -> 5 buckets of ~20% each:
                    '<= 6 h', '6-24 h', '1-3 days', '3-14 days', '> 2 weeks'
  (rating, comment_length_cat, has_resp, resp_length_cat are already coarse)

Step 2 - local suppression (only reviews still in a group smaller than k):
  the fields are coarsened one at a time, least useful first, and after each
  step the groups are recomputed so a review stops as soon as it is covered:
    resp_delay_hours -> null, pics_num -> null, resp_length_cat -> null,
    date -> year only, comment_length_cat -> null, date -> null,
    category -> null, rating -> null
  A suppressed value is written as null.
Step 3 - record suppression (last resort): a review that is still below k
  after all the steps above is removed. Every removal is printed (on v6 with
  k = 3 this is a single review).

Run:  python kanonymity_all_qi.py      (optional: --in FILE --out FILE --k 3)
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict

QI = ['category', 'date', 'rating', 'comment_length_cat',
      'pics_num', 'has_resp', 'resp_length_cat', 'resp_delay_hours']
POS = {q: i for i, q in enumerate(QI)}

# ------------------------------------------------------------------ generalization: date
def to_quarter(date):
    """'2019-03' -> '2019-Q1'."""
    if not date:
        return date
    return f'{date[:4]}-Q{(int(date[5:7]) - 1) // 3 + 1}'

# ------------------------------------------------------------------ generalization: category
# Explicit decisions, checked before the keyword rules (exact first-category name).
CATEGORY_FIXES = {
    'Beer garden': 'Food & drink',
    'Cider mill': 'Food & drink',
    'Health food store': 'Groceries & markets',
    'Orchard': 'Groceries & markets',
    'Indoor lodging': 'Lodging',
    'Country club': 'Outdoors & sports',
    'Baseball field': 'Outdoors & sports',
    'Camp': 'Outdoors & sports',
    'Garden center': 'Shopping',
    'Florist': 'Shopping',
    'Rest stop': 'Automotive',
}

# Keyword rules: regular expressions matched on whole words of the lower-case
# first category, tried in this order (the first group that matches wins).
BROAD_GROUPS = [
    ('Pets & animals',          r'animal|veterinar\w*|pets?|dogs?|kennel|grooming'),
    ('Health & medical',        r'hospital|doctor|dentist|dental|clinic|pharmacy|drug store|medical|'
                                r'physician|chiropract\w*|optometr\w*|urgent care|health|therap\w*|'
                                r'orthodont\w*|counsel\w*|psych\w*|surgeon|pediatric\w*|optician|'
                                r'eye care|hearing aid|physiotherap\w*'),
    ('Religion',                r'church|temple|synagogue|mosque|religious|chapel|worship|cathedral|'
                                r'monastery|parish'),
    ('Automotive',              r'auto|car|cars|car dealer|car wash|tires?|gas station|vehicle|'
                                r'motorcycle|truck|oil change|mechanic|towing|parking'),
    ('Outdoors & sports',       r'parks?|hiking|trails?|forest|mountain|lake|beach|ski|golf|'
                                r'recreation|nature|scenic|bridge|waterfall|peak|river|marina|'
                                r'playground|sports?|stadium|swimming|camps?'),
    ('Lodging',                 r'hotel|motel|inn|resort|bed & breakfast|lodge|lodging|hostel|'
                                r'campground|cottage|cabin|rv park|vacation|guest house'),
    ('Food & drink',            r'restaurant|bar|bars|cafe|coffee|bakery|pizza|diner|deli|'
                                r'delicatessen|brew\w*|pub|bistro|grill|food|ice cream|bagel|'
                                r'caterer|winery|tavern|sandwich|steak|steak house|\w*burgers?|'
                                r'sushi|taco|burrito|chicken|donut|tea|juice|dessert|creamery|'
                                r'distillery|wine|pastry|eatery|chocolate'),
    ('Groceries & markets',     r'grocery|supermarket|market|convenience|general store|cheese|'
                                r'dairy|butcher|liquor|beer store|farm|farms|produce|bottle shop|'
                                r'maple'),
    ('Arts & entertainment',    r'museum|gallery|theater|theatre|cinema|movie|music|event venue|'
                                r'art|arts|historical|tourist|attraction|bowling|arcade|exhibit|'
                                r'zoo|amusement|library|banquet|concert|monument|casino'),
    ('Personal care & fitness', r'salon|barber|spa|nail|gym|fitness|beauty|tattoo|massage|yoga|'
                                r'cosmetic\w*|hair'),
    ('Shopping',                r'store|shop|mall|boutique|outlet|dealer|supplier|wholesale\w*'),
]
GROUP_RX = [(g, re.compile(r'\b(?:' + rx + r')\b')) for g, rx in BROAD_GROUPS]
OTHER = 'Services & other'

def to_broad_group(cats):
    """List of categories -> one broad group, from the first (primary) category."""
    if not cats:
        return None
    first = cats[0]
    if first in CATEGORY_FIXES:
        return CATEGORY_FIXES[first]
    name = first.lower()
    for group, rx in GROUP_RX:
        if rx.search(name):
            return group
    return OTHER

# ------------------------------------------------------------------ generalization: other fields
def cap_pics(n):
    """0, 1, 2 stay; 3 or more photos become '3+'."""
    return n if n is None or n < 3 else '3+'

DELAY_BUCKETS = [(6, '<= 6 h'), (24, '6-24 h'), (72, '1-3 days'),
                 (24 * 14, '3-14 days'), (float('inf'), '> 2 weeks')]

def delay_bucket(hours):
    """Reply delay in hours -> one of 5 buckets of ~20% each (None stays None)."""
    if hours is None:
        return None
    for limit, label in DELAY_BUCKETS:
        if hours <= limit:
            return label

def generalize(row):
    """Published row -> list of generalized quasi-identifier values (order of QI)."""
    return [to_broad_group(row['category']), to_quarter(row['date']), row['rating'],
            row['comment_length_cat'], cap_pics(row['pics_num']), row['has_resp'],
            row['resp_length_cat'], delay_bucket(row['resp_delay_hours'])]

# ------------------------------------------------------------------ local suppression
year_only = lambda d: d[:4] if d else d
to_null = lambda v: None
SUPPRESSION_STEPS = [            # (label, field, how the value is coarsened)
    ('resp_delay_hours -> null',   'resp_delay_hours',   to_null),
    ('pics_num -> null',           'pics_num',           to_null),
    ('resp_length_cat -> null',    'resp_length_cat',    to_null),
    ('date -> year only',          'date',               year_only),
    ('comment_length_cat -> null', 'comment_length_cat', to_null),
    ('date -> null',               'date',               to_null),
    ('category -> null',           'category',           to_null),
    ('rating -> null',             'rating',             to_null),
]

def small_rows(keys, k):
    """Indices of the reviews whose group has fewer than k reviews."""
    size = Counter(map(tuple, keys))
    return [i for i, key in enumerate(keys) if size[tuple(key)] < k]

def suppress(keys, k):
    """Coarsen field by field only the reviews below k. Returns per-step counts."""
    log = []
    for label, field, how in SUPPRESSION_STEPS:
        todo = small_rows(keys, k)
        if not todo:
            break
        p, changed = POS[field], 0
        for i in todo:
            new = how(keys[i][p])
            if new != keys[i][p]:
                keys[i][p] = new
                changed += 1
        log.append((label, len(todo), changed))
    return log

# ------------------------------------------------------------------ reporting
def coverage(keys, k, upto=len(QI)):
    size = Counter(tuple(key[:upto]) for key in keys)
    n = len(keys)
    covered = sum(1 for key in keys if size[tuple(key[:upto])] >= k)
    unique = sum(1 for key in keys if size[tuple(key[:upto])] == 1)
    return 100 * covered / n, 100 * (n - covered) / n, 100 * unique / n, len(size), min(size.values())

def negative_share(rows_rating_len):
    """Utility check: % of 1-2 star reviews per comment length class."""
    tot, neg = Counter(), Counter()
    for rating, length in rows_rating_len:
        if rating is None:
            continue
        tot[length] += 1
        neg[length] += rating <= 2
    return {c: 100 * neg[c] / tot[c] for c in ('short', 'medium', 'long') if tot[c]}

# ------------------------------------------------------------------ main
def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='infile', default=os.path.join(here, 'review-Vermont-anon-v6.json'))
    ap.add_argument('--out', default=os.path.join(here, 'review-Vermont-anon-v7.json'))
    ap.add_argument('--k', type=int, default=3, help='minimum group size (default 3)')
    return ap.parse_args()

def main():
    a = parse_args()

    # pass 1: read, remember the published QI, build the generalized QI
    published, keys = [], []
    first_cats = defaultdict(Counter)                  # group -> first categories (for review)
    utility_before = []
    with open(a.infile, encoding='utf-8') as f:
        for line in f:
            row = json.loads(line)
            cats = row['category']
            published.append((tuple(sorted(cats)) if cats else None, row['date'], row['rating'],
                              row['comment_length_cat'], row['pics_num'], row['has_resp'],
                              row['resp_length_cat'], row['resp_delay_hours']))
            g = generalize(row)
            keys.append(g)
            if cats:
                first_cats[g[0]][cats[0]] += 1
            utility_before.append((row['rating'], row['comment_length_cat']))
    n = len(keys)
    print(f'reviews read: {n:,}   k = {a.k}   (spent untouched: sensitive attribute)')

    print('\nBroad groups (share of reviews, top first categories - please review):')
    group_sizes = Counter(key[0] for key in keys)
    for g, cnt in group_sizes.most_common():
        top = ', '.join(c for c, _ in first_cats[g].most_common(8)) if g else 'place already suppressed'
        print(f'  {str(g):26s}{100 * cnt / n:5.1f}%  {top}')

    stages = [('category, date, rating', 3), ('+ comment length', 4),
              ('+ pics, has_resp, resp_length', 7), ('+ resp_delay', 8)]
    def report(title, ks):
        print(f'\n{title}')
        print(f'  {"QI used":32s}{"covered":>10s}{"not cov.":>10s}{"unique":>9s}{"groups":>10s}{"smallest":>10s}')
        for label, upto in stages:
            cov, notc, uniq, groups, smallest = coverage(ks, a.k, upto)
            print(f'  {label:32s}{cov:9.2f}%{notc:9.2f}%{uniq:8.2f}%{groups:10,}{smallest:10,}')

    report('BEFORE (published v6):', published)
    report('AFTER step 1 - generalization:', keys)

    # step 2: local suppression
    log = suppress(keys, a.k)
    print('\nStep 2 - local suppression (reviews below k at that step / values changed):')
    for label, below, changed in log:
        print(f'  {label:30s} {below:8,} reviews below k   {changed:8,} values changed ({100 * changed / n:.2f}%)')
    # step 3: record suppression of whatever is still below k
    removed = set(small_rows(keys, a.k))
    print(f'\nStep 3 - record suppression: {len(removed):,} review(s) still below k removed '
          f'({100 * len(removed) / n:.4f}%)')
    final = [key for i, key in enumerate(keys) if i not in removed]
    report('FINAL v7 (after steps 1-3):', final)
    left = small_rows(final, a.k)
    print(f'\n  reviews below k = {a.k}: {len(left):,}' + ('  -> every review is covered' if not left else '  WARNING'))

    # utility check: does "unhappy customers write more" survive?
    before = negative_share(utility_before)
    after = negative_share((key[POS['rating']], key[POS['comment_length_cat']]) for key in final)
    print('\nUtility check - % negative (1-2 stars) by comment length:')
    for c in before:
        print(f'  {c:7s} before {before[c]:5.1f}%   after {after.get(c, float("nan")):5.1f}%')

    # pass 2: write v7 with the final values
    with open(a.infile, encoding='utf-8') as f, open(a.out, 'w', encoding='utf-8', newline='\n') as o:
        for i, line in enumerate(f):
            if i in removed:
                continue
            row = json.loads(line)
            for q, v in zip(QI, keys[i]):
                row[q] = v
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'\nwritten: {n - len(removed):,} reviews -> {a.out}')

if __name__ == '__main__':
    main()
