#!/usr/bin/env python
"""
Migration script to add body_md column (Markdown source) to existing database
Run with: python tools/migrate_add_post_body_md.py
"""
import sqlite3
import os

DB_PATH = 'instance/xampuparaossos.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        print("ℹ️  Run 'flask init-db' first to create the database")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(post)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'body_md' in columns:
            print("✅ Column 'body_md' already exists. No migration needed.")
            return

        # Add the new column. NULL para posts existentes: o editor cai no
        # fallback body_html até o post ser re-salvo com fonte Markdown.
        print("🔧 Adding 'body_md' column to 'post' table...")
        cursor.execute("""
            ALTER TABLE post
            ADD COLUMN body_md TEXT
        """)

        conn.commit()
        print("✅ Migration completed successfully!")
        print("ℹ️  Existing posts keep body_md=NULL (editor falls back to body_html)")

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
