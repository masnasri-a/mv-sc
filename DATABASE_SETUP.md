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

### 2. Tabel `payments`
```sql
-- Tabel Payments untuk tracking pembayaran via Saweria
CREATE TABLE payments (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
  package_type VARCHAR(20) NOT NULL CHECK (package_type IN ('1day', '7day', '30day', '1year')),
  amount DECIMAL(10,2) NOT NULL,
  saweria_id VARCHAR(255) UNIQUE,
  saweria_donation_id VARCHAR(255),
  status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'expired')),
  webhook_data JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE
);
```

**Field Explanation:**
- `user_id`: Referensi ke telegram_id user
- `package_type`: Jenis paket (1day, 7day, 30day, 1year)
- `amount`: Jumlah pembayaran dalam Rupiah
- `saweria_donation_id`: ID donasi dari Saweria
- `webhook_data`: Data mentah dari webhook Saweria
- `status`: Status pembayaran (pending, completed, failed, expired)

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