#!/usr/bin/env python
"""Visão do corpus: histograma de linhas (p/ calibrar o corte curto/longo),
distribuição de tags e quantos caem em cada classe para um corte dado.

Uso: python tools/classify/report.py [--corpus instance/corpus.json] [--cutoff 40]
"""
import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from tools.classify.text import LONG_CUTOFF, length_class  # noqa: E402

BINS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 80, 120, 10**9]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default=os.path.join(ROOT, 'instance', 'corpus.json'))
    ap.add_argument('--cutoff', type=int, default=LONG_CUTOFF)
    args = ap.parse_args()
    rows = json.load(open(args.corpus, encoding='utf-8'))
    print(f'{len(rows)} poemas\n\nlinhas não vazias:')
    for lo, hi in zip(BINS, BINS[1:]):
        n = sum(lo < r['n_lines'] <= hi if lo else r['n_lines'] <= hi for r in rows)
        label = f'{lo + 1 if lo else 0}-{hi}' if hi < 10**9 else f'>{lo}'
        print(f'  {label:>8} {n:5d} {"#" * (n * 60 // max(len(rows), 1))}')
    print(f'\ncorte {args.cutoff}:', dict(Counter(
        length_class(r['n_lines'], r['tags'], args.cutoff) for r in rows)))
    tags = Counter(t['value'] for r in rows for t in r['tags'] if t.get('type') != 'year')
    print('\ntags (não-ano):', tags.most_common(30))


if __name__ == '__main__':
    main()
