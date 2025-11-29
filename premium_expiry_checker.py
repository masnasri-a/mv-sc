import asyncio
import os
from datetime import datetime, timezone
from bot_services.handlers import BotHandlers
from telegram import Bot
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class PremiumExpiryChecker:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("BOT_TOKEN not configured")

        self.bot = Bot(token=self.bot_token)
        self.handlers = BotHandlers(None)  # We don't need application for notifications
        self.handlers.application = type('MockApp', (), {'bot': self.bot})()

    async def check_expiry_loop(self):
        """Main loop to check premium expiry periodically"""
        print("🚀 Starting premium expiry checker...")

        while True:
            try:
                print(f"🔍 Checking premium expiry at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

                # Check and handle expired premium users
                await self.handlers.check_premium_expiry()

                print("✅ Premium expiry check completed")

            except Exception as e:
                print(f"❌ Error in premium expiry check: {e}")

            # Wait for 1 hour before next check
            await asyncio.sleep(3600)  # 3600 seconds = 1 hour

    async def run_once(self):
        """Run expiry check once (for testing)"""
        print("🔍 Running one-time premium expiry check...")
        try:
            await self.handlers.check_premium_expiry()
            print("✅ One-time premium expiry check completed")
        except Exception as e:
            print(f"❌ Error in one-time premium expiry check: {e}")

if __name__ == "__main__":
    checker = PremiumExpiryChecker()

    # Run in different modes based on command line arguments
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Run once for testing
        asyncio.run(checker.run_once())
    else:
        # Run continuous loop
        asyncio.run(checker.check_expiry_loop())