# Drama Cina Gratis Bot

Bot Telegram untuk streaming drama Cina dengan sistem premium berlangganan.

## Fitur

- 🎬 Streaming drama Cina terbaru
- 💰 Sistem premium dengan paket berlangganan
- 🔄 Integrasi Supabase untuk database
- ☁️ Storage video di S3-compatible
- 🎯 Inline keyboard interface

## Paket Premium

- 🎟️ **1 Hari** - Rp 3.000
- 📅 **7 Hari** - Rp 10.000
- 📆 **30 Hari** - Rp 25.000
- 🎉 **1 Tahun** - Rp 50.000

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Copy `.env.example` ke `.env` dan isi dengan data Anda:

```bash
cp .env.example .env
```

Edit `.env` dengan:
- `BOT_TOKEN`: Token bot Telegram dari @BotFather
- `SUPABASE_URL`: URL Supabase project
- `SUPABASE_KEY`: Anon key dari Supabase
- `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`: Credentials S3 storage

### 3. Database Schema (Supabase)

Buat tabel berikut di Supabase:

#### Tabel `users`
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    is_premium BOOLEAN DEFAULT FALSE,
    premium_expiry TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);
```

#### Tabel `dramas`
```sql
CREATE TABLE dramas (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    genre TEXT,
    episodes INTEGER NOT NULL,
    rating DECIMAL(3,1),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Tabel `episodes`
```sql
CREATE TABLE episodes (
    id SERIAL PRIMARY KEY,
    drama_id TEXT REFERENCES dramas(id),
    episode_number INTEGER NOT NULL,
    s3_url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(drama_id, episode_number)
);
```

### 4. S3 Storage Structure

Upload video ke S3 dengan struktur:
```
drama/
├── drama_id/
    ├── episode_X/
        └── episode_X.mp4
```

### 5. Run Bot

```bash
python bot.py
```

## Cara Penggunaan

1. User kirim `/start` ke bot
2. Bot tampilkan paket premium yang tersedia
3. User pilih paket dan lakukan pembayaran
4. Admin aktivasi premium user
5. User dapat menonton semua drama

## Development

### Menambah Drama Baru

1. Upload video ke S3 dengan struktur yang benar
2. Insert data ke tabel `dramas`
3. Insert data episode ke tabel `episodes`

### Testing

```bash
# Test tanpa database (menggunakan sample data)
# Set SUPABASE_URL dan SUPABASE_KEY ke empty string
```

## API Endpoints

Bot menggunakan callback queries untuk navigasi:
- `show_packages`: Tampilkan paket premium
- `package_{type}`: Pilih paket spesifik (1day, 7day, 30day, 1year)
- `show_dramas`: Tampilkan daftar drama
- `drama_{id}`: Pilih drama spesifik
- `episode_{drama_id}_{num}`: Stream episode
- `back_to_main`: Kembali ke menu utama

## Error Handling

Bot menangani error:
- Database connection failed → fallback ke sample data
- S3 upload failed → log error
- Video tidak ditemukan → pesan error ke user
- User belum premium → redirect ke paket premium

## Premium System (Future)

Saat ini premium system masih placeholder. Untuk implementasi:
1. Tambah payment gateway integration
2. Update user status ke premium
3. Remove limit tontonan untuk premium users