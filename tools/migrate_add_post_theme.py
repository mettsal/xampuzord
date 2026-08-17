#!/usr/bin/env python
"""
Migration script to add post_theme column to existing database
Run with: python migrate_add_post_theme.py
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

        if 'post_theme' in columns:
            print("✅ Column 'post_theme' already exists. No migration needed.")
            return

        # Add the new column
        print("🔧 Adding 'post_theme' column to 'post' table...")
        cursor.execute("""
            ALTER TABLE post
            ADD COLUMN post_theme VARCHAR(50) DEFAULT 'inherit'
        """)

        # Update existing posts to use 'inherit'
        cursor.execute("""
            UPDATE post
            SET post_theme = 'inherit'
            WHERE post_theme IS NULL
        """)

        conn.commit()
        print("✅ Migration completed successfully!")
        print("ℹ️  All existing posts now have post_theme='inherit'")

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
