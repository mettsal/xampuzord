#!/usr/bin/env python
"""
Migration: URLs com título (/post/<slug>) — adiciona post.slug, a tabela
post_slug_alias (slugs antigos de títulos editados) e gera o slug de todos os
posts existentes, em ordem de id (o mais antigo fica com o slug "limpo";
títulos repetidos ganham -2, -3…; título sem letras vira poema-<id>).

Run with: python tools/migrate_add_post_slug.py [--db instance/xampuparaossos.db]
Idempotente: rodar de novo só preenche posts ainda sem slug.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add_schema(db_path):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(post)")
        if 'slug' not in [column[1] for column in cursor.fetchall()]:
            print("🔧 Adding 'slug' column to 'post' table...")
            cursor.execute("ALTER TABLE post ADD COLUMN slug VARCHAR(80)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_post_slug ON post (slug)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_slug_alias (
                id INTEGER NOT NULL PRIMARY KEY,
                slug VARCHAR(80) NOT NULL UNIQUE,
                post_id INTEGER NOT NULL,
                FOREIGN KEY(post_id) REFERENCES post (id)
            )
        """)
        conn.commit()
        print("✅ Schema OK")
    finally:
        conn.close()


def backfill(db_path):
    os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath(db_path)
    sys.path.insert(0, ROOT)
    from app import app, db, Post, slug_base, slugify, _unique_slug
    with app.app_context():
        taken = set()
        posts = Post.query.filter(Post.slug.is_(None)).order_by(Post.id).all()
        for post in posts:
            post.slug = _unique_slug(db.session, slug_base(post.title, post.id), post.id, taken)
            taken.add(post.slug)
        db.session.commit()
        by_id = sum(1 for p in posts if not slugify(p.title))
        repeated = sum(1 for p in posts if slugify(p.title) and p.slug != slugify(p.title))
        print(f"🔗 {len(posts)} posts ganharam slug ({by_id} sem letras no título -> poema-<id>; "
              f"{repeated} com sufixo -N por título repetido)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    args = parser.parse_args()
    if not os.path.exists(args.db):
        print(f"❌ Database not found at {args.db}")
        sys.exit(1)
    add_schema(args.db)
    backfill(args.db)
