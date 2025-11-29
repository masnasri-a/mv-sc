# Saweria Webhook Setup Guide

## Overview
Webhook endpoint untuk menerima callback pembayaran dari Saweria telah terintegrasi dengan bot utama. Bot akan menjalankan webhook server secara otomatis saat dijalankan.

## Webhook Data Format

Saweria mengirim data webhook dalam format berikut:

```json
{
  "version": "2022.01",
  "created_at": "2025-11-29T23:54:56.226386+07:00",
  "id": "3b668a15-b581-4f15-8598-033528fb346d",
  "type": "donation",
  "amount_raw": 1008,
  "cut": -58,
  "donator_name": "masnasri",
  "donator_email": "",
  "donator_is_user": true,
  "message": "asdasdasd",
  "etc": {
    "qr_string": "00020101021226650013CO.XENDIT.WWW01189360084800000000020215WNtXtb6qmr4ZJBw0303UME51370014ID.CO.QRIS.WWW0215ID2025378199850520450995303360540410085802ID5922PT Harta Tahta Sukaria6013JAKARTA PUSAT610510340622905250ojFniZShpzIG3ypSJxoBBUU36304957B",
    "amount_to_display": 1000,
    "transaction_fee_policy": "TIPPER"
  }
}
```

### Field Mapping:
- `amount_raw`: Jumlah asli dalam rupiah (termasuk biaya transaksi)
- `etc.amount_to_display`: Jumlah yang ditampilkan ke user (sudah dikurangi biaya)
- `etc.qr_string`: String QR code untuk pembayaran
- `message`: Pesan dari donatur (berisi payment code atau Telegram ID)

## Setup Webhook di Saweria

1. **Login ke Saweria Dashboard**
   - Pergi ke https://saweria.co/dashboard
   - Login dengan akun Anda

2. **Konfigurasi Webhook**
   - Pergi ke Settings > Webhook
   - Masukkan Webhook URL:
     ```
     https://your-domain.com/webhook/saweria
     ```
     atau untuk development:
     ```
     http://your-server-ip:5000/webhook/saweria
     ```

3. **Konfigurasi Secret**
   - Set webhook secret di environment variable `SAWERIA_SECRET`
   - Pastikan secret sama dengan yang dikonfigurasi di Saweria

## Environment Variables

Tambahkan ke file `.env`:

```env
# Saweria Webhook Configuration
SAWERIA_SECRET=your_saweria_webhook_secret_here
PORT=5000
```

## Cara Menjalankan

Bot sekarang akan otomatis menjalankan webhook server saat dijalankan:

```bash
python3 bot.py
```

Output yang diharapkan:
```
🤖 Starting Drama Bot with Webhook Server...
🚀 Starting Saweria webhook server on port 5000
📡 Starting bot polling...
✅ Bot and webhook server are running!
```

## Endpoint yang Tersedia

- `POST /webhook/saweria` - Menerima callback pembayaran dari Saweria
- `POST /assign-payment` - Assign pembayaran pending ke user (untuk admin)
- `GET /pending-payments` - Lihat pembayaran yang belum di-assign
- `GET /health` - Health check

## Database Migration

Jalankan migration untuk menambahkan kolom baru ke tabel payments:

```sql
-- Jalankan file add_payment_columns.sql
\i add_payment_columns.sql
```

Migration menambahkan:
- `amount_display`: Jumlah yang ditampilkan ke user
- `qr_string`: String QR code dari Saweria

## Flow Pembayaran

1. User membuat subscription via bot
2. Bot generate QR code Saweria
3. User bayar via Saweria
4. Saweria kirim webhook ke endpoint
5. Webhook handler:
   - Cari user berdasarkan payment code atau Telegram ID
   - Update status pembayaran
   - Aktivasi premium user
   - Kirim notifikasi ke user

## Testing Webhook

Untuk testing webhook secara lokal, gunakan ngrok atau tool serupa:

```bash
# Install ngrok
npm install -g ngrok

# Expose port 5000
ngrok http 5000

# Gunakan URL dari ngrok sebagai webhook URL di Saweria
```

## Troubleshooting

- **Webhook tidak menerima callback**: Periksa firewall dan pastikan port 5000 terbuka
- **Payment tidak terdeteksi**: Periksa format message di Saweria (harus ada payment code atau Telegram ID)
- **Error aktivasi premium**: Periksa koneksi database dan struktur tabel

## Security

- Selalu gunakan HTTPS untuk production
- Jaga kerahasiaan `SAWERIA_SECRET`
- Validasi webhook data sebelum processing