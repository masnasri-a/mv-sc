# Premium Expiry Management System

Sistem untuk mengelola dan menangani expired premium users secara otomatis.

## 📋 Fitur

### 🔍 Automatic Expiry Checking
- Mengecek user premium yang sudah expired setiap jam
- Otomatis update status premium menjadi `false`
- Reset `premium_expiry` menjadi `null`

### 📢 User Notifications
- Kirim notifikasi ke user ketika premium expired
- Tawarkan opsi upgrade premium kembali
- Pesan dengan tombol untuk langsung upgrade

### 👨‍💼 Admin Commands
- `/check_expiry` - Manual check dan expire premium
- `/extend_premium <telegram_id> <days>` - Extend premium user
- `/expire_premium <telegram_id>` - Force expire premium user

### 🔄 Background Service
- Service yang berjalan terus menerus
- Cek expiry setiap 1 jam
- Logging untuk monitoring

## 🚀 Cara Penggunaan

### Menjalankan Background Service
```bash
# Start service
./start_premium_checker.sh

# Stop service
./stop_premium_checker.sh

# Test sekali jalan
python premium_expiry_checker.py --once
```

### Admin Commands (Telegram Bot)
```
/check_expiry - Cek dan expire premium yang sudah habis
/extend_premium 123456789 30 - Extend premium user 30 hari
/expire_premium 123456789 - Force expire premium user
```

## 📊 Database Functions

### `check_and_expire_premium_users()`
- Query user dengan `is_premium = true` dan `premium_expiry < NOW()`
- Update status menjadi `is_premium = false`
- Return list user yang di-expire

### `get_expired_premium_users()`
- Query user premium yang sudah expired
- Tidak mengubah status, hanya return data

### `expire_user_premium(telegram_id)`
- Manual expire premium user tertentu

### `extend_user_premium(telegram_id, days)`
- Extend premium user dengan jumlah hari tertentu
- Jika sudah ada expiry, ditambah dari expiry yang ada

## 🔧 Konfigurasi

### Environment Variables
```env
BOT_TOKEN=your_telegram_bot_token
SAWERIA_USER_ID=f592c7af-65cb-465b-97e2-454b9c2d5b6b
```

### Admin IDs
Update `ADMIN_IDS` di `handlers.py` dan `bot.py`:
```python
ADMIN_IDS = [123456789, 987654321]  # Ganti dengan Telegram ID admin
```

## 📈 Monitoring

### Logs
- Premium expiry checker akan print log ke console
- Error handling untuk semua operasi
- Status check setiap jam

### Database Monitoring
```sql
-- Cek user premium yang aktif
SELECT * FROM users WHERE is_premium = true;

-- Cek user yang akan expired dalam 24 jam
SELECT * FROM users
WHERE is_premium = true
AND premium_expiry < NOW() + INTERVAL '1 day';

-- Cek subscription history
SELECT * FROM subscriptions ORDER BY created_at DESC;
```

## ⚠️ Error Handling

- Semua database operations memiliki try-catch
- Failed notifications tidak menghentikan proses
- Service akan continue running meski ada error
- Admin akan mendapat notifikasi error via logs

## 🔄 Workflow

1. **User Upgrade Premium** → Subscription dibuat via Saweria
2. **Pembayaran Berhasil** → `is_premium = true`, `premium_expiry` di-set
3. **Background Service** → Cek expiry setiap jam
4. **Expiry Detected** → Status diupdate, notifikasi dikirim
5. **User Diberitahu** → Tawaran upgrade, bisa langsung upgrade lagi

## 🎯 Best Practices

- Jalankan background service di server/production
- Monitor logs regularly
- Backup database sebelum maintenance
- Test expiry checker dengan user test dulu
- Set admin IDs dengan benar untuk security