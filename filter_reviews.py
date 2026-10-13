"""
filter_reviews.py - pick the 50,000 "most complete / most sensitive" Google reviews
from all 5 states (PPIA Homework 1).

A review is ELIGIBLE if it has: a rating, a reviewer name, an owner response, and
text that mentions at least one kind of sensitive information (names, family,
children, health, home, finance, work).  Eligible reviews are RANKED by:
    1. has photos   2. number of sensitive categories   3. text length
(With --allow-no-response the response is not required and becomes a tie-breaker
 after the number of categories - that was the earlier version.)
The top N are copied unchanged into the output file, with one extra field "state".

Usage (run from the folder with the review-*.json / meta-*.json files):
    python filter_reviews.py all                # everything in one go
or step by step (useful because each scan can take 1-2 minutes):
    python filter_reviews.py names              # step 1: build first-name dictionary
    python filter_reviews.py scan Vermont       # step 2: flag reviews of one state
    python filter_reviews.py select             # step 3: rank + write output
Options: --allow-no-response   (do not require an owner response)
         --data DIR (input folder, default: this script's folder)
         --work DIR (intermediate files, default: <data>/_work)
         --n 50000  (how many reviews to keep)
"""
import argparse, collections, json, os, pickle, re

STATES = ['Alaska', 'Delaware', 'Rhode_Island', 'Vermont', 'Wyoming']

# ---------------------------------------------------------------- sensitive categories
def rx(p):
    # \b = word boundary, re.I = ignore case
    return re.compile(r'\b(?:' + p + r')\b', re.I)

CATS = {
    # ambiguous family words (son, mom, sister...) only count after a possessive,
    # so business names like "Smith & Sons" or "Mom's Diner" do not match
    'family': rx(r"husband|hubby|wife|spouse|(?:my|our|his|her|their) (?:sons?|daughters?|mom|mother|mum|dad|father|"
                 r"parents|brothers?|sisters?|siblings|aunts?|uncles?|cousins?|nieces?|nephews?|family|partner|"
                 r"grand(?:ma|mother|pa|father|parents))|fianc[eé]e?|boyfriend|girlfriend|in-laws?"),
    'children': rx(r"kids?|children|child|bab(?:y|ies)|toddlers?|infants?|newborn|grandkids|grand(?:son|daughter)s?|"
                   r"\d+\s*(?:year|yr)s?[- ]old|teen(?:ager)?s?|stroller|daycare|diapers?"),
    # vague words need context: "got sick" not "sick view", "back pain" not "pain au chocolat"
    'health': rx(r"doctors?|physician|nurses?|hospital|emergency room|surgery|surgeon|cancer|chemo|diabet\w*|pregnan\w*|"
                 r"wheelchair|disab\w*|handicap\w*|therap(?:y|ist)|medications?|prescriptions?|illness|"
                 r"(?:got|was|were|felt|get|getting) sick|food poisoning|injur\w*|broke my|allerg\w*|celiac|dentist|dental|"
                 r"anxiety|depress\w*|autis\w*|dementia|alzheimer\w*|had a stroke|heart attack|diagnos\w*|tested positive|"
                 r"chronic|(?:back|neck|knee|hip|tooth|chest|chronic) pain|in pain"),
    'home': rx(r"(?:my|our) (?:house|home|apartment|condo|driveway|street|neighborhood|property|yard|basement|roof|furnace|"
               r"address)|neighbou?rs?|i live|we live|moved (?:here|to)"),
    'finance': rx(r"loans?|mortgage|debt|bankrupt\w*|credit score|unemploy\w*|laid off|paycheck|can'?t afford|"
                  r"insurance claim|my bank account"),
    'work': rx(r"my (?:boss|job|employer|co-?workers?|shift|manager at work)|i work (?:at|for|in)|my workplace"),
}
WORD = re.compile(r"\b[A-Z][a-z]+\b")      # capitalized words = name candidates

# words that look like first names but are mostly brands / places / other things here
NOT_NAMES = set("""
January February March April May June July August September October November December
Monday Tuesday Wednesday Thursday Friday Saturday Sunday Christmas Easter Thanksgiving Halloween
Google American German English French Italian Mexican Chinese Thai Indian Japanese Irish Canadian Royal
Vermont Alaska Alaskan Delaware Wyoming Rhode Island Michigan Montana France India Boston Maine Texas Florida
Carolina Virginia Jersey Montreal Adirondack Ark Mrs Indigo Jesus Mercedes Aspen Denali Newport
Amazon Walmart Subway Dunkin Costco Verizon Sunoco Shell Hannaford Lowes Kinney Wawa Applebee Arby Arbys
Wendy Wendys Carl Fred Meyer Dairy Queen Ben Jerry Ethan Allen Trapp Champlain Stowe Killington Okemo Jay Bolton
Laure Dutton Harley Ford Chevy Dodge Lincoln Tesla Subaru Honda Toyota
Original United Colorado Denver Christ Lexus Audi Volvo Kia Nissan Mazda Jeep African Macy Macys Denny Dennys Tita Valenti Walden
Tacoma San Porsche Chicago Hawaiian Vegas Cherokee Avalon Disney Dallas London Cadillac Asia Kansas Dakota Valentine Lyon
""".split())


