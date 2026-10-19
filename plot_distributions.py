"""
plot_distributions.py - figures for "The data" section of the report (PPIA Homework 1)

Reads the ORIGINAL Vermont data (raw_data/review-Vermont.json + meta-Vermont.json,
exact duplicates removed the same way as anonymize_v1.py) and the synthetic `spent`
column from review-Vermont-anon-v1.json(.gz), and saves one PNG per distribution
into figures/:

  01_ratings.png            star ratings
  02_reviews_per_year.png   reviews written per year
  03_reviews_per_user.png   how many reviews each user wrote
  04_reviews_per_place.png  how many reviews each place received
  05_text_length.png        length of the review text
  06_top_categories.png     most reviewed types of places (first category)
  07_spent.png              synthetic amount spent (log scale)

Run:  python plot_distributions.py        (needs matplotlib)
"""
import collections
import gzip
import json
import os
from datetime import datetime, timezone

import matplotlib
matplotlib.use('Agg')                      # no window, just files
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw_data')
OUT = os.path.join(HERE, 'figures')

# one colour for every chart (each chart shows a single series), quiet text and grid
BLUE, INK, INK2, GRID, SURFACE = '#2a78d6', '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'axes.edgecolor': GRID, 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
    'text.color': INK, 'font.size': 10, 'axes.titlesize': 12, 'axes.titleweight': 'bold',
    'axes.titlelocation': 'left', 'axes.spines.top': False, 'axes.spines.right': False,
})


# ------------------------------------------------------------------ loading
def load_meta():
    """gmap_id -> list of categories (first entry wins for duplicated places)."""
    meta = {}
    with open(os.path.join(RAW, 'meta-Vermont.json'), encoding='utf-8') as f:
        for line in f:
            m = json.loads(line)
            meta.setdefault(m['gmap_id'], m.get('category') or [])
    return meta

def load_reviews():
    """Collect the counters we plot, skipping exact duplicates (same user, place, time)."""
    c = dict(ratings=collections.Counter(), years=collections.Counter(),
             users=collections.Counter(), places=collections.Counter(),
             text=collections.Counter())
    seen = set()
    with open(os.path.join(RAW, 'review-Vermont.json'), encoding='utf-8') as f:
        for line in f:
            d = json.loads(line)
            key = (d['user_id'], d['gmap_id'], d['time'])
            if key in seen:
                continue
            seen.add(key)
            c['ratings'][d['rating']] += 1
            c['years'][datetime.fromtimestamp(d['time'] / 1000, tz=timezone.utc).year] += 1
            c['users'][d['user_id']] += 1
            c['places'][d['gmap_id']] += 1
            n = len(d['text']) if d.get('text') else 0
            c['text']['no text' if n == 0 else '< 50' if n < 50 else '50-500' if n <= 500 else '> 500'] += 1
    return c

def load_spent():
    """The synthetic `spent` values from v1 (plain JSON if present, else the .gz)."""
    path = os.path.join(HERE, 'review-Vermont-anon-v1.json')
    opener = open if os.path.exists(path) else gzip.open
    path = path if os.path.exists(path) else path + '.gz'
    with opener(path, 'rt', encoding='utf-8') as f:
        return [json.loads(line)['spent'] for line in f]


# ------------------------------------------------------------------ helpers
def bucket(counter_values, edges, labels):
    """Count how many values fall into each [edge_i, edge_i+1) bucket."""
    out = collections.Counter()
    for v in counter_values:
        for lo, hi, lab in zip(edges, edges[1:] + [float('inf')], labels):
            if lo <= v < hi:
                out[lab] += 1
                break
    return [out[l] for l in labels]

