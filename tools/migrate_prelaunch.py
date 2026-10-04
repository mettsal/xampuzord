#!/usr/bin/env python
"""
Migration (pré-lançamento): user.is_banned (bloquear pelo painel admin) e a
tabela site_setting (interruptores: cadastro, comentários, depoimentos).

Run with: python tools/migrate_prelaunch.py [--db instance/xampuparaossos.db]
Idempotente.
"""
import argparse
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(user)")
        if 'is_banned' not in [column[1] for column in cursor.fetchall()]:
            print("🔧 Adding 'is_banned' column to 'user' table...")
            cursor.execute("ALTER TABLE user ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT 0")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS site_setting (
                "key" VARCHAR(50) NOT NULL PRIMARY KEY,
                value VARCHAR(200) NOT NULL
            )
        """)
        conn.commit()
        print("✅ Migration completed successfully!")
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.path.join(ROOT, 'instance', 'xampuparaossos.db'))
    args = parser.parse_args()
    if not os.path.exists(args.db):
        print(f"❌ Database not found at {args.db}")
        sys.exit(1)
    migrate(args.db)
