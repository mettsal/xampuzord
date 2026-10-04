#!/usr/bin/env python
"""Exporta TODOS os posts (inclusive ocultos) do banco -> instance/corpus.json.
Rode no servidor. Mesmo formato do fetch_corpus.py.

Uso: python tools/classify/export_corpus.py [--db instance/xampuparaossos.db]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'instance', 'corpus.json'))
    args = ap.parse_args()
    os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath(args.db)
    from app import app, Post
    from tools.classify.text import stats
    with app.app_context():
        rows = [{
            'id': p.id, 'slug': p.slug, 'title': p.title,
            'created_at': p.created_at.isoformat(), 'tags': p.tags or [],
            'hidden': bool(p.hidden), 'source_path': p.source_path,
            **stats(p.body_html),
        } for p in Post.query.order_by(Post.id)]
    with open(args.out, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1)
    print(f'{len(rows)} poemas -> {args.out}')


if __name__ == '__main__':
    main()
