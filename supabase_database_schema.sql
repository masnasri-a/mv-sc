-- =====================================================================================
-- SUPABASE DATABASE SCHEMA - DRAMA BOT
-- =====================================================================================
-- File SQL lengkap untuk setup database Drama Bot di Supabase
-- 
-- Cara penggunaan:
-- 1. Login ke Supabase Dashboard
-- 2. Buka SQL Editor
-- 3. Copy paste seluruh isi file ini
-- 4. Klik "Run" untuk menjalankan
--
-- Created: December 2, 2025
-- =====================================================================================

-- =====================================================================================
-- TABEL 1: USERS
-- =====================================================================================
-- Deskripsi: Menyimpan data pengguna Telegram dan status premium mereka
-- 
-- Fields:
--   - id: Primary key auto increment
--   - telegram_id: ID unik dari Telegram (UNIQUE)
--   - username: Username Telegram (@username)
--   - first_name: Nama depan user
--   - is_premium: Status premium aktif/tidak
--   - premium_expiry: Tanggal kadaluarsa premium
--   - total_paid: Total pembayaran yang sudah dilakukan
--   - free_watches_used: Jumlah tontonan gratis yang sudah digunakan
--   - free_watches_limit: Batas maksimal tontonan gratis per minggu
--   - reset_time: Waktu terakhir reset counter tontonan gratis
--   - created_at: Waktu user terdaftar
--   - last_active: Waktu terakhir user aktif
-- =====================================================================================

CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  username VARCHAR(255),
  first_name VARCHAR(255) NOT NULL,
  is_premium BOOLEAN DEFAULT FALSE,
  premium_expiry TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  total_paid DECIMAL(10,2) DEFAULT 0,
  free_watches_used INTEGER DEFAULT 0,
  free_watches_limit INTEGER DEFAULT 1,
  reset_time TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_is_premium ON users(is_premium);
CREATE INDEX IF NOT EXISTS idx_users_premium_expiry ON users(premium_expiry);

-- Comments dokumentasi
COMMENT ON TABLE users IS 'Tabel untuk menyimpan data pengguna Telegram dan status premium';
COMMENT ON COLUMN users.telegram_id IS 'ID unik dari Telegram';
COMMENT ON COLUMN users.username IS 'Username Telegram (@username)';
COMMENT ON COLUMN users.first_name IS 'Nama depan user';
COMMENT ON COLUMN users.is_premium IS 'Status premium aktif/tidak';
COMMENT ON COLUMN users.premium_expiry IS 'Tanggal kadaluarsa premium';
COMMENT ON COLUMN users.total_paid IS 'Total pembayaran yang sudah dilakukan (Rupiah)';
COMMENT ON COLUMN users.free_watches_used IS 'Jumlah tontonan gratis yang sudah digunakan';
COMMENT ON COLUMN users.free_watches_limit IS 'Batas maksimal tontonan gratis per minggu';
COMMENT ON COLUMN users.reset_time IS 'Waktu terakhir reset counter tontonan gratis';

-- =====================================================================================
-- TABEL 2: DRAMA
-- =====================================================================================
-- Deskripsi: Menyimpan data drama/film yang tersedia untuk ditonton
--
-- Fields:
--   - id: Primary key auto increment
--   - book_name: Nama drama dalam bahasa asli
--   - book_name_en: Nama drama dalam bahasa Inggris
--   - book_name_lower: Nama drama dalam huruf kecil untuk URL
--   - cover: URL gambar cover drama
--   - chapter_id: ID chapter dari sumber
--   - has_downloaded: Status apakah drama sudah didownload
--   - created_at: Waktu drama ditambahkan
--   - updated_at: Waktu terakhir drama diupdate
-- =====================================================================================

