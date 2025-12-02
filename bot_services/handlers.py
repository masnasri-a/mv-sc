from typing import Dict, List, Optional, Any
import asyncio, os
import requests
import aiohttp
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, CallbackQuery, BotCommand
from telegram.ext import ContextTypes
from bot_services.database import (
    get_user_watch_count, increment_watch_count, check_user_premium_status,
    create_or_update_user, get_featured_dramas, get_available_dramas,
    get_drama_details, search_dramas_by_name, generate_payment_code,
    get_episode_count_from_s3, get_telegram_file_id, store_telegram_file_id,
    get_user_premium_expiry
)
from bot_services.utils import get_episode_url_with_retry, safe_edit_message, generate_presigned_url_from_key, safe_reply_text
from bot_services.config import ADMIN_WHITELIST
from io import BytesIO

async def send_video_with_cache(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                               s3_url_or_key: str, drama_title: str, episode_number: int, 
                               chat_id: int, message_id: int = None):
    """Send video using Telegram file_id caching system"""
    try:
        # Extract S3 key from URL if it's a full URL
        if s3_url_or_key.startswith('http'):
            # Extract key from presigned URL: https://s3.nevaobjects.id/drama/41000111481/episode_1/filename.mp4?...
            s3_key = s3_url_or_key.split('/drama/')[1].split('?')[0]  # Gets: 41000111481/episode_1/filename.mp4
        else:
            s3_key = s3_url_or_key
        
        # Check if we have a cached Telegram file_id
        cached_file_id = await get_telegram_file_id(s3_key)
        
        if cached_file_id:
            print(f"Using cached file_id: {repr(cached_file_id)} (length: {len(cached_file_id)})")
            try:
                # Use cached file_id for faster sending
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=cached_file_id,
                    caption=f"🎬 {drama_title} - Episode {episode_number}",
                    reply_to_message_id=message_id
                )
                return
            except Exception as cache_error:
                print(f"Cached file_id failed: {cache_error}, falling back to upload")
                # If cached file_id fails, continue to upload
        
        # No cache - download from S3 and upload to Telegram
        try:
            # Generate direct S3 URL for download
            if s3_url_or_key.startswith('http'):
                s3_url = s3_url_or_key
            else:
                s3_url = await generate_presigned_url_from_key(s3_url_or_key)
            
            # Try to send video directly using S3 URL (more efficient for large files)
            print(f"Trying direct URL upload for {s3_url}...")
            try:
                sent_message = await context.bot.send_video(
                    chat_id=chat_id,
                    video=s3_url,
                    caption=f"🎬 {drama_title} - Episode {episode_number}",
                    reply_to_message_id=message_id,
                    read_timeout=300,  # 5 minutes timeout
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=300
                )
                print("Direct URL upload successful")
                
                # Cache the file_id for future use
                if sent_message.video and sent_message.video.file_id:
                    file_id_to_store = sent_message.video.file_id
                    print(f"Direct upload successful. Storing file_id: {repr(file_id_to_store)} (length: {len(file_id_to_store)})")
                    await store_telegram_file_id(s3_key, file_id_to_store)
                return
                
            except Exception as url_error:
                print(f"Direct URL upload failed: {url_error}, falling back to download/upload")
                
            # Fallback: Download and upload the video
            print(f"Downloading video for upload: {s3_key}...")
            # Download video from S3 with longer timeout
            response = requests.get(s3_url, stream=True, timeout=120)  # 2 minutes timeout
            response.raise_for_status()
            
            # Read video data into memory (for smaller files)
            video_data = BytesIO()
            total_downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                video_data.write(chunk)
                total_downloaded += len(chunk)
                if total_downloaded > 50 * 1024 * 1024:  # 50MB limit
                    raise Exception("Video file too large (>50MB)")
            
            video_data.seek(0)
            print(f"Downloaded {total_downloaded} bytes, uploading to Telegram...")
            
            # Upload to Telegram to get file_id
            sent_message = await context.bot.send_video(
                chat_id=chat_id,
                video=video_data,
                caption=f"🎬 {drama_title} - Episode {episode_number}",
                reply_to_message_id=message_id,
                read_timeout=300,  # 5 minutes timeout
                write_timeout=300,
                connect_timeout=60,
                pool_timeout=300
            )
            
            # Cache the file_id for future use
            if sent_message.video:
                file_id_to_store = sent_message.video.file_id
                print(f"Upload successful. Storing file_id: {repr(file_id_to_store)} (length: {len(file_id_to_store)})")
                await store_telegram_file_id(s3_key, file_id_to_store)
                
        except Exception as e:
            print(f"Failed to download/upload video {s3_key}: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to load video. Please try again later.",
                reply_to_message_id=message_id
            )
            
    except Exception as e:
        print(f"Error in send_video_with_cache: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ An error occurred while sending the video.",
            reply_to_message_id=message_id
        )

