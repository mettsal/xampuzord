#!/usr/bin/env python
"""
Migration: adiciona post.pinned (poemas fixados no topo da home, via /admin).

Run with: python tools/migrate_add_post_pinned.py [--db instance/xampuparaossos.db]
Idempotente.
"""
import argparse
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(post)")
        if 'pinned' in [column[1] for column in cursor.fetchall()]:
            print("✅ 'pinned' already exists")
            return
        print("🔧 Adding 'pinned' column to 'post' table...")
        cursor.execute("ALTER TABLE post ADD COLUMN pinned BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
        print("✅ Done")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
