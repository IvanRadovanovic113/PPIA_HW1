"""
anonymize_v1.py - first anonymized version of the Vermont Google reviews (PPIA Homework 1)

Input : raw_data/review-Vermont.json, raw_data/meta-Vermont.json   (JSON lines)
Output: review-Vermont-anon-v1.json   (JSON lines, one review per line, next to this script)

What happens to each review (in order of the team's plan):
 1. user_id and name are removed                       (direct identifiers)
 2. time (Unix ms, UTC) -> "date" YYYY-MM-DD and "time" HH:MM in Vermont local time
 3. rating is kept as it is (can be null)
 4. text is removed -> comment_length = number of characters (0 if no text)
 5. pics are removed -> pics_num = number of pictures (0 if none)
 6. resp is removed -> has_resp (bool), resp_length (chars), resp_delay_hours
    (hours between review and response; null if there is no response or if the
     response is dated before the review, which happens when a review was edited later)
 7. gmap_id is kept; "category" (list) is looked up in meta-Vermont.json
 8. spent = random but realistic amount in USD (see SPEND_PROFILES below)
 9. state = "Vermont"
Exact duplicate reviews (same user, place and time) in the raw file are written only once.

Run:  python anonymize_v1.py            (optional: --data DIR --out FILE --seed 42)
Note: the rows keep the order of the raw file, which is grouped by place (gmap_id).
"""
import argparse
import json
import math
import os
import random
import re
from datetime import datetime, timedelta, timezone

# ------------------------------------------------------------------ time zone
# Vermont = US Eastern time. zoneinfo needs time zone data, which Windows may not have
# (pip install tzdata), so there is a fallback that applies the US daylight-saving rules.
try:
    from zoneinfo import ZoneInfo
    VT = ZoneInfo('America/New_York')
except Exception:
    VT = None