class BotHandlers:
    """Handles all bot command and callback operations"""

    def __init__(self, application):
        self.application = application

    async def setup_bot_commands(self) -> None:
        """Setup bot command menu for Telegram"""
        commands = [
            BotCommand("start", "🏠 Mulai menggunakan bot"),
            BotCommand("dramas", "📺 Lihat semua drama tersedia"),
            BotCommand("cari", "🔍 Cari drama berdasarkan nama"),
            BotCommand("commands", "📋 Lihat semua perintah"),
            BotCommand("help", "ℹ️ Bantuan cara penggunaan"),
        ]
        await self.application.bot.set_my_commands(commands)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command"""
        user = update.effective_user
        user_id: int = user.id
        print("User started bot:", user_id, user.username)

        # Setup bot commands on first start
        commands = [
            BotCommand("start", "🏠 Mulai menggunakan bot"),
            BotCommand("dramas", "📺 Lihat semua drama tersedia"),
            BotCommand("cari", "🔍 Cari drama berdasarkan nama"),
            BotCommand("commands", "📋 Lihat semua perintah"),
            BotCommand("help", "ℹ️ Bantuan cara penggunaan"),
        ]
        await self.application.bot.set_my_commands(commands)

        # Create or update user in database
        await create_or_update_user(user_id, user.username, user.first_name)

        # Get user's watch count
        watch_info: Dict[str, int] = await get_user_watch_count(user_id)
        free_watches_used: int = watch_info['used']
        free_watches_limit: int = watch_info['limit']
        remaining_watches: int = free_watches_limit - free_watches_used
        print("User watch info:", watch_info)
        # Get 3 random dramas to display
        dramas = await get_featured_dramas(3)
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
            [InlineKeyboardButton("🔍 Cari Drama", callback_data="search_dramas")],
            [InlineKeyboardButton("💰 Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send with first drama's cover if available
        if dramas and dramas[0].get('cover'):
            await update.message.reply_photo(
                photo=dramas[0]['cover'],
                caption=welcome_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await safe_reply_text(update.message, welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command"""
        help_text: str = """
🎬 *DRAMA CINA GRATIS BOT*

📋 *Perintah yang Tersedia:*
• `/start` - Mulai menggunakan bot
• `/dramas` - Lihat semua drama tersedia
• `/cari [nama]` - Cari drama berdasarkan nama
• `/commands` - Lihat semua perintah
• `/help` - Bantuan cara penggunaan

📺 *Cara Penggunaan:*
1. Gunakan /start untuk memulai
2. Pilih drama yang ingin ditonton
3. Tonton gratis hingga limit tercapai
4. Untuk tontonan lebih banyak, upgrade premium

🔍 *Cara Mencari Drama:*
• Ketik `/cari suara hati`
• Atau gunakan tombol "🔍 Cari Drama"
• Pencarian tidak case-sensitive

📺 *Fitur:*
• Streaming drama Cina terbaru
• Kualitas HD
• Subtitle Indonesia
• Tontonan gratis 1x per minggu
• Pencarian drama by nama

💰 *Premium:*
Untuk akses unlimited, hubungi @nanassssa

❓ *Bantuan:*
Kirim pesan ke admin jika ada masalah
        """
        await safe_reply_text(update.message, help_text, parse_mode='Markdown')

    async def search_dramas(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cari command for searching dramas"""
        user_id: int = update.effective_user.id

        # Get the search query from command arguments
        search_query: str = ' '.join(context.args) if context.args else ''

        if not search_query:
            help_text: str = """
🔍 *CARA MENCARI DRAMA*

Gunakan perintah:
`/cari [nama drama]`

Contoh:
• `/cari suara hati`
• `/cari penguasa yang bangkit`
• `/cari sekali rayu`

Atau gunakan tombol di bawah untuk mencari:
            """

            keyboard = [
                [InlineKeyboardButton("🔍 Cari Drama", callback_data="search_dramas")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_reply_text(update.message, help_text, reply_markup=reply_markup, parse_mode='Markdown')
            return

        # Search for dramas
        search_results: List[Dict[str, Any]] = await search_dramas_by_name(search_query)

        if not search_results:
            no_result_text: str = f"""
🔍 *HASIL PENCARIAN*

Tidak ditemukan drama dengan kata kunci: "{search_query}"

💡 Tips pencarian:
• Coba kata kunci yang lebih pendek
• Periksa ejaan kata kunci
• Gunakan kata kunci utama saja
            """
            keyboard = [
                [InlineKeyboardButton("🔍 Cari Lagi", callback_data="search_dramas")],
                [InlineKeyboardButton("📺 Semua Drama", callback_data="show_dramas")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_reply_text(update.message, no_result_text, reply_markup=reply_markup, parse_mode='Markdown')
            return

        # Display search results
        await self.display_search_results(update, search_query, search_results, user_id)

    async def show_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show all available commands"""
        commands_text: str = """
📋 *DAFTAR PERINTAH BOT*

🏠 `/start`
Mulai menggunakan bot dan kembali ke menu utama

📺 `/dramas`
Lihat semua drama yang tersedia untuk ditonton

🔍 `/cari [nama drama]`
Cari drama berdasarkan nama (tidak case-sensitive)
Contoh: `/cari suara hati`

📋 `/commands`
Tampilkan daftar perintah ini

ℹ️ `/help`
Bantuan lengkap cara menggunakan bot

💡 *Tips:*
• Gunakan tombol menu untuk navigasi yang mudah
• Ketik nama drama langsung untuk mencari
• Upgrade premium untuk akses unlimited

🎬 Selamat menikmati drama!
        """

        keyboard = [
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")],
            [InlineKeyboardButton("ℹ️ Bantuan Lengkap", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_reply_text(update.message, commands_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_dramas(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show available dramas"""
        user_id: int = update.effective_user.id

        # Get user's watch count
        watch_info: Dict[str, int] = await get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used

        # Check premium status
        is_premium = await check_user_premium_status(user_id)

        # Get dramas from database
        dramas = await get_available_dramas()

        if not dramas:
            await safe_reply_text(update.message, "❌ Maaf, tidak ada drama tersedia saat ini.")
            return

        if is_premium:
            expiry_date = await get_user_premium_expiry(user_id)
            expiry_text = f" - Expires: {expiry_date}" if expiry_date else ""
            text = f"📺 Drama Tersedia\n🌟 Status: Premium (Unlimited){expiry_text}\n\nPilih drama yang ingin ditonton:"
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

        await safe_reply_text(update.message, text, reply_markup=reply_markup)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards"""
        query: CallbackQuery = update.callback_query
        await query.answer()

        user_id: int = query.from_user.id
        data: str = query.data

        if data == "show_dramas":
            await self.show_dramas_callback(query)
        elif data == "search_dramas":
            await self.search_dramas_callback(query)
        elif data == "commands":
            await self.show_commands_callback(query)
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
            await self.select_featured_drama_callback(query, drama_id, user_id, context)
        elif data.startswith("episode_"):
            _, drama_id, episode_num = data.split("_")
            await self.stream_episode_callback(query, drama_id, int(episode_num), user_id, context)
        elif data.startswith("next_episode_"):
            _, _, drama_id, current_episode = data.split("_")
            await self.next_episode_callback(query, drama_id, int(current_episode), user_id, context)
        elif data.startswith("copy_code_"):
            payment_code = data.split("_")[2]
            await query.answer(f"Kode pembayaran {payment_code} berhasil dicopy!", show_alert=True)
        elif data.startswith("select_episodes_"):
            drama_id = data.split("_")[2]
            await self.select_episodes_callback(query, drama_id, user_id)
        elif data.startswith("package_"):
            package_type = data.split("_")[1]
            await self.select_package_callback(query, package_type, user_id)
        elif data == "check_subscription_status":
            await self.check_subscription_status_callback(query, user_id)

    async def select_drama_callback(self, query: CallbackQuery, drama_id: str, user_id: int) -> None:
        """Handle drama selection"""
        # Get drama details
        drama: Optional[Dict[str, Any]] = await get_drama_details(drama_id)
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

        # For non-premium users, only show episode 1
        max_episodes = 1 if not await check_user_premium_status(user_id) and user_id not in ADMIN_WHITELIST else drama.get('episodes', 0)

        keyboard = []
        for i in range(1, min(max_episodes + 1, 11)):  # Show max 10 episodes or only episode 1 for non-premium
            keyboard.append([
                InlineKeyboardButton(f"Episode {i}", callback_data=f"episode_{drama_id}_{i}")
            ])

        if drama.get('episodes', 0) > 10:
            keyboard.append([InlineKeyboardButton("➡️ Next Episodes", callback_data=f"episodes_page_{drama_id}_2")])

        keyboard.append([InlineKeyboardButton("⬅️ Kembali", callback_data="show_dramas")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Check if the original message has text or is a photo
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            if "no text in the message to edit" in str(e).lower():
                # If original message was a photo, edit the caption instead
                try:
                    await query.edit_message_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception:
                    # If that fails too, send a new message
                    await safe_reply_text(query.message, text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                # For other errors, try sending a new message
                await safe_reply_text(query.message, text, reply_markup=reply_markup, parse_mode='Markdown')

    async def select_featured_drama_callback(self, query: CallbackQuery, drama_id: str, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle featured drama selection - directly stream episode 1"""
        # Answer callback immediately to prevent timeout
        await query.answer()
        
        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n📺 Menyiapkan episode pertama...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return
        
        try:
            # Check watch count first
            watch_info: Dict[str, int] = await get_user_watch_count(user_id)
            print("Watch info for featured drama:", watch_info)
            free_watches_used: int = watch_info['used']
            free_watches_limit: int = watch_info['limit']
            remaining_watches: int = free_watches_limit - free_watches_used

            # Check if user has premium
            is_premium: bool = await check_user_premium_status(user_id)

            if not is_premium and remaining_watches <= 0:
                # Show premium packages if no free watches left
                await self.show_packages_callback(query)
                await wait_message.edit_text("❌ Tontonan gratis habis! Silakan upgrade premium.", parse_mode='Markdown')
                return

            # Get drama details
            drama = await get_drama_details(drama_id)
            if not drama:
                await wait_message.edit_text("❌ Drama tidak ditemukan.")
                return

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📁 Mengambil link video...", parse_mode='Markdown')

            # Get episode 1 URL from S3
            episode_url = await get_episode_url_with_retry(drama_id, 1)
            if not episode_url:
                await wait_message.edit_text("❌ Episode tidak tersedia atau sedang dalam proses upload.")
                return

            # Increment watch count if not premium
            if not is_premium:
                await increment_watch_count(user_id)
                remaining_watches -= 1

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📹 Mengirim video...", parse_mode='Markdown')

            # Send video file
            try:
                if not episode_url:
                    await wait_message.edit_text("❌ Video tidak dapat dimuat. Silakan coba lagi nanti.")
                    return

                # Use the new caching system to send video
                await send_video_with_cache(
                    query, context, episode_url, 
                    drama.get('title', 'Unknown'), 1, 
                    query.message.chat_id, wait_message.message_id
                )

                # Delete the wait message since video was sent successfully
                await wait_message.delete()

                # Add buttons based on premium status
                keyboard = []

                # Only add "Selanjutnya" button for premium users on episode 1
                if is_premium:
                    keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_1")])
                else:
                    # Add upgrade button instead of next for non-premium users
                    keyboard.append([InlineKeyboardButton("🔓 Unlock Episode 2+", callback_data="show_packages")])

                # Add episode selection for premium users
                if is_premium:
                    actual_episodes = await get_episode_count_from_s3(drama_id)
                    keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])

                # Always add home button
                keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await safe_reply_text(query.message, "Episode berikutnya:", reply_markup=reply_markup)

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

                    await safe_reply_text(query.message, upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')

            except Exception as e:
                import traceback
                traceback.print_exc()
                await wait_message.edit_text(f"❌ Gagal memuat video: {str(e)}")
                # Fallback: send text message with video URL if available
                if 'episode_url' in locals() and episode_url:
                    fallback_text = f"🎬 {drama['title']} - Episode 1\n📺 Status: {'Premium' if is_premium else f'Gratis ({remaining_watches} tersisa)'}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                    await safe_reply_text(query.message, fallback_text)
                else:
                    await safe_reply_text(query.message, f"❌ Gagal memuat video: {str(e)}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

    async def stream_episode_callback(self, query: CallbackQuery, drama_id: str, episode_num: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle episode streaming"""
        # Answer callback immediately to prevent timeout
        await query.answer()
        
        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n📺 Menyiapkan episode...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return
        
        try:
            # Check watch count first
            watch_info: Dict[str, int] = await get_user_watch_count(user_id)
            free_watches_used: int = watch_info['used']
            free_watches_limit: int = watch_info['limit']
            remaining_watches: int = free_watches_limit - free_watches_used

            # Check if user has premium
            is_premium: bool = await check_user_premium_status(user_id)

            # Block non-premium users from episode 2 and beyond
            if not is_premium and episode_num > 1:
                text = """
🔒 *EPISODE PREMIUM*

Episode 2 dan selanjutnya hanya untuk pengguna premium!

💰 Upgrade sekarang untuk menonton semua episode:
                """

                keyboard = [
                    [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
                    [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
                    [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
                    [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await wait_message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return

            if not is_premium and remaining_watches <= 0:
                # Show premium packages if no free watches left
                await self.show_packages_callback(query)
                await wait_message.edit_text("❌ Tontonan gratis habis! Silakan upgrade premium.", parse_mode='Markdown')
                return
            
            drama = await get_drama_details(drama_id)
            
            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📁 Mengambil link video...", parse_mode='Markdown')
            
            # Get episode URL from S3
            episode_url = await get_episode_url_with_retry(drama_id, episode_num)
            if not episode_url:
                await wait_message.edit_text("❌ Episode tidak tersedia.")
                return

            # Increment watch count if not premium
            if not is_premium:
                await increment_watch_count(user_id)
                remaining_watches -= 1

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n Mengirim video...", parse_mode='Markdown')

            # Send video file
            try:
                caption = f"🎬 Episode {episode_num}\n📺 Status: {'Premium' if is_premium else f'Gratis ({remaining_watches} tersisa)'}\n\nSelamat menonton! 🎭"
                
                # Use the new caching system to send video
                await send_video_with_cache(
                    query, context, episode_url, 
                    drama.get('title', 'Unknown'), episode_num, 
                    query.message.chat_id, wait_message.message_id
                )

                # Delete the wait message since video was sent successfully
                await wait_message.delete()

                # Add buttons based on premium status
                keyboard = []

                # Only add "Selanjutnya" button for premium users
                if is_premium:
                    keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_{episode_num}")])
                elif episode_num == 1:
                    # For non-premium users on episode 1, show upgrade button instead
                    keyboard.append([InlineKeyboardButton("🔓 Unlock Episode 2+", callback_data="show_packages")])

                # Add episode selection for premium users
                if is_premium:
                    actual_episodes = await get_episode_count_from_s3(drama_id)
                    keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])

                # Always add home button
                keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await safe_reply_text(query.message, "Episode berikutnya:", reply_markup=reply_markup)

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

                    await safe_reply_text(query.message, upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')

            except Exception as e:
                import traceback
                traceback.print_exc()
                await wait_message.edit_text(f"❌ Gagal memuat video: {str(e)}")
                # Fallback: send text message with video URL if available
                if 'episode_url' in locals() and episode_url:
                    drama = await get_drama_details(drama_id)
                    fallback_text = f"🎬 {drama.get('title', 'Unknown')} - Episode {episode_num}\n📺 Status: {'Premium' if is_premium else f'Gratis ({remaining_watches} tersisa)'}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                    await safe_reply_text(query.message, fallback_text)
                else:
                    await safe_reply_text(query.message, f"❌ Gagal memuat video: {str(e)}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

    async def next_episode_callback(self, query: CallbackQuery, drama_id: str, current_episode: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle next episode streaming"""
        # Answer callback immediately to prevent timeout
        await query.answer()
        
        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n📺 Menyiapkan episode berikutnya...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return
        
        try:
            next_episode: int = current_episode + 1

            # Get drama details to check if next episode exists
            drama: Optional[Dict[str, Any]] = await get_drama_details(drama_id)
            if not drama:
                await wait_message.edit_text("❌ Drama tidak ditemukan.")
                return

            # Check if next episode exists (assuming max 12 episodes for now)
            if next_episode > drama.get('episodes', 0):
                await wait_message.edit_text("🎬 Sudah mencapai episode terakhir!\n\nGunakan /start untuk kembali ke menu utama.")
                return

            # Check watch count first
            watch_info = await get_user_watch_count(user_id)
            free_watches_used = watch_info['used']
            free_watches_limit = watch_info['limit']
            remaining_watches = free_watches_limit - free_watches_used

            # Check if user has premium
            is_premium = await check_user_premium_status(user_id)

            # For non-premium users, block access to episode 2 and beyond
            if not is_premium and next_episode > 1:
                text = """
🔒 *EPISODE PREMIUM*

Episode 2 dan selanjutnya hanya untuk pengguna premium!

💰 Upgrade sekarang untuk menonton semua episode:
                """

                keyboard = [
                    [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
                    [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
                    [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
                    [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")],
                    [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await wait_message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return

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

                await wait_message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')
                return

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📁 Mengambil link video...", parse_mode='Markdown')

            # Get next episode URL from S3
            episode_url = await get_episode_url_with_retry(drama_id, next_episode)
            if not episode_url:
                await wait_message.edit_text(f"❌ Episode {next_episode} tidak tersedia.")
                return

            # Increment watch count if not premium
            if not is_premium:
                await increment_watch_count(user_id)
                remaining_watches -= 1

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📹 Mengirim video...", parse_mode='Markdown')

            # Send video file
            try:
                caption = f"🎬 {drama.get('title', 'Unknown')} - Episode {next_episode}\n📺 Status: {'Premium' if is_premium else f'Gratis ({remaining_watches} tersisa)'}\n\nSelamat menonton! 🎭"
                
                # Use the new caching system to send video
                await send_video_with_cache(
                    query, context, episode_url, 
                    drama.get('title', 'Unknown'), next_episode, 
                    query.message.chat_id, wait_message.message_id
                )

                # Delete the wait message since video was sent successfully
                await wait_message.delete()

                # Add buttons based on premium status
                keyboard = []

                # Always add "Selanjutnya" button
                keyboard.append([InlineKeyboardButton("⏭️ Selanjutnya", callback_data=f"next_episode_{drama_id}_{next_episode}")])

                # Add episode selection for premium users
                if is_premium:
                    actual_episodes = await get_episode_count_from_s3(drama_id)
                    keyboard.append([InlineKeyboardButton("📋 Pilih Episode", callback_data=f"select_episodes_{drama_id}")])

                # Always add home button
                keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await safe_reply_text(query.message, "Episode berikutnya:", reply_markup=reply_markup)

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

                    await safe_reply_text(query.message, upgrade_text, reply_markup=reply_markup, parse_mode='Markdown')

            except Exception as e:
                import traceback
                traceback.print_exc()
                await wait_message.edit_text(f"❌ Gagal memuat video: {str(e)}")
                # Fallback: send text message with video URL if available
                if 'episode_url' in locals() and episode_url:
                    fallback_text = f"🎬 {drama.get('title', 'Unknown')} - Episode {next_episode}\n📺 Status: {'Premium' if is_premium else f'Gratis ({remaining_watches} tersisa)'}\n\n📁 Link Video: {episode_url}\n\nKlik link di atas untuk menonton."
                    await safe_reply_text(query.message, fallback_text)
                else:
                    await safe_reply_text(query.message, f"❌ Gagal memuat video: {str(e)}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

    async def show_packages_callback(self, query: CallbackQuery) -> None:
        """Show premium packages"""
        user_id = query.from_user.id

        # Check if user has pending subscription
        from bot_services.database import get_supabase_client
        supabase = get_supabase_client()
        pending_result = supabase.table('subscriptions').select('id').eq('user_id', user_id).eq('status', 'pending').limit(1).execute()
        has_pending = len(pending_result.data) > 0

        text: str = """
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

💳 *Pembayaran via QRIS*
Bayar langsung via QR Code
        """

        keyboard = [
            [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
            [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
            [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
            [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")]
        ]

        # Add check status button if user has pending subscription
        if has_pending:
            keyboard.append([InlineKeyboardButton("🔍 Cek Status Pembayaran", callback_data="check_subscription_status")])

        keyboard.extend([
            [InlineKeyboardButton("💬 Hubungi Admin", url="https://t.me/admin")],
            [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main")]
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            await safe_reply_text(query.message, text, reply_markup=reply_markup, parse_mode='Markdown')
            
    async def select_package_manual_callback(self, query: CallbackQuery, package_type: str, user_id: int) -> None:
        """Handle package selection"""
        package_info: Dict[str, Dict[str, str]] = {
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
        payment_code = await generate_payment_code(user_id, package_type)

        text = f"""
🎟️ *PAKET {pkg['name'].upper()}*

💰 Harga: {pkg['price']}
⏰ Durasi: {pkg['duration']}
🏷️ Kode Pembayaran: `{payment_code}`

📋 *Cara Pembayaran via Saweria:*

1️⃣ Klik link Saweria di bawah

2️⃣ Donasi sesuai harga paket: {pkg['price']}

3️⃣ Tulis kode pembayaran `{payment_code}` di pesan donasi

4️⃣ Hubungi admin untuk aktivasi: @nanassssa

✅ *Setelah pembayaran berhasil:*
• Akses penuh semua drama
• Streaming tanpa batas
• Kualitas HD
• Update terbaru

❓ Masalah pembayaran? Hubungi @nanassssa
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

    async def select_episodes_callback(self, query: CallbackQuery, drama_id: str, user_id: int) -> None:
        """Handle episode selection for premium users"""
        # Answer callback immediately to prevent timeout
        await query.answer()
        
        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n📋 Mengambil daftar episode...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return
        
        try:
            # Check if user is premium
            is_premium: bool = await check_user_premium_status(user_id)
            if not is_premium and user_id not in ADMIN_WHITELIST:
                await wait_message.edit_text("❌ Fitur ini hanya untuk pengguna premium.")
                return

            # Get drama details
            drama = await get_drama_details(drama_id)
            if not drama:
                await wait_message.edit_text("❌ Drama tidak ditemukan.")
                return

            # Update wait message
            await wait_message.edit_text("⏳ *Sedang memproses...*\n\n📋 Membuat daftar episode...", parse_mode='Markdown')

            # Get actual episode count from S3
            actual_episodes = await get_episode_count_from_s3(drama_id)

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

            await wait_message.edit_text(text, reply_markup=reply_markup, parse_mode='Markdown')

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Terjadi kesalahan: {str(e)}")

    async def show_dramas_callback(self, query: CallbackQuery) -> None:
        """Handle show dramas callback"""
        user_id: int = query.from_user.id

        # Get user's watch count
        watch_info: Dict[str, int] = await get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used

        # Check premium status
        is_premium = await check_user_premium_status(user_id)

        dramas = await get_available_dramas()

        if not dramas:
            await query.edit_message_text("❌ Maaf, tidak ada drama tersedia saat ini.")
            return
        text: str = ""
        if is_premium:
            if user_id in ADMIN_WHITELIST:
                text = "📺 Drama Tersedia\n👑 Status: Admin (Unlimited)\n\nPilih drama yang ingin ditonton:"
            else:
                expiry_date = await get_user_premium_expiry(user_id)
                expiry_text = f" - Expires: {expiry_date}" if expiry_date else ""
                text = f"📺 Drama Tersedia\n🌟 Status: Premium (Unlimited){expiry_text}\n\nPilih drama yang ingin ditonton:"
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

        # Check if the original message has text or is a photo
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            if "no text in the message to edit" in str(e).lower():
                # If original message was a photo, edit the caption instead
                try:
                    await query.edit_message_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception:
                    # If that fails too, send a new message
                    await safe_reply_text(query.message, text, reply_markup=reply_markup)
            else:
                # For other errors, try sending a new message
                await safe_reply_text(query.message, text, reply_markup=reply_markup)

    async def search_dramas_callback(self, query: CallbackQuery) -> None:
        """Handle search dramas callback"""
        search_text: str = """
🔍 *CARI DRAMA*

Kirim nama drama yang ingin Anda cari.

Contoh:
• Ketik: `Suara Hati`
• Ketik: `Penguasa Yang Bangkit`
• Ketik: `Sekali Rayu`

💡 Tips:
• Pencarian tidak sensitif huruf besar/kecil
• Bisa menggunakan sebagian nama drama
• Gunakan kata kunci utama untuk hasil terbaik
        """

        keyboard = [
            [InlineKeyboardButton("📺 Lihat Semua Drama", callback_data="show_dramas")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_edit_message(query, search_text, reply_markup, 'Markdown')

    async def show_commands_callback(self, query: CallbackQuery) -> None:
        """Handle commands callback"""
        commands_text: str = """
📋 *DAFTAR PERINTAH BOT*

🏠 `/start`
Mulai menggunakan bot dan kembali ke menu utama

📺 `/dramas`
Lihat semua drama yang tersedia untuk ditonton

🔍 `/cari [nama drama]`
Cari drama berdasarkan nama (tidak case-sensitive)
Contoh: `/cari suara hati`

📋 `/commands`
Tampilkan daftar perintah ini

ℹ️ `/help`
Bantuan lengkap cara menggunakan bot

💡 *Tips:*
• Gunakan tombol menu untuk navigasi yang mudah
• Ketik nama drama langsung untuk mencari
• Upgrade premium untuk akses unlimited

🎬 Selamat menikmati drama!
        """

        keyboard = [
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")],
            [InlineKeyboardButton("ℹ️ Bantuan Lengkap", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_edit_message(query, commands_text, reply_markup, 'Markdown')

    async def help_callback(self, query: CallbackQuery) -> None:
        """Handle help callback"""
        help_text: str = """
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

        # Check if the original message has text or is a photo
        try:
            await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            if "no text in the message to edit" in str(e).lower():
                # If original message was a photo, edit the caption instead
                try:
                    await query.edit_message_caption(
                        caption=help_text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                except Exception:
                    # If that fails too, send a new message
                    await safe_reply_text(query.message, help_text, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                # For other errors, try sending a new message
                await safe_reply_text(query.message, help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def back_to_main_callback(self, query: CallbackQuery) -> None:
        """Handle back to main callback"""
        user = query.from_user
        user_id: int = user.id

        # Get user's watch count
        watch_info: Dict[str, int] = await get_user_watch_count(user_id)
        free_watches_used = watch_info['used']
        free_watches_limit = watch_info['limit']
        remaining_watches = free_watches_limit - free_watches_used

        # Check premium status
        is_premium = await check_user_premium_status(user_id)

        # Get premium expiry date if user is premium
        premium_expiry = None
        if is_premium and user_id not in ADMIN_WHITELIST:
            from bot_services.database import get_user_premium_expiry
            premium_expiry = await get_user_premium_expiry(user_id)

        # Get 3 random dramas to display
        dramas = await get_featured_dramas(3)

        if is_premium:
            if user_id in ADMIN_WHITELIST:
                status_text = "👑 Admin (Unlimited)"
            else:
                status_text = f"🌟 Premium (Unlimited)\n⏰ Expired: {premium_expiry}" if premium_expiry else "🌟 Premium (Unlimited)"
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
            [InlineKeyboardButton("🔍 Cari Drama", callback_data="search_dramas")],
            [InlineKeyboardButton("💰 Paket Premium", callback_data="show_packages")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send with first drama's cover if available
        if dramas and dramas[0].get('cover'):
            await query.edit_message_media(
                media=InputMediaPhoto(
                    media=dramas[0]['cover'],
                    caption=welcome_text,
                    parse_mode='Markdown'
                ),
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def display_search_results(self, update: Update, search_query: str, results: List[Dict[str, Any]], user_id: int) -> None:
        """Display search results to user"""
        # Get user status
        watch_info: Dict[str, int] = await get_user_watch_count(user_id)
        is_premium: bool = await check_user_premium_status(user_id)

        results_count: int = len(results)

        if is_premium or user_id in ADMIN_WHITELIST:
            if user_id in ADMIN_WHITELIST:
                status_text: str = "👑 Admin (Unlimited)"
            else:
                expiry_date = await get_user_premium_expiry(user_id)
                status_text: str = f"🌟 Premium (Unlimited) - Expires: {expiry_date}" if expiry_date else "🌟 Premium (Unlimited)"
        else:
            remaining_watches: int = watch_info['limit'] - watch_info['used']
            status_text = f"📺 Gratis ({remaining_watches}/{watch_info['limit']})"

        search_text: str = f"""
🔍 *HASIL PENCARIAN*

Kata kunci: "{search_query}"
📊 Ditemukan: {results_count} drama
{status_text}

Pilih drama yang ingin ditonton:
        """

        keyboard = []

        # Add drama results (show first 10)
        for drama in results[:10]:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎬 {drama['title'][:40]}{'...' if len(drama['title']) > 40 else ''} (Ep. {drama['episodes']})",
                    callback_data=f"drama_{drama['id']}"
                )
            ])

        # Add navigation buttons
        nav_buttons = []
        if results_count > 10:
            nav_buttons.append(InlineKeyboardButton(f"📋 Lihat Semua ({results_count})", callback_data="show_dramas"))

        nav_buttons.extend([
            InlineKeyboardButton("🔍 Cari Lagi", callback_data="search_dramas"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")
        ])

        # Add navigation buttons in pairs
        for i in range(0, len(nav_buttons), 2):
            if i + 1 < len(nav_buttons):
                keyboard.append([nav_buttons[i], nav_buttons[i + 1]])
            else:
                keyboard.append([nav_buttons[i]])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send with cover image if available
        if results and results[0].get('cover'):
            await update.message.reply_photo(
                photo=results[0]['cover'],
                caption=search_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await safe_reply_text(update.message, search_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle regular text messages"""
        text: str = update.message.text
        user_id: int = update.effective_user.id

        # Handle admin commands
        if text.startswith('/activate'):
            await self.handle_manual_activation(update, context)
            return

        # Check if user is in search mode (after clicking search button)
        # For now, treat any non-command text as potential search query
        if not text.startswith('/'):
            # Treat as search query
            search_results: List[Dict[str, Any]] = await search_dramas_by_name(text)

            if search_results:
                await self.display_search_results(update, text, search_results, user_id)
            else:
                no_result_text: str = f"""
🔍 *HASIL PENCARIAN*

Tidak ditemukan drama dengan kata kunci: "{text}"

💡 Tips pencarian:
• Coba kata kunci yang lebih pendek
• Periksa ejaan kata kunci
• Gunakan kata kunci utama saja

Atau gunakan /cari [nama drama]
                """

                keyboard = [
                    [InlineKeyboardButton("🔍 Coba Lagi", callback_data="search_dramas")],
                    [InlineKeyboardButton("📺 Lihat Semua", callback_data="show_dramas")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await safe_reply_text(update.message, no_result_text, reply_markup=reply_markup, parse_mode='Markdown')
            return
        else:
            # Handle unknown commands
            unknown_command_text: str = """
❓ *PERINTAH TIDAK DIKENALI*

📋 Perintah yang tersedia:
• `/start` - Menu utama
• `/dramas` - Lihat semua drama
• `/cari [nama]` - Cari drama
• `/commands` - Daftar perintah
• `/help` - Bantuan

💡 Atau ketik nama drama untuk mencari langsung!
            """

            keyboard = [
                [InlineKeyboardButton("📋 Lihat Perintah", callback_data="commands")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_reply_text(update.message, unknown_command_text, reply_markup=reply_markup, parse_mode='Markdown')
            return

    async def handle_manual_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle manual premium activation by admin"""
        user_id: int = update.effective_user.id
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs

        if user_id not in ADMIN_IDS:
            await safe_reply_text(update.message, "❌ Akses ditolak.")
            return

        try:
            parts = update.message.text.split()
            if len(parts) != 3:
                await safe_reply_text(update.message, "Format: `/activate <payment_id> <telegram_id>`", parse_mode='Markdown')
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
                await safe_reply_text(update.message, f"✅ Premium berhasil diaktivasi untuk user {target_telegram_id}")
            else:
                await safe_reply_text(update.message, f"❌ Gagal aktivasi: {result.get('error', 'Unknown error')}")

        except Exception as e:
            await safe_reply_text(update.message, f"❌ Error: {e}")

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin panel for managing payments"""
        user_id: int = update.effective_user.id

        # Simple admin check (you can make this more sophisticated)
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs

        if user_id not in ADMIN_IDS:
            await safe_reply_text(update.message, "❌ Akses ditolak. Anda bukan admin.")
            return

        # Get pending payments from webhook server
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:5000/pending-payments') as response:
                    data = await response.json()

            pending_payments = data.get('pending_payments', [])

            if not pending_payments:
                await safe_reply_text(update.message, "✅ Tidak ada pembayaran pending.")
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

            await safe_reply_text(update.message, text, parse_mode='Markdown')

        except Exception as e:
            await safe_reply_text(update.message, f"❌ Error mengakses data pembayaran: {e}")

    async def create_subscription(self, user_id: int, package_type: str, amount: int) -> Dict[str, Any]:
        """Create subscription via Saweria API"""
        saweria_user_id = os.getenv('SAWERIA_USER_ID')
        if not saweria_user_id:
            raise ValueError("SAWERIA_USER_ID not configured")

        # Get user info
        from bot_services.database import get_user_by_telegram_id
        user = await get_user_by_telegram_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Package info
        package_info = {
            "1day": {"name": "1 Hari", "price": 3000, "duration": "24 jam"},
            "7day": {"name": "7 Hari", "price": 10000, "duration": "1 minggu"},
            "30day": {"name": "30 Hari", "price": 25000, "duration": "1 bulan"},
            "1year": {"name": "1 Tahun", "price": 50000, "duration": "1 tahun"}
        }

        if package_type not in package_info:
            raise ValueError("Invalid package type")

        pkg = package_info[package_type]

        # Prepare API request
        url = f"https://backend.saweria.co/donations/snap/{saweria_user_id}"
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0)'
        }

        payload = {
            "agree": True,
            "notUnderage": True,
            "message": f"Premium {pkg['name']} - Telegram ID: {user_id}",
            "amount": pkg['price'],
            "payment_type": "qris",
            "vote": "",
            "currency": "IDR",
            "customer_info": {
                "first_name": user.get('first_name', 'User'),
                "email": f"user{user_id}@telegram.bot",
                "phone": ""
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status != 201:
                        error_text = await response.text()
                        raise Exception(f"Saweria API error: {response.status} - {error_text}")

                    result = await response.json()

                    # Save subscription to database
                    await self.save_subscription_to_db(
                        user_id=user_id,
                        saweria_donation_id=result['data']['id'],
                        amount=pkg['price'],
                        package_type=package_type,
                        payment_type="qris",
                        qr_string=result['data']['qr_string'],
                        message=payload['message'],
                        customer_info=payload['customer_info']
                    )

                    return result['data']

        except Exception as e:
            print(f"Subscription creation error: {e}")
            raise

    async def save_subscription_to_db(self, user_id: int, saweria_donation_id: str, amount: int,
                                    package_type: str, payment_type: str, qr_string: str,
                                    message: str, customer_info: Dict[str, Any]):
        """Save subscription data to database"""
        from bot_services.database import get_supabase_client
        supabase = get_supabase_client()

        subscription_data = {
            'user_id': user_id,
            'saweria_donation_id': saweria_donation_id,
            'amount': amount,
            'payment_type': payment_type,
            'status': 'pending',
            'qr_string': qr_string,
            'message': message,
            'package_type': package_type,
            'customer_info': customer_info
        }

        result = supabase.table('subscriptions').insert(subscription_data).execute()
        return result

    async def select_package_callback(self, query: CallbackQuery, package_type: str, user_id: int) -> None:
        """Handle package selection with QR code payment"""
        # Answer callback immediately to prevent timeout
        await query.answer()

        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n💳 Membuat pembayaran...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return

        try:
            package_info = {
                "1day": {"name": "1 Hari", "price": "Rp 3.000", "duration": "24 jam"},
                "7day": {"name": "7 Hari", "price": "Rp 10.000", "duration": "1 minggu"},
                "30day": {"name": "30 Hari", "price": "Rp 25.000", "duration": "1 bulan"},
                "1year": {"name": "1 Tahun", "price": "Rp 50.000", "duration": "1 tahun"}
            }

            if package_type not in package_info:
                await wait_message.edit_text("❌ Paket tidak valid.")
                return

            pkg = package_info[package_type]

            # Create subscription via Saweria API
            subscription_data = await self.create_subscription(user_id, package_type, pkg['price'])

            # Generate QR code image from qr_string
            import qrcode
            import io

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(subscription_data['qr_string'])
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)

            # Send QR code with payment instructions
            text = f"""
🎟️ *PAKET {pkg['name'].upper()}*

💰 Harga: {pkg['price']}
⏰ Durasi: {pkg['duration']}
🆔 ID Pembayaran: `{subscription_data['id'][:8]}...`

📱 *Scan QR Code di bawah untuk bayar:*

✅ *Setelah pembayaran berhasil:*
• Akses penuh semua drama
• Streaming tanpa batas
• Kualitas HD
• Update terbaru

💡 *Status pembayaran akan otomatis terupdate*
⏰ *Expired dalam 24 jam*
            """

            # Send QR code as photo with caption
            await query.message.reply_photo(
                photo=buffer,
                caption=text,
                parse_mode='Markdown'
            )

            # Delete the wait message
            await wait_message.delete()

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Gagal membuat pembayaran: {str(e)}")

    async def check_subscription_status_callback(self, query: CallbackQuery, user_id: int) -> None:
        """Check subscription payment status"""
        # Answer callback immediately to prevent timeout
        await query.answer()

        # Send "please wait" message immediately
        try:
            wait_message = await safe_reply_text(query.message, "⏳ *Sedang memproses...*\n\n🔍 Mengecek status pembayaran...", parse_mode='Markdown')
        except Exception as e:
            print(f"Failed to send wait message: {e}")
            return

        try:
            from bot_services.database import get_supabase_client
            supabase = get_supabase_client()

            # Get latest pending subscription for user
            result = supabase.table('subscriptions').select('*').eq('user_id', user_id).eq('status', 'pending').order('created_at', desc=True).limit(1).execute()

            if not result.data:
                await wait_message.edit_text("❌ Tidak ada pembayaran pending.")
                return

            subscription = result.data[0]

            # Check status with Saweria API
            saweria_user_id = os.getenv('SAWERIA_USER_ID')
            url = f"https://backend.saweria.co/donations/{subscription['saweria_donation_id']}"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        status_data = await response.json()

                        if status_data['data']['status'] == 'COMPLETED':
                            # Update subscription status
                            supabase.table('subscriptions').update({
                                'status': 'completed',
                                'completed_at': 'now()'
                            }).eq('id', subscription['id']).execute()
                            # Activate premium for user
                            await self.activate_user_premium(user_id, subscription['package_type'])
                            await wait_message.edit_text("✅ *PEMBAYARAN BERHASIL!*\n\n🌟 Premium Anda telah diaktifkan!\n\nSilakan nikmati semua fitur premium! 🎬", parse_mode='Markdown')
                            return

            await wait_message.edit_text("⏳ *PEMBAYARAN MASIH PENDING*\n\nBelum ada konfirmasi pembayaran.\n\nCoba lagi dalam beberapa menit atau hubungi admin jika sudah bayar.", parse_mode='Markdown')

        except Exception as e:
            import traceback
            traceback.print_exc()
            await wait_message.edit_text(f"❌ Gagal cek status: {str(e)}")

    async def activate_user_premium(self, user_id: int, package_type: str):
        """Activate premium status for user"""
        from bot_services.database import get_supabase_client
        import datetime

        supabase = get_supabase_client()

        # Calculate expiry date based on package
        now = datetime.datetime.now()
        if package_type == '1day':
            expiry = now + datetime.timedelta(days=1)
        elif package_type == '7day':
            expiry = now + datetime.timedelta(days=7)
        elif package_type == '30day':
            expiry = now + datetime.timedelta(days=30)
        elif package_type == '1year':
            expiry = now + datetime.timedelta(days=365)
        else:
            expiry = now + datetime.timedelta(days=1)  # Default 1 day

        # Update user premium status
        supabase.table('users').update({
            'is_premium': True,
            'premium_expiry': expiry.isoformat()
        }).eq('telegram_id', user_id).execute()

    async def check_premium_expiry(self) -> None:
        """Check and handle expired premium users"""
        from bot_services.database import check_and_expire_premium_users

        try:
            expired_users = await check_and_expire_premium_users()

            if expired_users:
                print(f"Found {len(expired_users)} expired premium users")

                # Send notifications to expired users
                for user in expired_users:
                    try:
                        await self.send_premium_expired_notification(user['telegram_id'], user['first_name'])
                    except Exception as e:
                        print(f"Failed to send expiry notification to user {user['telegram_id']}: {e}")

        except Exception as e:
            print(f"Error checking premium expiry: {e}")

    async def send_premium_expired_notification(self, user_id: int, first_name: str) -> None:
        """Send notification to user whose premium has expired"""
        try:
            text = f"""
⚠️ *PREMIUM ANDA SUDAH HABIS*

Halo {first_name}! ⏰

Premium Anda sudah expired dan tidak aktif lagi.

📺 *Fitur yang tidak bisa digunakan:*
• ❌ Akses semua episode drama
• ❌ Streaming unlimited
• ❌ Kualitas HD
• ❌ Download episode

💰 *Upgrade Lagi untuk Melanjutkan:*

Silakan pilih paket premium yang sesuai:
            """

            keyboard = [
                [InlineKeyboardButton("🎟️ 1 Hari - Rp 3.000", callback_data="package_1day")],
                [InlineKeyboardButton("📅 7 Hari - Rp 10.000", callback_data="package_7day")],
                [InlineKeyboardButton("📆 30 Hari - Rp 25.000", callback_data="package_30day")],
                [InlineKeyboardButton("🎉 1 Tahun - Rp 50.000", callback_data="package_1year")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Try to send message to user
            await self.application.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

            print(f"Sent premium expiry notification to user {user_id}")

        except Exception as e:
            print(f"Failed to send premium expiry notification to user {user_id}: {e}")

    async def admin_check_expiry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command to manually check and expire premium users"""
        user_id = update.effective_user.id

        # Simple admin check
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs
        if user_id not in ADMIN_IDS:
            await safe_reply_text(update.message, "❌ Akses ditolak. Anda bukan admin.")
            return

        await safe_reply_text(update.message, "🔍 Sedang mengecek premium yang expired...")

        try:
            expired_users = await self.check_premium_expiry()

            if expired_users:
                text = f"✅ Berhasil mengecek dan expire {len(expired_users)} user premium:\n\n"
                for user in expired_users:
                    text += f"• {user['first_name']} (@{user.get('username', 'N/A')}) - ID: {user['telegram_id']}\n"
                text += "\nNotifikasi sudah dikirim ke user yang bersangkutan."
            else:
                text = "✅ Tidak ada user premium yang expired."

            await safe_reply_text(update.message, text)

        except Exception as e:
            await safe_reply_text(update.message, f"❌ Error: {e}")

    async def admin_extend_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command to extend user premium manually"""
        user_id = update.effective_user.id

        # Simple admin check
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs
        if user_id not in ADMIN_IDS:
            await safe_reply_text(update.message, "❌ Akses ditolak. Anda bukan admin.")
            return

        try:
            args = context.args
            if len(args) != 2:
                await safe_reply_text(update.message, "Format: `/extend_premium <telegram_id> <days>`\nContoh: `/extend_premium 123456789 30`")
                return

            target_user_id = int(args[0])
            days = int(args[1])

            from bot_services.database import extend_user_premium

            success = await extend_user_premium(target_user_id, days)

            if success:
                await safe_reply_text(update.message, f"✅ Berhasil extend premium user {target_user_id} selama {days} hari.")
            else:
                await safe_reply_text(update.message, f"❌ Gagal extend premium user {target_user_id}.")

        except ValueError:
            await safe_reply_text(update.message, "❌ Format salah. Gunakan angka untuk telegram_id dan days.")
        except Exception as e:
            await safe_reply_text(update.message, f"❌ Error: {e}")

    async def admin_expire_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command to expire user premium manually"""
        user_id = update.effective_user.id

        # Simple admin check
        ADMIN_IDS = [123456789, 987654321]  # Replace with actual admin Telegram IDs
        if user_id not in ADMIN_IDS:
            await safe_reply_text(update.message, "❌ Akses ditolak. Anda bukan admin.")
            return

        try:
            args = context.args
            if len(args) != 1:
                await safe_reply_text(update.message, "Format: `/expire_premium <telegram_id>`\nContoh: `/expire_premium 123456789`")
                return

            target_user_id = int(args[0])

            from bot_services.database import expire_user_premium

            success = await expire_user_premium(target_user_id)

            if success:
                await safe_reply_text(update.message, f"✅ Berhasil expire premium user {target_user_id}.")
            else:
                await safe_reply_text(update.message, f"❌ Gagal expire premium user {target_user_id}.")

        except ValueError:
            await safe_reply_text(update.message, "❌ Format salah. Gunakan angka untuk telegram_id.")
        except Exception as e:
            await safe_reply_text(update.message, f"❌ Error: {e}")