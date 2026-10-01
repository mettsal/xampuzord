#!/usr/bin/env python
"""
Migration script to add the gallery_item table to existing databases.
Run with: python tools/migrate_add_gallery.py
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
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gallery_item'")
        if cursor.fetchone():
            print("✅ Table 'gallery_item' already exists. No migration needed.")
            return

        print("🔧 Creating 'gallery_item' table...")
        cursor.execute("""
            CREATE TABLE gallery_item (
                id INTEGER NOT NULL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                image_path VARCHAR(200) NOT NULL,
                caption TEXT,
                author_id INTEGER NOT NULL,
                created_at DATETIME,
                FOREIGN KEY(author_id) REFERENCES user (id)
            )
        """)

        conn.commit()
        print("✅ Migration completed successfully!")

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
