# Setup Database Tables

## Tabel yang Sudah Dibuat di Supabase:

### 1. Tabel `users`
```sql
-- Tabel Users untuk bot Telegram
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  username VARCHAR(255),
  first_name VARCHAR(255) NOT NULL,
  is_premium BOOLEAN DEFAULT FALSE,
  premium_expiry TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  total_paid DECIMAL(10,2) DEFAULT 0
);
```

**Field Explanation:**
- `telegram_id`: ID unik dari Telegram
- `username`: Username Telegram (@username)
- `first_name`: Nama depan user
- `is_premium`: Status premium aktif/tidak
- `premium_expiry`: Tanggal kadaluarsa premium
- `total_paid`: Total pembayaran yang sudah dilakukan

### 3. Tabel `telegram_cache`
```sql
-- Tabel untuk caching Telegram file_id untuk optimasi video streaming
CREATE TABLE telegram_cache (
  id BIGSERIAL PRIMARY KEY,
  drama_id BIGINT NOT NULL,
  episode INTEGER NOT NULL,
  file_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(drama_id, episode)
);
```

**Field Explanation:**
- `drama_id`: ID drama dari tabel Drama
- `episode`: Nomor episode
- `file_id`: File ID dari Telegram untuk caching
- `created_at`: Waktu pertama kali di-cache
- `updated_at`: Waktu terakhir di-update

### 4. Update Tabel `users` (Tambahan Field)
```sql
-- Tambahkan field untuk sistem watch count gratis
ALTER TABLE users ADD COLUMN IF NOT EXISTS free_watches_used INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS free_watches_limit INTEGER DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_time TIMESTAMP WITH TIME ZONE DEFAULT NOW();
```

**Field Explanation:**
- `free_watches_used`: Jumlah tontonan gratis yang sudah digunakan
- `free_watches_limit`: Batas maksimal tontonan gratis per minggu
- `reset_time`: Waktu terakhir reset counter tontonan gratis

## Cara Setup Saweria Webhook:

### 1. Setup di Saweria
1. Login ke dashboard Saweria
2. Pergi ke Webhook Settings
3. Set webhook URL: `https://yourdomain.com/webhook/saweria`
4. Set webhook secret (simpan di .env)

### 2. Format Pesan Donasi
User harus tulis Telegram ID mereka di pesan donasi Saweria:
```
1234567890
```
atau
```
TelegramID: 1234567890
```

### 3. Webhook Response
Webhook akan otomatis:
- Extract Telegram ID dari pesan
- Tentukan paket berdasarkan jumlah donasi
- Update status premium user
- Record pembayaran di database

### 4. Package Mapping
```python
PACKAGE_PRICES = {
    '1day': 3000,    # Rp 3.000
    '7day': 10000,   # Rp 10.000
    '30day': 25000,  # Rp 25.000
    '1year': 50000   # Rp 50.000
}
```

## Testing:

### Test Webhook
```bash
# Test endpoint
POST http://localhost:5000/webhook/test
{
  "test": "data"
}

# Health check
GET http://localhost:5000/health
```

### Manual Premium Activation
```sql
-- Aktivasi manual user premium
UPDATE users 
SET is_premium = true, 
    premium_expiry = NOW() + INTERVAL '7 days'
WHERE telegram_id = 1234567890;
```

## Deployment:

### 1. Local Development
```bash
python webhook_handler.py
```

### 2. Production (dengan gunicorn)
```bash
gunicorn -w 4 -b 0.0.0.0:5000 webhook_handler:app
```

### 3. Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "webhook_handler:app"]
```