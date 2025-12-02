-- =====================================================================================
-- TABEL EPISODES - DRAMA BOT
-- =====================================================================================
-- Deskripsi: Menyimpan data episode dari setiap drama
--            Setiap drama bisa memiliki banyak episode
--
-- Created: December 2, 2025
-- =====================================================================================

CREATE TABLE IF NOT EXISTS episodes (
  id BIGSERIAL PRIMARY KEY,
  drama_id BIGINT NOT NULL,
  episode_number INTEGER NOT NULL,
  title VARCHAR(500),
  duration INTEGER,
  s3_key TEXT,
  s3_url TEXT,
  video_quality VARCHAR(50) DEFAULT '720p',
  file_size BIGINT,
  is_downloaded BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(drama_id, episode_number),
  FOREIGN KEY (drama_id) REFERENCES "Drama"(id) ON DELETE CASCADE
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_episodes_drama_id ON episodes(drama_id);
CREATE INDEX IF NOT EXISTS idx_episodes_drama_episode ON episodes(drama_id, episode_number);
CREATE INDEX IF NOT EXISTS idx_episodes_is_downloaded ON episodes(is_downloaded);
CREATE INDEX IF NOT EXISTS idx_episodes_created_at ON episodes(created_at DESC);

-- Comments dokumentasi
COMMENT ON TABLE episodes IS 'Tabel untuk menyimpan data episode dari setiap drama';
COMMENT ON COLUMN episodes.drama_id IS 'ID drama dari tabel Drama (Foreign Key)';
COMMENT ON COLUMN episodes.episode_number IS 'Nomor episode (1, 2, 3, dst)';
COMMENT ON COLUMN episodes.title IS 'Judul episode (opsional)';
COMMENT ON COLUMN episodes.duration IS 'Durasi video dalam detik';
COMMENT ON COLUMN episodes.s3_key IS 'Key/path file di S3 storage (format: drama_id/episode_X/filename.mp4)';
COMMENT ON COLUMN episodes.s3_url IS 'URL lengkap untuk akses file di S3';
COMMENT ON COLUMN episodes.video_quality IS 'Kualitas video (720p, 1080p, dll)';
COMMENT ON COLUMN episodes.file_size IS 'Ukuran file dalam bytes';
COMMENT ON COLUMN episodes.is_downloaded IS 'Status apakah episode sudah didownload dan diupload ke S3';
COMMENT ON COLUMN episodes.created_at IS 'Waktu episode ditambahkan';
COMMENT ON COLUMN episodes.updated_at IS 'Waktu terakhir episode diupdate';

-- =====================================================================================
-- QUERY CONTOH PENGGUNAAN
-- =====================================================================================

-- 1. Insert episode baru
-- INSERT INTO episodes (drama_id, episode_number, s3_key, is_downloaded)
-- VALUES (42000000035, 1, '42000000035/episode_1/episode_1.mp4', true);

-- 2. Get semua episode dari drama tertentu
-- SELECT * FROM episodes WHERE drama_id = 42000000035 ORDER BY episode_number;

-- 3. Get total episode per drama
-- SELECT drama_id, COUNT(*) as total_episodes 
-- FROM episodes 
-- GROUP BY drama_id;

-- 4. Get episode yang belum didownload
-- SELECT * FROM episodes WHERE is_downloaded = false;

-- 5. Update status download episode
-- UPDATE episodes 
-- SET is_downloaded = true, s3_url = 'https://...' 
-- WHERE drama_id = 42000000035 AND episode_number = 1;

-- =====================================================================================
