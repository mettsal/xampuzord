#!/usr/bin/env python
"""Baixa os poemas públicos via GET /api/posts?page=N -> instance/corpus.json.

Só vê o que o site expõe (sem posts ocultos). Para o acervo completo, rode
export_corpus.py no servidor (mesmo formato).

Uso: python tools/classify/fetch_corpus.py [--base https://xampuparaossos.com.br]
"""
import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from tools.classify.text import stats  # noqa: E402


def row(post):
    s = stats(post['body_html'])
    return {
        'id': post['id'], 'slug': post.get('slug'), 'title': post['title'],
        'created_at': post['created_at'], 'tags': post.get('tags') or [],
        'hidden': False, **s,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='https://xampuparaossos.com.br')
    ap.add_argument('--out', default=os.path.join(ROOT, 'instance', 'corpus.json'))
    args = ap.parse_args()
    rows, page = {}, 1
    while True:
        req = urllib.request.Request(f'{args.base}/api/posts?page={page}',
                                     headers={'User-Agent': 'xampu-classify/1'})
        with urllib.request.urlopen(req, timeout=30) as res:
            batch = json.load(res)
        if not batch:
            break
        for post in batch:
            rows[post['id']] = row(post)
        print(f'página {page}: {len(rows)} poemas', file=sys.stderr)
        page += 1
        time.sleep(0.3)  # gentileza (o limiter só cobre rotas de escrita)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(sorted(rows.values(), key=lambda r: r['id']), fh, ensure_ascii=False, indent=1)
    print(f'{len(rows)} poemas -> {args.out}')


if __name__ == '__main__':
    main()
