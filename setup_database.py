#!/usr/bin/env python3
"""
Database Setup Script
Creates missing tables and updates existing ones for the Drama Bot
"""

import os
import sys
from datetime import datetime, timezone
from supabase import create_client, Client

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.db import get_supabase_client
    supabase = get_supabase_client()
except ImportError:
    # Fallback if config import fails
    from bot_services.config import SUPABASE_URL, SUPABASE_KEY
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def create_telegram_cache_table():
    """Create telegram_cache table for video caching"""
    try:
        # Check if table exists
        result = supabase.table('telegram_cache').select('id').limit(1).execute()
        print("✅ telegram_cache table already exists")
        return True
    except Exception:
        print("📝 Creating telegram_cache table...")

    # Create table using raw SQL (since Supabase Python client doesn't support DDL)
    # We'll need to run this manually or through Supabase dashboard
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS telegram_cache (
      id BIGSERIAL PRIMARY KEY,
      drama_id BIGINT NOT NULL,
      episode INTEGER NOT NULL,
      file_id VARCHAR(255) NOT NULL,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      UNIQUE(drama_id, episode)
    );
    """

    print("⚠️  Please run this SQL in your Supabase SQL Editor:")
    print(create_table_sql)
    return False

def update_users_table():
    """Add missing columns to users table"""
    print("📝 Checking users table columns...")

    # Check if columns exist by trying to select them
    try:
        result = supabase.table('users').select('free_watches_used, free_watches_limit, reset_time').limit(1).execute()
        print("✅ All required columns exist in users table")
        return True
    except Exception as e:
        print(f"⚠️  Missing columns detected: {e}")

    # Add columns using raw SQL
    alter_table_sql = """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS free_watches_used INTEGER DEFAULT 0;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS free_watches_limit INTEGER DEFAULT 1;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_time TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    """

    print("⚠️  Please run this SQL in your Supabase SQL Editor:")
    print(alter_table_sql)
    return False

def create_sample_data():
    """Create sample data for testing"""
    print("📝 Creating sample data...")

    try:
        # Check if we have any users
        result = supabase.table('users').select('id').limit(1).execute()
        if result.data:
            print("✅ Users table has data")
        else:
            print("📝 Users table is empty - you can add users through the bot")

        # Check telegram_cache
        result = supabase.table('telegram_cache').select('id').limit(1).execute()
        if result.data:
            print("✅ telegram_cache table has data")
        else:
            print("📝 telegram_cache table is empty - will be populated when videos are sent")

    except Exception as e:
        print(f"⚠️  Error checking sample data: {e}")

def main():
    """Main setup function"""
    print("🚀 Starting Database Setup for Drama Bot")
    print("=" * 50)

    if not supabase:
        print("❌ Failed to connect to Supabase. Please check your credentials.")
        return

    print("✅ Connected to Supabase successfully")

    # Create tables
    cache_created = create_telegram_cache_table()
    users_updated = update_users_table()

    # Create sample data
    create_sample_data()

    print("\n" + "=" * 50)
    if cache_created and users_updated:
        print("✅ Database setup completed successfully!")
        print("🎬 Your bot should now work with video caching.")
    else:
        print("⚠️  Manual SQL execution required. Please run the SQL commands shown above in your Supabase dashboard.")
        print("🔄 After running the SQL, restart your bot.")

if __name__ == "__main__":
    main()