def _nth_sunday(year, month, n):          # n-th Sunday of a month (n=-1 -> last)
    if n > 0:
        d = datetime(year, month, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = datetime(year, month + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)

def to_vermont(ms):
    utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    if VT is not None:
        return utc.astimezone(VT)
    # fallback: EST = UTC-5, EDT = UTC-4; DST rules changed in 2007
    y = utc.year
    if y >= 2007:
        start, end = _nth_sunday(y, 3, 2), _nth_sunday(y, 11, 1)
    else:
        start, end = _nth_sunday(y, 4, 1), _nth_sunday(y, 10, -1)
    local_std = utc.replace(tzinfo=None) - timedelta(hours=5)
    dst = start + timedelta(hours=2) <= local_std < end + timedelta(hours=1)
    return local_std + timedelta(hours=1) if dst else local_std

# ------------------------------------------------------------------ spending model
# Each profile: (keywords, mixture). A place gets the FIRST profile whose keyword appears
# in any of its categories, so specific profiles come first. Keywords match WHOLE words
# (optionally plural), so "inn" does not match "dinner" and "tire" not "retirement";
# a keyword ending in * is a word stem ("veterinar*" -> veterinarian, veterinary).
# mixture = list of (probability, median USD, spread). The amount is drawn from a
# log-normal distribution: median * exp(N(0, spread)) -> always positive, right-skewed,
# like real spending.  median 0 = free place (park, church, ATM...).
SPEND_PROFILES = [
    (['car dealer', 'truck dealer', 'motorcycle dealer', 'rv dealer', 'boat dealer'],
                                                          [(0.35, 22000, 0.5), (0.65, 350, 0.9)]),  # purchase vs service
    (['real estate'],                                     [(1.0, 5000, 1.0)]),
    (['ski resort'],                                      [(1.0, 120, 0.5)]),
    (['hotel', 'motel', 'inn', 'bed & breakfast', 'lodge', 'lodging', 'resort', 'cottage', 'vacation'],
                                                          [(1.0, 250, 0.6)]),
    (['campground', 'rv park'],                           [(1.0, 40, 0.5)]),
    (['electrician', 'plumber', 'hvac', 'roofing', 'contractor', 'builder', 'landscap*', 'excavat*',
      'septic', 'moving', 'security system', 'propane', 'heating oil', 'fuel supplier', 'painter'],
                                                          [(1.0, 900, 1.0)]),
    (['attorney', 'lawyer', 'accountant', 'tax'],        [(1.0, 800, 0.8)]),
    (['insurance'],                                       [(1.0, 1200, 0.6)]),
    (['dentist', 'dental', 'orthodont*'],                  [(1.0, 250, 0.7)]),
    (['veterinar*', 'animal hospital'],                    [(1.0, 200, 0.7)]),
    (['doctor', 'physician', 'medical', 'hospital', 'urgent care', 'chiropract*', 'physical therap*',
      'optometrist', 'clinic'],                           [(1.0, 150, 0.8)]),
    (['pharmacy', 'drug store'],                          [(1.0, 25, 0.7)]),
    (['tattoo'],                                          [(1.0, 200, 0.6)]),
    (['barber'],                                          [(1.0, 25, 0.3)]),
    (['hair salon', 'nail salon', 'beauty salon', 'spa', 'massage'],
                                                          [(1.0, 60, 0.5)]),
    (['oil change', 'car wash'],                          [(1.0, 50, 0.4)]),
    (['auto repair', 'mechanic', 'tire', 'brake', 'body shop', 'car repair', 'transmission', 'towing',
      'wheel alignment', 'muffler'],                      [(1.0, 350, 0.9)]),
    (['furniture', 'appliance', 'electronics', 'jewelry', 'mattress', 'cell phone'],
                                                          [(1.0, 350, 0.9)]),
    (['grocery', 'supermarket', 'food co-op'],            [(1.0, 70, 0.6)]),
    (['gas station', 'convenience store'],                [(1.0, 25, 0.6)]),
    (['liquor', 'wine store', 'beer store'],              [(1.0, 35, 0.6)]),
    (['fast food', 'pizza', 'sandwich', 'deli', 'bakery', 'donut', 'bagel', 'coffee', 'cafe',
      'ice cream', 'takeout', 'hamburger', 'hot dog', 'food truck'],
                                                          [(1.0, 14, 0.5)]),
    (['restaurant', 'bar', 'pub', 'brewery', 'winery', 'distillery', 'diner', 'grill', 'caterer'],
                                                          [(1.0, 45, 0.5)]),
    # after restaurants: a restaurant that also hosts weddings is mostly reviewed by diners
    (['wedding venue'],                                   [(1.0, 8000, 0.6)]),
    (['farm', 'orchard', 'maple', 'sugar shack'],         [(1.0, 25, 0.6)]),
    (['hardware', 'home improvement', 'garden center', 'auto parts', 'paint store', 'tool store',
      'lumber'],                                          [(1.0, 60, 0.8)]),
    (['car rental', 'truck rental', 'van rental', 'trailer rental'],
                                                          [(1.0, 150, 0.6)]),
    (['golf', 'bowling', 'movie theater', 'cinema', 'amusement', 'gym', 'fitness', 'theater',
      'live music venue', 'auditorium', 'skating rink', 'country club'],
                                                          [(1.0, 40, 0.5)]),
    (['museum', 'zoo', 'event venue', 'tour'],            [(1.0, 25, 0.7)]),
    (['steak house'],                                     [(1.0, 60, 0.5)]),
    (['store', 'shop', 'boutique', 'outlet', 'market', 'shopping mall', 'florist'],   [(1.0, 45, 0.8)]),
    (['park', 'hiking', 'trail', 'lake', 'river', 'mountain peak', 'bridge', 'waterfall', 'beach',
      'scenic', 'landmark', 'monument', 'church', 'place of worship', 'cemetery', 'library',
      'post office', 'city hall', 'government', 'school', 'playground', 'atm', 'bank',
      'credit union', 'non-profit', 'tourist attraction', 'social services', 'veterans',
      'community center', 'senior citizen center', 'bus stop', 'transit station', 'boat ramp',
      'rest stop', 'tourist information', 'visitor center', 'fire station', 'police', 'bay',
      'mountain pass', 'recycling center', 'animal shelter', 'corporate office', 'manufacturer',
      'warehouse', 'kingdom hall', 'wildlife refuge', 'nature preserve'],
                                                          [(1.0, 0, 0)]),
]
DEFAULT_PROFILE = [(1.0, 40, 1.0)]
# price level from the meta file scales the amount (only ~15% of places have one;
# a few Vermont places use the won sign, treated the same way)
PRICE_FACTOR = {1: 0.7, 2: 1.0, 3: 1.8, 4: 3.0}

def _pattern(keywords):
    parts = [re.escape(k[:-1]) if k.endswith('*') else re.escape(k) + r'(?:s|es)?\b' for k in keywords]
    return re.compile(r'\b(?:' + '|'.join(parts) + ')', re.I)

PROFILE_PATTERNS = [(_pattern(k), m) for k, m in SPEND_PROFILES]

def spend_profile(categories):
    text = ' ; '.join(categories or [])
    for pattern, mixture in PROFILE_PATTERNS:
        if pattern.search(text):
            return mixture
    return DEFAULT_PROFILE

def draw_spent(mixture, price, rng):
    r, acc = rng.random(), 0.0
    for prob, median, spread in mixture:
        acc += prob
        if r <= acc:
            break
    if median == 0:
        return 0.0
    amount = median * math.exp(rng.gauss(0, spread)) * PRICE_FACTOR.get(price, 1.0)
    return round(max(amount, 1.0), 2)

# ------------------------------------------------------------------ main
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=os.path.join(here, 'raw_data'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--seed', type=int, default=42)   # same seed -> same "spent" values
    a = ap.parse_args()
    out = a.out or os.path.join(here, 'review-Vermont-anon-v1.json')
    rng = random.Random(a.seed)

    # gmap_id -> (categories, price level). The meta file has a few duplicate places: keep the first.
    places = {}
    with open(os.path.join(a.data, 'meta-Vermont.json'), encoding='utf-8') as f:
        for line in f:
            m = json.loads(line)
            if m['gmap_id'] not in places:
                price = len(m['price']) if m.get('price') else None   # "$$" -> 2
                places[m['gmap_id']] = (m.get('category'), price)

    seen = set()
    stats = dict(read=0, written=0, duplicates=0, negative_delay=0, no_meta=0)
    with open(os.path.join(a.data, 'review-Vermont.json'), encoding='utf-8') as f, \
         open(out, 'w', encoding='utf-8', newline='\n') as o:
        for line in f:
            d = json.loads(line)
            stats['read'] += 1
            key = (d['user_id'], d['gmap_id'], d['time'])
            if key in seen:
                stats['duplicates'] += 1
                continue
            seen.add(key)

            local = to_vermont(d['time'])
            resp = d.get('resp')
            delay = None
            if resp and resp.get('time') is not None:
                delay = round((resp['time'] - d['time']) / 3_600_000, 2)    # ms -> hours
                if delay < 0:
                    stats['negative_delay'] += 1
                    delay = None
            categories, price = places.get(d['gmap_id'], (None, None))
            if d['gmap_id'] not in places:
                stats['no_meta'] += 1

            row = {
                'date': local.strftime('%Y-%m-%d'),
                'time': local.strftime('%H:%M'),
                'rating': d['rating'],
                'comment_length': len(d['text']) if d.get('text') else 0,
                'pics_num': len(d['pics']) if d.get('pics') else 0,
                'has_resp': bool(resp),
                'resp_length': len(resp['text']) if resp and resp.get('text') else None,
                'resp_delay_hours': delay,
                'gmap_id': d['gmap_id'],
                'category': categories,
                'spent': draw_spent(spend_profile(categories), price, rng),
                'state': 'Vermont',
            }
            o.write(json.dumps(row, ensure_ascii=False) + '\n')
            stats['written'] += 1
    print(stats)
    print('output:', out)

if __name__ == '__main__':
    main()
