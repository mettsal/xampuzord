#!/usr/bin/env python
"""Aplica classifications.json como tags (curto/longo + tema).

Por padrão é ENSAIO; --write grava. Idempotente (não duplica tag). Usa
process_tags() do app para manter Tag.count correto (post oculto não conta).
Tudo o que foi adicionado vai para o ledger (instance/classify_ledger.json), e
--revert desfaz só isso (decrement_tags), sem tocar nas tags manuais.
Faça backup antes (tools/db_backup.sh).

Uso: python tools/classify/apply_tags.py instance/classifications.json [--write|--revert]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def apply(classifications, ledger, write=False):
    """Núcleo testável: devolve {post_id: [tags novas]}; atualiza `ledger` se write."""
    from app import db, Post, process_tags
    added = {}
    for key, cls in classifications.items():
        post = db.session.get(Post, int(key))
        if not post:
            continue
        have = {str(t.get('value')).lower() for t in post.tags or []}
        new = [v for v in (cls.get('length'), cls.get('theme')) if v and v.lower() not in have]
        if not new:
            continue
        added[int(key)] = new
        if write:
            created = process_tags(', '.join(new), count=not post.hidden)
            post.tags = list(post.tags or []) + created  # reatribui: JSON não detecta mutação
            ledger.setdefault(str(key), [])
            ledger[str(key)] = sorted(set(ledger[str(key)]) | set(new))
    if write:
        db.session.commit()
    return added


def revert(ledger):
    from app import db, Post, decrement_tags
    n = 0
    for key, values in list(ledger.items()):
        post = db.session.get(Post, int(key))
        if post:
            gone = [t for t in post.tags or [] if t.get('value') in values]
            post.tags = [t for t in post.tags if t not in gone]
            if not post.hidden:
                decrement_tags(gone)
            n += len(gone)
        del ledger[key]
    db.session.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('classifications', nargs='?')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    ap.add_argument('--ledger', default=os.path.join(ROOT, 'instance', 'classify_ledger.json'))
    args = ap.parse_args()
    os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath(args.db)
    from app import app
    ledger = json.load(open(args.ledger)) if os.path.exists(args.ledger) else {}
    with app.app_context():
        if args.revert:
            print(f'{revert(ledger)} tags removidas')
        else:
            if not args.classifications:
                sys.exit('Informe classifications.json')
            cls = json.load(open(args.classifications, encoding='utf-8'))
            added = apply(cls, ledger, write=args.write)
            total = sum(map(len, added.values()))
            print(f'{total} tags em {len(added)} poemas' + ('' if args.write else ' (ensaio: use --write)'))
    if args.write or args.revert:
        with open(args.ledger, 'w') as fh:
            json.dump(ledger, fh, indent=1)


if __name__ == '__main__':
    main()