def bar_chart(filename, title, labels, values, xlabel, ylabel='share (%)', note=None,
              horizontal=False, total=None):
    """Single-series bar chart with percentage labels on the bars.
    total = denominator for the percentages (default: the sum of the values shown)."""
    total = total or sum(values)
    pct = [100 * v / total for v in values]
    fig, ax = plt.subplots(figsize=(7, 4.2 if not horizontal else 5.2))
    if horizontal:
        bars = ax.barh(labels[::-1], pct[::-1], color=BLUE, height=0.7, edgecolor=SURFACE, linewidth=2)
        ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
        ax.set_xlabel(ylabel)
        for b, p in zip(bars, pct[::-1]):
            ax.text(b.get_width() + max(pct) * 0.01, b.get_y() + b.get_height() / 2,
                    f'{p:.1f}%', va='center', fontsize=8.5, color=INK2)
    else:
        bars = ax.bar(labels, pct, color=BLUE, width=0.75, edgecolor=SURFACE, linewidth=2)
        ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        for b, p in zip(bars, pct):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + max(pct) * 0.01,
                    f'{p:.1f}%' if p >= 0.1 else '<0.1%', ha='center', va='bottom', fontsize=8.5, color=INK2)
    ax.set_title(title, pad=12)
    if note:
        fig.text(0.01, 0.01, note, fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03 if note else 0, 1, 1))
    fig.savefig(os.path.join(OUT, filename), dpi=200)
    plt.close(fig)
    print('saved', filename)


# ------------------------------------------------------------------ charts
def main():
    os.makedirs(OUT, exist_ok=True)
    meta = load_meta()
    c = load_reviews()
    n = sum(c['ratings'].values())
    print(f'{n} reviews, {len(c["users"])} users, {len(c["places"])} places')

    r = c['ratings']
    bar_chart('01_ratings.png', 'Star ratings', ['1', '2', '3', '4', '5', 'none'],
              [r[1], r[2], r[3], r[4], r[5], r[None]], 'stars')

    years = sorted(y for y in c['years'] if y >= 2010)
    early = sum(v for y, v in c['years'].items() if y < 2010)
    bar_chart('02_reviews_per_year.png', 'Reviews per year', [str(y) for y in years],
              [c['years'][y] for y in years], 'year',
              note=f'{early} reviews written before 2010 are not shown; 2021 covers January-September only.')

    labels = ['1', '2', '3-5', '6-10', '11-20', '21-50', '> 50']
    bar_chart('03_reviews_per_user.png', 'Number of reviews written per user', labels,
              bucket(c['users'].values(), [1, 2, 3, 6, 11, 21, 51], labels),
              'reviews written in Vermont', ylabel='share of users (%)')

    labels = ['1-4', '5-9', '10-19', '20-49', '50-99', '100-499', '500+']
    bar_chart('04_reviews_per_place.png', 'Number of reviews received per place', labels,
              bucket(c['places'].values(), [1, 5, 10, 20, 50, 100, 500], labels),
              'reviews received', ylabel='share of places (%)')

    t = c['text']
    labels = ['no text', '< 50', '50-500', '> 500']
    bar_chart('05_text_length.png', 'Length of the review text', labels, [t[l] for l in labels],
              'characters', ylabel='share of reviews (%)')

    first = collections.Counter()
    for g, k in c['places'].items():
        first[(meta.get(g) or ['(no category)'])[0]] += k
    top = first.most_common(15)
    bar_chart('06_top_categories.png', 'Most reviewed types of places (top 15, first category)',
              [k for k, _ in top], [v for _, v in top], '', ylabel='share of all reviews (%)',
              horizontal=True, total=n)        # % of ALL reviews, not of the top 15

    spent = load_spent()
    zero = sum(1 for s in spent if s == 0)
    pos = [s for s in spent if s > 0]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    edges = [10 ** (i / 10) for i in range(0, 52)]          # 1 $ .. ~126,000 $, log-spaced
    ax.hist(pos, bins=edges, color=BLUE, edgecolor=SURFACE, linewidth=0.6,
            weights=[100 / len(spent)] * len(pos))
    ax.set_xscale('log')
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.yaxis.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    ax.set_xlabel('amount spent (log scale)'); ax.set_ylabel('share of reviews (%)')
    ax.set_title('Amount spent per visit (synthetic)', pad=12)
    med = sorted(spent)[len(spent) // 2]
    ax.axvline(med, color=INK2, linewidth=1, linestyle='--')
    ax.text(med * 1.6, ax.get_ylim()[1] * 0.97, f'median ${med:,.0f}', fontsize=8.5, color=INK2, va='top',
            bbox=dict(facecolor=SURFACE, edgecolor='none', pad=2))
    fig.text(0.01, 0.01, f'{100 * zero / len(spent):.1f}% of reviews have $0 (free places) and are not shown.',
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(OUT, '07_spent.png'), dpi=200)
    plt.close(fig)
    print('saved 07_spent.png')

if __name__ == '__main__':
    main()
