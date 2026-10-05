"""Inventory of six unfiltered Trending lists; languages are metadata, not scope."""
import csv
from pathlib import Path

P = Path(__file__).parent


def targets(languages=None, spoken=None, full_cross=False):
    # Retained arguments let old callers run, but never expand language filters.
    for kind in ('repositories', 'developers'):
        root = 'https://github.com/trending' + ('/developers' if kind == 'developers' else '')
        for window in ('daily', 'weekly', 'monthly'):
            yield {'kind': kind, 'language': 'any', 'spoken_language': 'any',
                   'window': window, 'url': root + '?since=' + window, 'tested': False}


def main():
    rows = list(targets())
    with (P / 'github-scope-matrix.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(len(rows), P / 'github-scope-matrix.csv')


if __name__ == '__main__':
    main()
