-- Create telegram_cache table for video caching
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS telegram_cache (
  id BIGSERIAL PRIMARY KEY,
  drama_id BIGINT NOT NULL,
  episode INTEGER NOT NULL,
  file_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(drama_id, episode)
);

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_telegram_cache_drama_episode
ON telegram_cache(drama_id, episode);

-- Add comment
COMMENT ON TABLE telegram_cache IS 'Cache for Telegram file_ids to optimize video streaming';