def p(*a): return os.path.join(*a)

def read_jsonl(path):
    # encoding is explicit so it also works on Windows (default there is cp1252)
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f):
            yield i, line, json.loads(line)

# ---------------------------------------------------------------- step 1
def build_names(data, work):
    """First names = first word of reviewers' names (all states) that appear
    capitalized in texts and (almost) never in lowercase."""
    first, cap, low, places = collections.Counter(), collections.Counter(), collections.Counter(), set()
    wre = re.compile(r"[A-Za-z]+")
    for st in STATES:
        for _, _, d in read_jsonl(p(data, f'review-{st}.json')):
            if d.get('name'):
                t = d['name'].split()[0]
                if t.isalpha() and len(t) >= 3:
                    first[t.capitalize()] += 1
            if d.get('text'):
                for w in wre.findall(d['text']):
                    if w[0].isupper() and not w.isupper(): cap[w] += 1
                    elif w.islower(): low[w] += 1
        # city names from the place addresses ("..., Rutland, VT 05701") are not person names
        for _, _, d in read_jsonl(p(data, f'meta-{st}.json')):
            parts = (d.get('address') or '').split(',')
            if len(parts) >= 3:
                places.update(wre.findall(parts[-2]))
        print(f'  names: read {st}')
    names = {n for n, c in first.items()
             if c >= 15 and cap[n] >= 3 and low[n.lower()] <= 0.1 * cap[n]}
    names -= NOT_NAMES | places
    pickle.dump(names, open(p(work, 'names.pkl'), 'wb'))
    print(f'  {len(names)} first names kept')

# ---------------------------------------------------------------- step 2
def scan_state(st, data, work):
    """Flag every review of one state; keep a small summary of the eligible ones."""
    names = pickle.load(open(p(work, 'names.pkl'), 'rb')) - NOT_NAMES   # exclusions applied again here
    seen, rows, dup = set(), [], 0
    for i, _, d in read_jsonl(p(data, f'review-{st}.json')):
        key = (d['user_id'], d['gmap_id'], d['time'])
        if key in seen:                       # the raw files contain duplicate reviews
            dup += 1; continue
        seen.add(key)
        if d['rating'] is None or not d['text'] or not d['name']:
            continue
        t = d['text']
        hit = [c for c, r in CATS.items() if r.search(t)]
        if any(w in names for w in WORD.findall(t)):
            hit.append('names')
        if hit:
            # (state, line number, photos?, response?, #categories, text length, categories)
            rows.append((st, i, bool(d['pics']), bool(d['resp']), len(hit), len(t), '|'.join(sorted(hit))))
    pickle.dump(rows, open(p(work, f'rows-{st}.pkl'), 'wb'))
    print(f'  {st}: {len(rows)} eligible, {dup} duplicates skipped')

# ---------------------------------------------------------------- step 3
def select(data, work, n, require_response=True):
    rows = []
    for st in STATES:
        rows += pickle.load(open(p(work, f'rows-{st}.pkl'), 'rb'))
    if require_response:
        rows = [r for r in rows if r[3]]          # keep only reviews with an owner response
    # ranking: photos > number of sensitive categories > owner response > longer text
    # (Python compares the tuples element by element; later elements only break ties)
    rows.sort(key=lambda r: (r[2], r[4], r[3], r[5]), reverse=True)
    chosen = rows[:n]
    keep = collections.defaultdict(set)
    for r in chosen:
        keep[r[0]].add(r[1])
    out = p(data, f'review-5states-{n // 1000}k.json')
    with open(out, 'w', encoding='utf-8', newline='\n') as o:
        for st in STATES:
            for i, _, d in read_jsonl(p(data, f'review-{st}.json')):
                if i in keep[st]:
                    d['state'] = st.replace('_', ' ')          # the new field
                    o.write(json.dumps(d) + '\n')
    # short summary
    c = collections.Counter
    print(f'  eligible in all states: {len(rows)}  ->  written {len(chosen)} to {out}')
    print('  per state:', dict(c(r[0] for r in chosen)))
    print('  photos:', sum(r[2] for r in chosen), ' response:', sum(r[3] for r in chosen),
          ' photos+response:', sum(r[2] and r[3] for r in chosen))
    print('  #categories:', sorted(c(r[4] for r in chosen).items()))
    print('  categories:', c(x for r in chosen for x in r[6].split('|')).most_common())
    print('  last row taken (photos, response, #cat, len):', chosen[-1][2:6])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=['names', 'scan', 'select', 'all'])
    ap.add_argument('state', nargs='?')
    ap.add_argument('--data', default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--work')
    ap.add_argument('--n', type=int, default=50000)
    ap.add_argument('--allow-no-response', action='store_true')
    a = ap.parse_args()
    work = a.work or p(a.data, '_work')
    os.makedirs(work, exist_ok=True)
    if a.step in ('names', 'all'):
        build_names(a.data, work)
    if a.step == 'scan':
        scan_state(a.state, a.data, work)
    if a.step == 'all':
        for st in STATES:
            scan_state(st, a.data, work)
    if a.step in ('select', 'all'):
        select(a.data, work, a.n, require_response=not a.allow_no_response)
