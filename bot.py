import os, traceback
import json
import asyncio
import boto3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client
from config.db import get_supabase_client
from dotenv import load_dotenv
from botocore.client import Config

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = get_supabase_client()

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Admin whitelist - users with unlimited access
ADMIN_WHITELIST = [1356120446, 731203660]

# S3 configuration for video streaming
S3_ENDPOINT = os.getenv('S3_ENDPOINT')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET_KEY = os.getenv('S3_SECRET_KEY')
print("S3 Endpoint:", S3_ENDPOINT)

# Initialize S3 client
s3_client = boto3.client(
's3',
aws_access_key_id=S3_ACCESS_KEY,
aws_secret_access_key=S3_SECRET_KEY,
endpoint_url=S3_ENDPOINT,
config=Config(signature_version='s3')
)

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
        
        # Get user's watch count
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        print("User watch info:", watch_info)
        # Get 3 random dramas to display
        dramas = await self.get_featured_dramas(3)
        print("Featured dramas:", dramas)
        welcome_text = f"""
🎬 Selamat datang di Drama Cina Gratis Bot! 

👤 User: {user.first_name}
📺 Tontonan gratis: {remaining_watches}/{free_watches_limit}

📺 *Drama Pilihan Hari Ini:*
        """
        
        if dramas:
            for i, drama in enumerate(dramas, 1):
                welcome_text += f"\n{i}. 🎭 {drama['book_name']}"
        else:
            welcome_text += "\n❌ Tidak ada drama tersedia saat ini."
        
        if remaining_watches > 0:
            welcome_text += "\n\nSilakan pilih menu di bawah:"
        else:
            welcome_text += "\n\n⚠️ Tontonan gratis habis! Upgrade ke premium untuk lanjut menonton."

        keyboard = []
        
        # Add numbered buttons for each featured drama if user has remaining watches
        if dramas and remaining_watches > 0:
            drama_buttons = []
            for i, drama in enumerate(dramas, 1):
                drama_buttons.append(
                    InlineKeyboardButton(str(i), callback_data=f"featured_drama_{drama['id']}")
                )
            keyboard.append(drama_buttons)
            
        keyboard.extend([
            [InlineKeyboardButton("📺 Semua Drama", callback_data="show_dramas")],
            [InlineKeyboardButton("💰 Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

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
• Tontonan gratis 1x per minggu

💰 *Premium:*
Untuk akses unlimited, hubungi @admin

❓ *Bantuan:*
Kirim pesan ke admin jika ada masalah
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def show_dramas(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available dramas"""
        user_id = update.effective_user.id
        
        # Get user's watch count
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        
        # Check premium status
        is_premium = await self.check_user_premium_status(user_id)

        # Get dramas from database
        dramas = await self.get_available_dramas()

        if not dramas:
            await update.message.reply_text("❌ Maaf, tidak ada drama tersedia saat ini.")
            return

        if is_premium:
            text = "📺 Drama Tersedia\n🌟 Status: Premium (Unlimited)\n\nPilih drama yang ingin ditonton:"
        else:
            text = f"📺 Drama Tersedia\n📺 Tontonan gratis: {remaining_watches}/{free_watches_limit}\n\nPilih drama yang ingin ditonton:"

        keyboard = []
        for drama in dramas[:10]:  # Show max 10 dramas
            keyboard.append([
                InlineKeyboardButton(
                    f"🎬 {drama.get('title', 'N/A')} (Ep. {drama.get('episodes', 'N/A')})",
                    callback_data=f"drama_{drama.get('id', 'N/A')}"
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
        elif data.startswith("featured_drama_"):
            drama_id = data.split("_")[2]
            await self.select_featured_drama_callback(query, drama_id, user_id)
        elif data.startswith("episode_"):
            _, drama_id, episode_num = data.split("_")
            await self.stream_episode_callback(query, drama_id, int(episode_num), user_id)
        elif data.startswith("next_episode_"):
            _, _, drama_id, current_episode = data.split("_")
            await self.next_episode_callback(query, drama_id, int(current_episode), user_id)
        elif data.startswith("copy_code_"):
            payment_code = data.split("_")[2]
            await query.answer(f"Kode pembayaran {payment_code} berhasil dicopy!", show_alert=True)
        elif data.startswith("select_episodes_"):
            drama_id = data.split("_")[2]
            await self.select_episodes_callback(query, drama_id, user_id)

    async def select_drama_callback(self, query, drama_id: str, user_id: int):
        """Handle drama selection"""
        # Get drama details
        drama = await self.get_drama_details(drama_id)
        if not drama:
            await query.edit_message_text("❌ Drama tidak ditemukan.")
            return

        text = f"""
🎬 *{drama.get('title', 'N/A')}*

📝 Deskripsi: {drama.get('description', 'N/A')}
🎭 Genre: {drama.get('genre', 'N/A')}
📺 Total Episode: {drama.get('episodes', 0)}
⭐ Rating: {drama.get('rating', 'N/A')}

Pilih episode yang ingin ditonton:
        """

        keyboard = []
        for i in range(1, min(drama.get('episodes', 0) + 1, 11)):  # Show max 10 episodes
            keyboard.append([
                InlineKeyboardButton(f"Episode {i}", callback_data=f"episode_{drama_id}_{i}")
            ])

        if drama.get('episodes', 0) > 10:
            keyboard.append([InlineKeyboardButton("➡️ Next Episodes", callback_data=f"episodes_page_{drama_id}_2")])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="show_dramas")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def select_featured_drama_callback(self, query, drama_id: str, user_id: int):
        """Handle featured drama selection - directly stream episode 1"""
        # Check watch count first
        watch_info = await self.get_user_watch_count(user_id)
        print("Watch info for featured drama:", watch_info)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        
        # Check if user has premium
        is_premium = await self.check_user_premium_status(user_id)
        
        if not is_premium and remaining_watches <= 0:
            # Show premium packages if no free watches left
            await self.show_packages_callback(query)
            return
        
        # Get drama details
        drama = await self.get_drama_details(drama_id)
        if not drama:
            await query.edit_message_text("❌ Drama tidak ditemukan.")
            return
        
        # Get episode 1 URL from S3
        episode_url = await self.get_episode_url(drama_id, 1, drama.get('title', 'Unknown'))
        if not episode_url:
            await query.edit_message_text("❌ Episode tidak tersedia atau sedang dalam proses upload.")
            return

        # Increment watch count if not premium
        if not is_premium:
            await self.increment_watch_count(user_id)
            remaining_watches -= 1

        # Send streaming message
        watch_status = "Premium" if is_premium else f"Gratis ({remaining_watches} tersisa)"
        text = f"""
🎬 {drama.get('title', 'Unknown')} - Episode 1

📺 Status: {watch_status}
📹 Link streaming sedang diproses...
        """

        await query.edit_message_text(text)

        # Send video file
        try:
            if not episode_url:
                await query.message.reply_text("❌ Video tidak dapat dimuat. Silakan coba lagi nanti.")
                return
                
            caption = f"🎬 {drama.get('title', 'Unknown')} - Episode 1\n📺 Status: {watch_status}\n\nSelamat menonton! 🎭"
            
            # Send video with timeout handling
            await query.message.reply_video(
                video=episode_url,
                caption=caption,
                supports_streaming=True,
                protect_content=True,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30
            )
            
            # Add buttons based on premium status
            keyboard = []
            
            # Always add "Selanjutnya" button
            keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_1")])
            
            # Add episode selection for premium users
            if is_premium:
                actual_episodes = await self.get_episode_count_from_s3(drama_id)
                keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])
            
            # Always add home button
            keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Episode berikutnya:", reply_markup=reply_markup)
            
            # Show upgrade message if this was last free watch
            if not is_premium and remaining_watches == 0:
                upgrade_text = """
⚠️ *Tontonan gratis Anda telah habis!*

Upgrade ke premium untuk menonton tanpa batas:
• 🎟️ 1 Hari - Rp 3.000
• 📅 7 Hari - Rp 10.000  
• 📆 30 Hari - Rp 25.000
• 🎉 1 Tahun - Rp 50.000
                """
                
                keyboard = [
                    [InlineKeyboardButton("💰 Upgrade Premium", callback_data="show_packages")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            traceback.print_exc()
            await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")
            # Fallback: send text message with video URL if available
            if 'episode_url' in locals() and episode_url:
                fallback_text = f"🎬 {drama['title']} - Episode 1\n📺 Status: {watch_status}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                await query.message.reply_text(fallback_text)
            else:
                await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")

    async def stream_episode_callback(self, query, drama_id: str, episode_num: int, user_id: int):
        """Handle episode streaming"""
        # Check watch count first
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        
        # Check if user has premium
        is_premium = await self.check_user_premium_status(user_id)
        
        if not is_premium and remaining_watches <= 0:
            # Show premium packages if no free watches left
            await self.show_packages_callback(query)
            return
        drama = await self.get_drama_details(drama_id)
        # Get episode URL from S3
        episode_url = await self.get_episode_url(drama_id, episode_num, drama.get('title', 'Unknown'))
        if not episode_url:
            await query.edit_message_text("❌ Episode tidak tersedia.")
            return

        # Increment watch count if not premium
        if not is_premium:
            await self.increment_watch_count(user_id)
            remaining_watches -= 1

        # Send streaming message
        watch_status = "Premium" if is_premium else f"Gratis ({remaining_watches} tersisa)"
        text = f"""
🎬 Episode {episode_num} - Sedang diproses...

📺 Status: {watch_status}
📹 Link streaming akan segera dikirim!
        """

        await query.edit_message_text(text)

        # Send video file
        try:
            caption = f"🎬 Episode {episode_num}\n📺 Status: {watch_status}\n\nSelamat menonton! 🎭"
            await query.message.reply_video(
                video=episode_url,
                caption=caption,
                supports_streaming=True,
                protect_content=True,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30
            )
            
            # Add buttons based on premium status
            keyboard = []
            
            # Always add "Selanjutnya" button
            keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_{episode_num}")])
            
            # Add episode selection for premium users
            if is_premium:
                actual_episodes = await self.get_episode_count_from_s3(drama_id)
                keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])
            
            # Always add home button
            keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Episode berikutnya:", reply_markup=reply_markup)
            
            # Show upgrade message if this was last free watch
            if not is_premium and remaining_watches == 0:
                upgrade_text = """
⚠️ *Tontonan gratis Anda telah habis!*

Upgrade ke premium untuk menonton tanpa batas:
• 🎟️ 1 Hari - Rp 3.000
• 📅 7 Hari - Rp 10.000  
• 📆 30 Hari - Rp 25.000
• 🎉 1 Tahun - Rp 50.000
                """
                
                keyboard = [
                    [InlineKeyboardButton("💰 Upgrade Premium", callback_data="show_packages")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            traceback.print_exc()
            await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")
            # Fallback: send text message with video URL if available
            if 'episode_url' in locals() and episode_url:
                drama = await self.get_drama_details(drama_id)
                fallback_text = f"🎬 {drama.get('title', 'Unknown')} - Episode {episode_num}\n📺 Status: {watch_status}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                await query.message.reply_text(fallback_text)
            else:
                await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")

    async def next_episode_callback(self, query, drama_id: str, current_episode: int, user_id: int):
        """Handle next episode streaming"""
        next_episode = current_episode + 1
        
        # Get drama details to check if next episode exists
        drama = await self.get_drama_details(drama_id)
        if not drama:
            await query.edit_message_text("❌ Drama tidak ditemukan.")
            return
        
        # Check if next episode exists (assuming max 12 episodes for now)
        if next_episode > drama.get('episodes', 0):
            await query.edit_message_text("🎬 Sudah mencapai episode terakhir!\n\nGunakan /start untuk kembali ke menu utama.")
            return
        
        # Check watch count first
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        
        # Check if user has premium
        is_premium = await self.check_user_premium_status(user_id)
        
        if not is_premium and remaining_watches <= 0:
            # Force payment - redirect to package selection
            text = """
💰 *TONTONAN GRATIS HABIS!*

Untuk melanjutkan menonton episode berikutnya, Anda perlu upgrade ke premium.

Pilih paket yang sesuai:
            """
            
            keyboard = [
                [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
                [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
                [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
                [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")],
                [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        
        # Get next episode URL from S3
        episode_url = await self.get_episode_url(drama_id, next_episode, drama.get('title', 'Unknown'))
        if not episode_url:
            await query.edit_message_text(f"❌ Episode {next_episode} tidak tersedia.")
            return

        # Increment watch count if not premium
        if not is_premium:
            await self.increment_watch_count(user_id)
            remaining_watches -= 1

        # Send streaming message
        watch_status = "Premium" if is_premium else f"Gratis ({remaining_watches} tersisa)"
        text = f"""
🎬 {drama.get('title', 'Unknown')} - Episode {next_episode}

📺 Status: {watch_status}
📹 Link streaming sedang diproses...
        """

        await query.edit_message_text(text)

        # Send video file
        try:
            caption = f"🎬 {drama.get('title', 'Unknown')} - Episode {next_episode}\n📺 Status: {watch_status}\n\nSelamat menonton! 🎭"
            await query.message.reply_video(
                video=episode_url,
                caption=caption,
                supports_streaming=True,
                protect_content=True,
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30
            )
            
            # Add buttons based on premium status
            keyboard = []
            
            # Always add "Selanjutnya" button
            keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_{next_episode}")])
            
            # Add episode selection for premium users
            if is_premium:
                actual_episodes = await self.get_episode_count_from_s3(drama_id)
                keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])
            
            # Always add home button
            keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Episode berikutnya:", reply_markup=reply_markup)
            
            # Show upgrade message if this was last free watch
            if not is_premium and remaining_watches == 0:
                upgrade_text = """
⚠️ *Tontonan gratis Anda telah habis!*

Upgrade ke premium untuk menonton tanpa batas:
• 🎟️ 1 Hari - Rp 3.000
• 📅 7 Hari - Rp 10.000  
• 📆 30 Hari - Rp 25.000
• 🎉 1 Tahun - Rp 50.000
                """
                
                keyboard = [
                    [InlineKeyboardButton("💰 Upgrade Premium", callback_data="show_packages")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.message.reply_text(upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            traceback.print_exc()
            await query.message.reply_text(f"❌ Gagal memuat video: {str(e)}")
            # Fallback: send text message with video URL if available
            if 'episode_url' in locals() and episode_url:
                fallback_text = f"🎬 {drama.get('title', 'Unknown')} - Episode {next_episode}\n📺 Status: {watch_status}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                await query.message.reply_text(fallback_text)
            else:
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

    async def get_total_eps(self, drama_id: str) -> int:
        """Get total episodes for a drama from S3"""
                
        # Replace these placeholders with your credentials
        # Initialize the S3 client
        _s3_client = boto3.client(
            's3',
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            endpoint_url=S3_ENDPOINT
        )

        bucket_name = 'drama'
        prefix = f"{drama_id}/"
        try:
            response = _s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter='/')
            folders = response.get('CommonPrefixes', [])
            total_folders = len(folders)
            return total_folders
        except Exception as e:
            print(f"Error: {e}")

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
        payment_code = self.generate_payment_code(user_id, package_type)
        
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

    async def select_episodes_callback(self, query, drama_id: str, user_id: int):
        """Handle episode selection for premium users"""
        # Check if user is premium
        is_premium = await self.check_user_premium_status(user_id)
        if not is_premium and user_id not in ADMIN_WHITELIST:
            await query.edit_message_text("❌ Fitur ini hanya untuk pengguna premium.")
            return
        
        # Get drama details
        drama = await self.get_drama_details(drama_id)
        if not drama:
            await query.edit_message_text("❌ Drama tidak ditemukan.")
            return
        
        # Get actual episode count from S3
        actual_episodes = await self.get_episode_count_from_s3(drama_id)
        
        text = f"""
🎬 *{drama.get('title', 'Unknown')}*

📺 Pilih episode yang ingin ditonton:
📊 Total Episode: {actual_episodes}
        """
        
        keyboard = []
        
        # Create episode buttons (max 10 per row for better layout)
        episode_buttons = []
        for i in range(1, actual_episodes + 1):
            episode_buttons.append(
                InlineKeyboardButton(f"{i}", callback_data=f"episode_{drama_id}_{i}")
            )
            # Create new row every 5 episodes
            if len(episode_buttons) == 5:
                keyboard.append(episode_buttons)
                episode_buttons = []
        
        # Add remaining buttons
        if episode_buttons:
            keyboard.append(episode_buttons)
        
        # Add back button
        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data=f"drama_{drama_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def get_episode_url(self, drama_id: str, episode_num: int, drama_title: str) -> str:
        """Get presigned URL for episode video"""
        return await self.generate_presigned_url(drama_id, episode_num, drama_title)
    # Database operations
    async def generate_presigned_url(self, drama_id: str, episode_num: int, drama_title) -> str:
        """Generate presigned URL for S3 video file"""
        try:
            bucket_name = 'drama'
            
            # Create S3 key based on drama structure
            # Format: drama_id/episode_X/Drama_Title_ep_X.mp4
            if drama_title:
                # Clean drama title for filename
                clean_title = drama_title.replace(' ', '_').replace('/', '_').replace('\\', '_')
                key = f"{drama_id}/episode_{episode_num}/{clean_title}_ep_{episode_num}.mp4"
            
            
            # Generate presigned URL (expires in 1 hour)
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=3600  # URL expires in 1 hour
            )
            
            print(f"Generated presigned URL for {key}: {presigned_url}")
            return presigned_url
            
        except Exception as e:
            print(f"Error generating presigned URL: {e}")
            # Fallback to direct S3 URL
            return f"{S3_ENDPOINT}/{bucket_name}/{drama_id}/episode_{episode_num}/episode_{episode_num}.mp4"

    async def get_user_watch_count(self, user_id: int) -> dict:
        """Get user's watch count information"""
        # Check if user is in admin whitelist - unlimited access
        if user_id in ADMIN_WHITELIST:
            return {'used': 0, 'limit': 9999}
        
        if not supabase:
            return {'used': 0, 'limit': 1}
        
        try:
            result = supabase.table('users').select('free_watches_used, free_watches_limit, last_watch_reset').eq('telegram_id', user_id).execute()
            if result.data:
                user_data = result.data[0]
                current_time = datetime.now()
                
                # Check if we need to reset weekly watch count
                last_reset = user_data.get('last_watch_reset')
                if last_reset:
                    last_reset_time = datetime.fromisoformat(last_reset.replace('Z', '+00:00'))
                    # Reset if more than 7 days have passed
                    if (current_time - last_reset_time).days >= 7:
                        # Reset watch count and update last reset time
                        supabase.table('users').update({
                            'free_watches_used': 0,
                            'last_watch_reset': current_time.isoformat()
                        }).eq('telegram_id', user_id).execute()
                        return {
                            'used': 0,
                            'limit': user_data['free_watches_limit'] or 1
                        }
                
                return {
                    'used': user_data['free_watches_used'] or 0,
                    'limit': user_data['free_watches_limit'] or 1
                }
            return {'used': 0, 'limit': 1}
        except Exception as e:
            print(f"Error getting watch count: {e}")
            return {'used': 0, 'limit': 1}

    async def increment_watch_count(self, user_id: int):
        """Increment user's watch count"""
        # Skip incrementing for whitelisted users
        if user_id in ADMIN_WHITELIST:
            return
        
        if not supabase:
            return
        
        try:
            # First get current watch count
            result = supabase.table('users').select('free_watches_used').eq('telegram_id', user_id).execute()
            if result.data:
                current_count = result.data[0]['free_watches_used'] or 0
                new_count = current_count + 1
                
                # Update with incremented value
                supabase.table('users').update({
                    'free_watches_used': new_count,
                    'last_watch_reset': datetime.now().isoformat(),
                    'last_active': datetime.now().isoformat()
                }).eq('telegram_id', user_id).execute()
        except Exception as e:
            print(f"Error incrementing watch count: {e}")

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
        """Check if user has active premium or is whitelisted"""
        # Check if user is in admin whitelist
        if user_id in ADMIN_WHITELIST:
            return True

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
                    'free_watches_used': 0,
                    'free_watches_limit': 1,
                    'last_watch_reset': datetime.now().isoformat(),
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

    async def get_featured_dramas(self, limit: int = 3):
        """Get featured dramas from Drama table"""

        if not supabase:
            return []

        try:
            # Get random dramas from Drama table, ordered by created_at desc to get newest
            result = supabase.table('Drama').select('id, book_name, book_name_en, cover, chapter_id').eq('has_downloaded', True).order('created_at', desc=True).limit(limit).execute()
            print(result)
            # Format data to match expected structure
            dramas = []
            for drama in result.data:
                dramas.append({
                    'id': str(drama['id']),
                    'title': drama['book_name'],
                    'book_name': drama['book_name'],
                    'book_name_en': drama['book_name_en'],
                    'cover': drama['cover'],
                    'chapter_id': drama['chapter_id'],
                    'episodes': 12  # Default episodes, can be calculated if needed
                })
            
            return dramas
        except Exception as e:
            print(f"Error getting featured dramas: {e}")
            return []

    async def get_available_dramas(self):
        """Get available dramas from Drama table"""
        print("Fetching available dramas...")
        if not supabase:
            return []

        try:
            # Get dramas from actual Drama table
            result = supabase.table('Drama').select('id, book_name, book_name_en, cover, chapter_id').eq('has_downloaded', True).order('created_at', desc=True).limit(20).execute()
            print("Available dramas:", result)
            # Format data to match expected structure
            dramas = []
            for drama in result.data:
                dramas.append({
                    'id': str(drama['id']),
                    'title': drama['book_name'],
                    'book_name': drama['book_name'], 
                    'book_name_en': drama['book_name_en'],
                    'cover': drama['cover'],
                    'chapter_id': drama['chapter_id'],
                    'episodes': 12,  # Default episodes
                    'genre': 'Drama',  # Default genre
                    'rating': 9.0  # Default rating
                })
            
            return dramas
        except Exception as e:
            print(f"Error getting dramas: {e}")
            return []

    async def get_drama_details(self, drama_id: str):
        """Get drama details from Drama table"""
        if not supabase:
            return None

        try:
            # Get drama from Drama table by id
            result = supabase.table('Drama').select('*').eq('id', int(drama_id)).execute()
            
            if result.data:
                drama = result.data[0]
                # Get actual episode count from S3
                actual_episodes = await self.get_episode_count_from_s3(drama_id)
                return {
                    'id': str(drama['id']),
                    'title': drama['book_name'],
                    'book_name': drama['book_name'],
                    'book_name_en': drama['book_name_en'], 
                    'cover': drama['cover'],
                    'chapter_id': drama['chapter_id'],
                    'description': f"Drama menarik tentang {drama['book_name']}",
                    'episodes': actual_episodes
                }
            return None
        except Exception as e:
            print(f"Error getting drama details: {e}")
            return None

    async def get_episode_count_from_s3(self, drama_id: str) -> int:
        """Get actual episode count from S3 bucket"""
        return await self.get_total_eps(drama_id)
            
    # Callback handlers
    async def show_dramas_callback(self, query):
        """Handle show dramas callback"""
        user_id = query.from_user.id
        
        # Get user's watch count
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used
        
        # Check premium status
        is_premium = await self.check_user_premium_status(user_id)

        dramas = await self.get_available_dramas()

        if not dramas:
            await query.edit_message_text("❌ Maaf, tidak ada drama tersedia saat ini.")
            return

        if is_premium:
            if user_id in ADMIN_WHITELIST:
                text = "📺 Drama Tersedia\n👑 Status: Admin (Unlimited)\n\nPilih drama yang ingin ditonton:"
            else:
                text = "📺 Drama Tersedia\n🌟 Status: Premium (Unlimited)\n\nPilih drama yang ingin ditonton:"
        else:
            text = f"📺 Drama Tersedia\n📺 Tontonan gratis: {remaining_watches}/{free_watches_limit}\n\nPilih drama yang ingin ditonton:"

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
        user_id = user.id
        
        # Get user's watch count
        watch_info = await self.get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used

        # Check premium status
        is_premium = await self.check_user_premium_status(user_id)

        # Get 3 random dramas to display
        dramas = await self.get_featured_dramas(3)
        
        if is_premium:
            if user_id in ADMIN_WHITELIST:
                status_text = "👑 Admin (Unlimited)"
            else:
                status_text = "🌟 Premium (Unlimited)"
            welcome_text = f"""
🎬 Selamat datang kembali!

👤 User: {user.first_name}
{status_text}

📺 *Drama Pilihan Hari Ini:*
            """
        else:
            welcome_text = f"""
🎬 Selamat datang kembali!

👤 User: {user.first_name}
📺 Tontonan gratis: {remaining_watches}/{free_watches_limit}

📺 *Drama Pilihan Hari Ini:*
            """
        
        if dramas:
            for i, drama in enumerate(dramas, 1):
                welcome_text += f"\n{i}. 🎭 {drama['book_name']}"
        else:
            welcome_text += "\n❌ Tidak ada drama tersedia saat ini."
        
        if remaining_watches > 0:
            welcome_text += "\n\nSilakan pilih menu di bawah:"
        else:
            welcome_text += "\n\n⚠️ Tontonan gratis habis! Upgrade ke premium untuk lanjut menonton."

        keyboard = []
        
        # Add numbered buttons for each featured drama if user has remaining watches
        if dramas and remaining_watches > 0:
            drama_buttons = []
            for i, drama in enumerate(dramas, 1):
                drama_buttons.append(
                    InlineKeyboardButton(str(i), callback_data=f"featured_drama_{drama['id']}")
                )
            keyboard.append(drama_buttons)
            
        keyboard.extend([
            [InlineKeyboardButton("📺 Semua Drama", callback_data="show_dramas")],
            [InlineKeyboardButton("💰 Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

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
        try:
            self.application.run_polling()
        except RuntimeError as e:
            if "no current event loop" in str(e):
                # Fix for Python 3.14 event loop issue
                import asyncio
                asyncio.set_event_loop(asyncio.new_event_loop())
                self.application.run_polling()
            else:
                raise


# Initialize and run bot
if __name__ == '__main__':
    bot = DramaBot()
    bot.run()