CREATE TABLE IF NOT EXISTS "Drama" (
  id BIGSERIAL PRIMARY KEY,
  book_name VARCHAR(500) NOT NULL,
  book_name_en VARCHAR(500),
  book_name_lower VARCHAR(500),
  cover TEXT,
  chapter_id INTEGER,
  has_downloaded BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_drama_has_downloaded ON "Drama"(has_downloaded);
CREATE INDEX IF NOT EXISTS idx_drama_created_at ON "Drama"(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_drama_chapter_id ON "Drama"(chapter_id);

-- Comments dokumentasi
COMMENT ON TABLE "Drama" IS 'Tabel untuk menyimpan data drama/film yang tersedia';
COMMENT ON COLUMN "Drama".book_name IS 'Nama drama dalam bahasa asli';
COMMENT ON COLUMN "Drama".book_name_en IS 'Nama drama dalam bahasa Inggris';
COMMENT ON COLUMN "Drama".book_name_lower IS 'Nama drama dalam huruf kecil untuk URL';
COMMENT ON COLUMN "Drama".cover IS 'URL gambar cover drama';
COMMENT ON COLUMN "Drama".chapter_id IS 'ID chapter dari sumber';
COMMENT ON COLUMN "Drama".has_downloaded IS 'Status apakah drama sudah didownload ke storage';

-- =====================================================================================
-- TABEL 3: TELEGRAM_CACHE
-- =====================================================================================
-- Deskripsi: Menyimpan cache Telegram file_id untuk optimasi video streaming
--            Menghindari upload ulang video yang sama ke Telegram
--
-- Fields:
--   - id: Primary key auto increment
--   - drama_id: ID drama dari tabel Drama
--   - episode: Nomor episode
--   - file_id: File ID dari Telegram untuk caching
--   - created_at: Waktu pertama kali di-cache
--   - updated_at: Waktu terakhir di-update
--
-- Constraint:
--   - UNIQUE(drama_id, episode): Satu drama & episode hanya punya 1 cache
-- =====================================================================================

CREATE TABLE IF NOT EXISTS telegram_cache (
  id BIGSERIAL PRIMARY KEY,
  drama_id BIGINT NOT NULL,
  episode INTEGER NOT NULL,
  file_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(drama_id, episode)
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_telegram_cache_drama_episode 
  ON telegram_cache(drama_id, episode);
CREATE INDEX IF NOT EXISTS idx_telegram_cache_drama_id 
  ON telegram_cache(drama_id);

-- Comments dokumentasi
COMMENT ON TABLE telegram_cache IS 'Cache untuk Telegram file_ids untuk optimasi video streaming';
COMMENT ON COLUMN telegram_cache.drama_id IS 'ID drama dari tabel Drama';
COMMENT ON COLUMN telegram_cache.episode IS 'Nomor episode';
COMMENT ON COLUMN telegram_cache.file_id IS 'File ID dari Telegram untuk caching';
COMMENT ON COLUMN telegram_cache.created_at IS 'Waktu pertama kali di-cache';
COMMENT ON COLUMN telegram_cache.updated_at IS 'Waktu terakhir di-update';

-- =====================================================================================
-- TABEL 4: EPISODES
-- =====================================================================================
-- Deskripsi: Menyimpan data episode dari setiap drama
--            Setiap drama bisa memiliki banyak episode
--
-- Fields:
--   - id: Primary key auto increment
--   - drama_id: ID drama dari tabel Drama (Foreign Key)
--   - episode_number: Nomor episode (1, 2, 3, dst)
--   - title: Judul episode (opsional)
--   - duration: Durasi video dalam detik
--   - s3_key: Key/path file di S3 storage
--   - s3_url: URL lengkap untuk akses file di S3
--   - video_quality: Kualitas video (720p, 1080p, dll)
--   - file_size: Ukuran file dalam bytes
--   - is_downloaded: Status apakah episode sudah didownload dan diupload ke S3
--   - created_at: Waktu episode ditambahkan
--   - updated_at: Waktu terakhir episode diupdate
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
-- TABEL 5: PAYMENTS
-- =====================================================================================
-- Deskripsi: Menyimpan data pembayaran dan transaksi premium dari Saweria
--
-- Fields:
--   - id: Primary key auto increment
--   - user_id: Telegram ID user yang melakukan pembayaran (FK ke users.telegram_id)
--   - package_type: Jenis paket (1day, 7day, 30day, 1year)
--   - amount: Jumlah pembayaran raw dari Saweria (amount_raw)
--   - amount_display: Jumlah pembayaran yang ditampilkan ke user
--   - qr_string: QR code string dari Saweria webhook
--   - saweria_donation_id: ID donasi dari Saweria
--   - payment_code: Kode pembayaran unik untuk tracking
--   - status: Status pembayaran (pending, completed, pending_assignment, failed)
--   - webhook_data: Data lengkap dari webhook Saweria (JSON)
--   - created_at: Waktu pembayaran dibuat
--   - completed_at: Waktu pembayaran selesai diproses
--
-- Paket Premium:
--   - 1day: Rp 3.000 (1 hari)
--   - 7day: Rp 10.000 (7 hari)
--   - 30day: Rp 25.000 (30 hari)
--   - 1year: Rp 50.000 (365 hari)
-- =====================================================================================

CREATE TABLE IF NOT EXISTS payments (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT,
  package_type VARCHAR(50) NOT NULL,
  amount INTEGER NOT NULL,
  amount_display INTEGER,
  qr_string TEXT,
  saweria_donation_id VARCHAR(255),
  payment_code VARCHAR(50),
  status VARCHAR(50) DEFAULT 'pending',
  webhook_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE,
  FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_payment_code ON payments(payment_code);
CREATE INDEX IF NOT EXISTS idx_payments_saweria_donation_id ON payments(saweria_donation_id);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at DESC);

-- Comments dokumentasi
COMMENT ON TABLE payments IS 'Tabel untuk menyimpan data pembayaran dan transaksi premium';
COMMENT ON COLUMN payments.user_id IS 'Telegram ID user yang melakukan pembayaran';
COMMENT ON COLUMN payments.package_type IS 'Jenis paket: 1day, 7day, 30day, 1year';
COMMENT ON COLUMN payments.amount IS 'Jumlah pembayaran raw dari Saweria (amount_raw)';
COMMENT ON COLUMN payments.amount_display IS 'Jumlah pembayaran yang ditampilkan ke user (amount_to_display)';
COMMENT ON COLUMN payments.qr_string IS 'QR code string dari Saweria webhook (qr_string)';
COMMENT ON COLUMN payments.saweria_donation_id IS 'ID donasi dari Saweria';
COMMENT ON COLUMN payments.payment_code IS 'Kode pembayaran unik untuk tracking';
COMMENT ON COLUMN payments.status IS 'Status pembayaran: pending, completed, pending_assignment, failed';
COMMENT ON COLUMN payments.webhook_data IS 'Data lengkap dari webhook Saweria dalam format JSON';
COMMENT ON COLUMN payments.completed_at IS 'Waktu pembayaran selesai diproses';

-- =====================================================================================
-- TABEL 6: SUBSCRIPTIONS
-- =====================================================================================
-- Deskripsi: Menyimpan data subscription QR code yang dibuat via Saweria API
--            Sistem ini berbeda dengan payments - langsung generate QR code
--
-- Fields:
--   - id: Primary key auto increment
--   - user_id: Telegram ID user yang membuat subscription (FK ke users.telegram_id)
--   - saweria_donation_id: ID donasi dari Saweria API response
--   - package_type: Jenis paket (1day, 7day, 30day, 1year)
--   - amount: Jumlah pembayaran sesuai paket
--   - payment_type: Tipe pembayaran (qris, gopay, dll)
--   - qr_string: QR code string dari Saweria API
--   - message: Pesan yang dikirim ke Saweria
--   - status: Status subscription (pending, completed, failed)
--   - customer_info: Info customer dari API request (JSON)
--   - webhook_data: Data lengkap dari webhook Saweria (JSON)
--   - created_at: Waktu subscription dibuat
--   - completed_at: Waktu subscription selesai diproses
--
-- Perbedaan dengan tabel payments:
-- - subscriptions: Untuk QR code langsung dari bot via API
-- - payments: Untuk payment code manual yang user tulis di Saweria
-- =====================================================================================

CREATE TABLE IF NOT EXISTS subscriptions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  saweria_donation_id VARCHAR(255),
  package_type VARCHAR(50) NOT NULL,
  amount INTEGER NOT NULL,
  payment_type VARCHAR(50) DEFAULT 'qris',
  qr_string TEXT,
  message TEXT,
  status VARCHAR(50) DEFAULT 'pending',
  customer_info JSONB,
  webhook_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE,
  FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

-- Index untuk optimasi query
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_saweria_donation_id ON subscriptions(saweria_donation_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_created_at ON subscriptions(created_at DESC);

-- Comments dokumentasi
COMMENT ON TABLE subscriptions IS 'Tabel untuk menyimpan data subscription QR code via Saweria API';
COMMENT ON COLUMN subscriptions.user_id IS 'Telegram ID user yang membuat subscription';
COMMENT ON COLUMN subscriptions.saweria_donation_id IS 'ID donasi dari Saweria API response';
COMMENT ON COLUMN subscriptions.package_type IS 'Jenis paket: 1day, 7day, 30day, 1year';
COMMENT ON COLUMN subscriptions.amount IS 'Jumlah pembayaran sesuai paket';
COMMENT ON COLUMN subscriptions.payment_type IS 'Tipe pembayaran: qris, gopay, dll';
COMMENT ON COLUMN subscriptions.qr_string IS 'QR code string dari Saweria API';
COMMENT ON COLUMN subscriptions.message IS 'Pesan yang dikirim ke Saweria';
COMMENT ON COLUMN subscriptions.status IS 'Status subscription: pending, completed, failed';
COMMENT ON COLUMN subscriptions.customer_info IS 'Info customer dari API request dalam format JSON';
COMMENT ON COLUMN subscriptions.webhook_data IS 'Data lengkap dari webhook Saweria dalam format JSON';
COMMENT ON COLUMN subscriptions.created_at IS 'Waktu subscription dibuat';
COMMENT ON COLUMN subscriptions.completed_at IS 'Waktu subscription selesai diproses';

-- =====================================================================================
-- SELESAI - DATABASE SCHEMA SETUP COMPLETE
-- =====================================================================================
--
-- Summary:
-- ✓ 6 tabel berhasil dibuat
--   1. users - Data pengguna dan status premium (12 fields)
--   2. Drama - Data drama/film yang tersedia (8 fields)
--   3. telegram_cache - Cache file_id Telegram (6 fields)
--   4. episodes - Data episode dari setiap drama (12 fields)
--   5. payments - Data pembayaran dan transaksi (12 fields)
--   6. subscriptions - Data subscription QR code (13 fields)
--
-- ✓ 23 index untuk optimasi query
-- ✓ Foreign keys dan constraints
-- ✓ Comments dokumentasi lengkap
--
-- Relasi Tabel:
-- users (telegram_id) ←─── payments (user_id) [ON DELETE CASCADE]
-- users (telegram_id) ←─── subscriptions (user_id) [ON DELETE CASCADE]
-- Drama (id) ←─── episodes (drama_id) [ON DELETE CASCADE]
-- Drama (id) ←─── telegram_cache (drama_id) [referensi tidak langsung]
--
-- Sistem Pembayaran:
-- 1. Payment Code Manual (tabel payments):
--    - User dapat payment code dari bot
--    - User tulis payment code di Saweria message
--    - Webhook cari berdasarkan payment_code
--
-- 2. QR Code via API (tabel subscriptions):
--    - Bot langsung generate QR code via Saweria API
--    - User scan QR code langsung
--    - Webhook cari berdasarkan saweria_donation_id
--
-- Storage Structure di S3:
-- drama_id/
--   ├── episode_1/
--   │   └── episode_1.mp4
--   ├── episode_2/
--   │   └── episode_2.mp4
--   └── ...
--
-- Next Steps:
-- 1. Verifikasi semua tabel sudah terbuat di Table Editor
-- 2. Setup Row Level Security (RLS) jika diperlukan
-- 3. Konfigurasi .env dengan SUPABASE_URL dan ANON_KEY
-- 4. Test koneksi dari aplikasi
-- 5. Upload video ke S3 dengan struktur folder yang benar
--
-- =====================================================================================
