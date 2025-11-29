import os, traceback, requests
import json
import asyncio
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, CallbackQuery, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client
from config.db import get_supabase_client
from dotenv import load_dotenv
from botocore.client import Config

# Set event loop policy for Python 3.14 compatibility
# asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())  # Deprecated in 3.14

# Import modularized components
from bot_services.config import SUPABASE_URL, SUPABASE_KEY, BOT_TOKEN, ADMIN_WHITELIST, s3_client
from bot_services.handlers import BotHandlers

class DramaBot:
    def __init__(self):
        self.application = ApplicationBuilder().token(BOT_TOKEN).build()
        self.handlers = BotHandlers(self.application)
        self.setup_handlers()

    def setup_handlers(self) -> None:
        """Setup all bot handlers"""
        self.application.add_handler(CommandHandler("start", self.handlers.start))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))
        self.application.add_handler(CommandHandler("dramas", self.handlers.show_dramas))
        self.application.add_handler(CommandHandler("cari", self.handlers.search_dramas))
        self.application.add_handler(CommandHandler("commands", self.handlers.show_commands))
        self.application.add_handler(CommandHandler("admin", self.handlers.admin_panel))
        self.application.add_handler(CommandHandler("check_expiry", self.handlers.admin_check_expiry))
        self.application.add_handler(CommandHandler("extend_premium", self.handlers.admin_extend_premium))
        self.application.add_handler(CommandHandler("expire_premium", self.handlers.admin_expire_premium))
        self.application.add_handler(CallbackQueryHandler(self.handlers.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message))

    async def run_async(self) -> None:
        """Run the bot asynchronously"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep the bot running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    def run(self) -> None:
        """Run the bot"""
        asyncio.run(self.run_async())


if __name__ == "__main__":
    bot = DramaBot()
    bot.run()