#!/usr/bin/env python
"""
Migration: adiciona post.source_path e post.hidden (painel /admin/acervo) e
liga os posts já importados aos arquivos de poesia/ pelo conteúdo.

Run with: python tools/migrate_add_post_source.py [--db instance/xampuparaossos.db]
Idempotente: rodar de novo só religa posts que ainda estejam sem vínculo.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add_columns(db_path):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(post)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'source_path' not in columns:
            print("🔧 Adding 'source_path' column to 'post' table...")
            cursor.execute("ALTER TABLE post ADD COLUMN source_path VARCHAR(500)")
        if 'hidden' not in columns:
            print("🔧 Adding 'hidden' column to 'post' table...")
            cursor.execute("ALTER TABLE post ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT 0")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_post_source_path ON post (source_path)")
        conn.commit()
        print("✅ Columns OK")
    finally:
        conn.close()


def link_existing(db_path):
    os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.abspath(db_path)
    sys.path.insert(0, ROOT)
    from app import app, Post
    with app.app_context():
        import acervo
        poems, _notes = acervo.scan()
        linked = acervo.link_orphans(poems)
        orphans = Post.query.filter(Post.source_path.is_(None)).count()
        print(f"🔗 {linked} posts ligados ao arquivo de origem; {orphans} sem arquivo "
              f"(editor/seed ou texto editado no site)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    args = parser.parse_args()
    if not os.path.exists(args.db):
        print(f"❌ Database not found at {args.db}")
        sys.exit(1)
    add_columns(args.db)
    link_existing(args.db)
