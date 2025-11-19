import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8458286417:AAFJJSobOlZ_E3QPsx8bdCBqJuQEgjMvK7E')

class DramaBot:
    def __init__(self):
        self.application = ApplicationBuilder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all bot handlers"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("dramas", self.show_dramas))
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id

        # Create or update user in database
        await self.create_or_update_user(user_id, user.username, user.first_name)

        welcome_text = f"""
🎬 Selamat datang di Drama Cina Gratis Bot! 

👤 User: {user.first_name}

Silakan pilih paket premium untuk menonton drama!
        """

        keyboard = [
            [InlineKeyboardButton("💰 Lihat Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🎬 *DRAMA CINA GRATIS BOT*

📋 *Cara Penggunaan:*
1. Gunakan /start untuk memulai
2. Pilih drama yang ingin ditonton
3. Tonton gratis hingga limit tercapai
4. Untuk tontonan lebih banyak, hubungi admin

📺 *Fitur:*
• Streaming drama Cina terbaru
• Kualitas HD
• Subtitle Indonesia
• Tontonan gratis 3x per user

💰 *Premium:*
Untuk akses unlimited, hubungi @admin

❓ *Bantuan:*
Kirim pesan ke admin jika ada masalah
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def show_dramas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available dramas"""
        user_id = update.effective_user.id

        # Get dramas from database
        dramas = await self.get_available_dramas()

        if not dramas:
            await update.message.reply_text("❌ Maaf, tidak ada drama tersedia saat ini.")
            return

        text = "📺 Drama Tersedia\n\nPilih drama yang ingin ditonton:"

        keyboard = []
        for drama in dramas[:10]:  # Show max 10 dramas
            keyboard.append([
                InlineKeyboardButton(
                    f"🎬 {drama['title']} (Ep. {drama['episodes']})",
                    callback_data=f"drama_{drama['id']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(text, reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "show_dramas":
            await self.show_dramas_callback(query)
        elif data == "show_packages":
            await self.show_packages_callback(query)
        elif data == "help":
            await self.help_callback(query)
        elif data == "back_to_main":
            await self.back_to_main_callback(query)
        elif data.startswith("drama_"):
            drama_id = data.split("_")[1]
            await self.select_drama_callback(query, drama_id, user_id)
        elif data.startswith("episode_"):
            _, drama_id, episode_num = data.split("_")
            await self.stream_episode_callback(query, drama_id, int(episode_num), user_id)
        elif data.startswith("copy_code_"):
            payment_code = data.split("_")[2]
            await query.answer(f"Kode pembayaran {payment_code} berhasil dicopy!", show_alert=True)
        elif data.startswith("package_"):
            package_type = data.split("_")[1]
            await self.select_package_callback(query, package_type, user_id)

    async def select_drama_callback(self, query, drama_id: str, user_id: int):
        """Handle drama selection"""
        # Get drama details
        drama = await self.get_drama_details(drama_id)
        if not drama:
            await query.edit_message_text("❌ Drama tidak ditemukan.")
            return

        text = f"""
🎬 *{drama['title']}*

📝 Deskripsi: {drama.get('description', 'N/A')}
🎭 Genre: {drama.get('genre', 'N/A')}
📺 Total Episode: {drama['episodes']}
⭐ Rating: {drama.get('rating', 'N/A')}

Pilih episode yang ingin ditonton:
        """

        keyboard = []
        for i in range(1, min(drama['episodes'] + 1, 11)):  # Show max 10 episodes
            keyboard.append([
                InlineKeyboardButton(f"Episode {i}", callback_data=f"episode_{drama_id}_{i}")
            ])

        if drama['episodes'] > 10:
            keyboard.append([InlineKeyboardButton("➡️ Next Episodes", callback_data=f"episodes_page_{drama_id}_2")])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="show_dramas")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def stream_episode_callback(self, query, drama_id: str, episode_num: int, user_id: int):
        """Handle episode streaming"""
        # Check if user has premium
        is_premium = await self.check_user_premium_status(user_id)
        
        if not is_premium:
            await self.show_packages_callback(query)
            return
        
        # Get episode URL from S3
        episode_url = await self.get_episode_url(drama_id, episode_num)
        if not episode_url:
            await query.edit_message_text("❌ Episode tidak tersedia.")
            return

        # Send streaming message
        text = f"""
🎬 Episode {episode_num} - Sedang diproses...

📺 Link streaming akan segera dikirim!
        """

        await query.edit_message_text(text)

        # Send video file
        try:
            await query.message.reply_video(
                video=episode_url,
                caption=f"🎬 Episode {episode_num}\n\nSelamat menonton! 🎭",
                supports_streaming=True
            )
        except Exception as e:
            await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")

    async def show_packages_callback(self, query):
        """Show premium packages"""
        text = """
💰 *PAKET PREMIUM DRAMA CINA*

Pilih paket yang sesuai kebutuhan Anda:

🎟️ *1 Hari* - Rp 3.000
   • Akses penuh 24 jam
   • Semua drama tersedia
   • Kualitas HD

📅 *7 Hari* - Rp 10.000
   • Akses selama 1 minggu
   • Drama terbaru & klasik
   • Download episode

📆 *30 Hari* - Rp 25.000
   • Akses 1 bulan penuh
   • Update drama mingguan
   • Subtitle Indonesia

🎉 *1 Tahun* - Rp 50.000
   • Akses setahun unlimited
   • Drama eksklusif
   • Prioritas support

💳 *Pembayaran:*
Kirim bukti transfer ke @admin
        """

        keyboard = [
            [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
            [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
            [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
            [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")],
            [InlineKeyboardButton("💬 Hubungi Admin", url="https://t.me/admin")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def select_package_callback(self, query, package_type: str, user_id: int):
        """Handle package selection"""
        package_info = {
            "1day": {"name": "1 Hari", "price": "Rp 3.000", "duration": "24 jam"},
            "7day": {"name": "7 Hari", "price": "Rp 10.000", "duration": "1 minggu"},
            "30day": {"name": "30 Hari", "price": "Rp 25.000", "duration": "1 bulan"},
            "1year": {"name": "1 Tahun", "price": "Rp 50.000", "duration": "1 tahun"}
        }

        if package_type not in package_info:
            await query.edit_message_text("❌ Paket tidak valid.")
            return

        pkg = package_info[package_type]

        # Generate payment code for tracking
        payment_code = await self.generate_payment_code(user_id, package_type)
        
        text = f"""
🎟️ *PAKET {pkg['name'].upper()}*

💰 Harga: {pkg['price']}
⏰ Durasi: {pkg['duration']}
🏷️ Kode Pembayaran: `{payment_code}`

📋 *Cara Pembayaran via Saweria:*

1️⃣ Klik link Saweria di bawah

2️⃣ Donasi sesuai harga paket: {pkg['price']}

3️⃣ Tulis kode pembayaran `{payment_code}` di pesan donasi

4️⃣ Hubungi admin untuk aktivasi: @admin

✅ *Setelah pembayaran berhasil:*
• Akses penuh semua drama
• Streaming tanpa batas
• Kualitas HD
• Update terbaru

❓ Masalah pembayaran? Hubungi @admin
        """

        keyboard = [
            [InlineKeyboardButton("💳 Bayar via Saweria", url="https://saweria.co/yoursaweria")],
            [InlineKeyboardButton(f"📋 Copy Kode: {payment_code}", callback_data=f"copy_code_{payment_code}")],
            [InlineKeyboardButton("💬 Hubungi Admin", url="https://t.me/admin")],
            [InlineKeyboardButton("📋 Lihat Paket Lain", callback_data="show_packages")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    # Database operations
    async def generate_payment_code(self, user_id: int, package_type: str) -> str:
        """Generate unique payment code for user"""
        import hashlib
        import time
        
        # Generate unique code based on user_id, package_type, and timestamp
        raw_string = f"{user_id}_{package_type}_{int(time.time())}"
        payment_code = hashlib.md5(raw_string.encode()).hexdigest()[:8].upper()
        
        # Store payment code in database for tracking
        if supabase:
            try:
                payment_data = {
                    'user_id': user_id,
                    'package_type': package_type,
                    'amount': {'1day': 3000, '7day': 10000, '30day': 25000, '1year': 50000}[package_type],
                    'status': 'pending',
                    'payment_code': payment_code
                }
                supabase.table('payments').insert(payment_data).execute()
            except Exception as e:
                print(f"Error storing payment code: {e}")
        
        return payment_code

    async def check_user_premium_status(self, user_id: int) -> bool:
        """Check if user has active premium"""
        if not supabase:
            return False
        
        try:
            result = supabase.table('users').select('is_premium, premium_expiry').eq('telegram_id', user_id).execute()
            if result.data:
                user_data = result.data[0]
                if user_data['is_premium'] and user_data['premium_expiry']:
                    expiry = datetime.fromisoformat(user_data['premium_expiry'].replace('Z', '+00:00'))
                    return expiry > datetime.now(expiry.tzinfo)
            return False
        except Exception as e:
            print(f"Error checking premium status: {e}")
            return False

    async def create_payment_record(self, user_id: int, package_type: str) -> int:
        """Create payment record for tracking"""
        if not supabase:
            return None
            
        try:
            package_prices = {
                '1day': 3000,
                '7day': 10000,
                '30day': 25000,
                '1year': 50000
            }
            
            payment_data = {
                'user_id': user_id,
                'package_type': package_type,
                'amount': package_prices[package_type],
                'status': 'pending'
            }
            
            result = supabase.table('payments').insert(payment_data).execute()
            return result.data[0]['id'] if result.data else None
        except Exception as e:
            print(f"Error creating payment record: {e}")
            return None

    async def create_or_update_user(self, user_id: int, username: str, first_name: str):
        """Create or update user in database"""
        if not supabase:
            return

        try:
            # Check if user exists
            result = supabase.table('users').select('*').eq('telegram_id', user_id).execute()

            if not result.data:
                # Create new user
                user_data = {
                    'telegram_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'is_premium': False,
                    'created_at': datetime.now().isoformat(),
                    'last_active': datetime.now().isoformat()
                }
                supabase.table('users').insert(user_data).execute()
            else:
                # Update last active
                supabase.table('users').update({
                    'last_active': datetime.now().isoformat()
                }).eq('telegram_id', user_id).execute()

        except Exception as e:
            print(f"Error creating/updating user: {e}")

    async def get_available_dramas(self):
        """Get available dramas from database"""
        if not supabase:
            # Return sample data if no database
            return [
                {'id': '1', 'title': 'Love in the Air', 'episodes': 12, 'genre': 'Romance', 'rating': 9.2},
                {'id': '2', 'title': 'My Stand-In', 'episodes': 12, 'genre': 'BL Romance', 'rating': 9.5},
                {'id': '3', 'title': 'Only Friends', 'episodes': 12, 'genre': 'BL Drama', 'rating': 8.8}
            ]

        try:
            result = supabase.table('dramas').select('*').eq('is_active', True).limit(10).execute()
            return result.data
        except Exception as e:
            print(f"Error getting dramas: {e}")
            return []

    async def get_drama_details(self, drama_id: str):
        """Get drama details"""
        if not supabase:
            # Return sample data
            sample_dramas = {
                '1': {'id': '1', 'title': 'Love in the Air', 'episodes': 12, 'genre': 'Romance', 'rating': 9.2, 'description': 'A beautiful BL romance story'},
                '2': {'id': '2', 'title': 'My Stand-In', 'episodes': 12, 'genre': 'BL Romance', 'rating': 9.5, 'description': 'Complex relationships and love triangles'},
                '3': {'id': '3', 'title': 'Only Friends', 'episodes': 12, 'genre': 'BL Drama', 'rating': 8.8, 'description': 'Friends to lovers story'}
            }
            return sample_dramas.get(drama_id)

        try:
            result = supabase.table('dramas').select('*').eq('id', drama_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting drama details: {e}")
            return None

    async def get_episode_url(self, drama_id: str, episode_num: int) -> str:
        """Get episode streaming URL from S3"""
        if not supabase:
            # Return sample S3 URL
            return f"https://s3.nevaobjects.id/drama/{drama_id}/episode_{episode_num}/episode_{episode_num}.mp4"

        try:
            result = supabase.table('episodes').select('s3_url').eq('drama_id', drama_id).eq('episode_number', episode_num).execute()
            if result.data:
                return result.data[0]['s3_url']
            return None
        except Exception as e:
            print(f"Error getting episode URL: {e}")
            return None

    # Callback handlers
    async def show_dramas_callback(self, query):
        """Handle show dramas callback"""
        user_id = query.from_user.id

        dramas = await self.get_available_dramas()

        if not dramas:
            await query.edit_message_text("❌ Maaf, tidak ada drama tersedia saat ini.")
            return

        text = "📺 Drama Tersedia\n\nPilih drama yang ingin ditonton:"

        keyboard = []
        for drama in dramas[:10]:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎬 {drama['title']} (Ep. {drama['episodes']})",
                    callback_data=f"drama_{drama['id']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup)

    async def help_callback(self, query):
        """Handle help callback"""
        help_text = """
🎬 *DRAMA CINA GRATIS BOT*

📋 *Cara Penggunaan:*
1. Pilih paket premium yang diinginkan
2. Lakukan pembayaran
3. Kirim bukti ke admin
4. Admin aktivasi dalam 5-10 menit
5. Mulai tonton semua drama!

💰 *Paket Premium:*
• 🎟️ 1 Hari - Rp 3.000
• 📅 7 Hari - Rp 10.000
• 📆 30 Hari - Rp 25.000
• 🎉 1 Tahun - Rp 50.000

📺 *Fitur Premium:*
• ✅ Tontonan unlimited
• ✅ Drama terbaru & klasik
• ✅ Kualitas HD
• ✅ Download episode
• ✅ Subtitle Indonesia

❓ *Bantuan:*
Kirim pesan ke admin jika ada masalah
        """
        keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def back_to_main_callback(self, query):
        """Handle back to main callback"""
        user = query.from_user

        welcome_text = f"""
🎬 Selamat datang kembali!

👤 User: {user.first_name}

Silakan pilih paket premium untuk menonton drama!
        """

        keyboard = [
            [InlineKeyboardButton("💰 Lihat Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(welcome_text, reply_markup=reply_markup)

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin panel for managing payments"""
        user_id = update.effective_user.id
        
        # Simple admin check (you can make this more sophisticated)
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Akses ditolak. Anda bukan admin.")
            return
        
        # Get pending payments from webhook server
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:5000/pending-payments') as response:
                    data = await response.json()
                    
            pending_payments = data.get('pending_payments', [])
            
            if not pending_payments:
                await update.message.reply_text("✅ Tidak ada pembayaran pending.")
                return
            
            text = "💰 *PEMBAYARAN PENDING*\n\n"
            for payment in pending_payments[:5]:  # Show max 5 payments
                text += f"ID: `{payment['id']}`\n"
                text += f"💰 {payment['amount']:,} ({payment['package_type']})\n"
                text += f"👤 {payment['donator_name']}\n"
                text += f"💬 {payment['message'][:50]}...\n"
                text += f"📅 {payment['created_at'][:16]}\n\n"
            
            text += "Untuk aktivasi manual:\n"
            text += "`/activate <payment_id> <telegram_id>`"
            
            await update.message.reply_text(text, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error mengakses data pembayaran: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""
        text = update.message.text
        user_id = update.effective_user.id
        
        # Handle admin commands
        if text.startswith('/activate'):
            await self.handle_manual_activation(update, context)
            return
            
        await update.message.reply_text("Gunakan /start untuk memulai atau /help untuk bantuan.")

    async def handle_manual_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle manual premium activation by admin"""
        user_id = update.effective_user.id
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ Akses ditolak.")
            return
        
        try:
            parts = update.message.text.split()
            if len(parts) != 3:
                await update.message.reply_text("Format: `/activate <payment_id> <telegram_id>`", parse_mode='Markdown')
                return
            
            payment_id = int(parts[1])
            target_telegram_id = int(parts[2])
            
            # Call webhook server to assign payment
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post('http://localhost:5000/assign-payment', json={
                    'payment_id': payment_id,
                    'telegram_id': target_telegram_id
                }) as response:
                    result = await response.json()
            
            if response.status == 200:
                await update.message.reply_text(f"✅ Premium berhasil diaktivasi untuk user {target_telegram_id}")
            else:
                await update.message.reply_text(f"❌ Gagal aktivasi: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    def run(self):
        """Run the bot"""
        print("🤖 Drama Bot is running...")
        self.application.run_polling()


# Initialize and run bot
if __name__ == '__main__':
    bot = DramaBot()
    bot.run()