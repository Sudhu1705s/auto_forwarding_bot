import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError, RetryAfter, TimedOut
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('forward_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# CONFIGURATION
FORWARD_BOT_TOKEN = os.environ.get('FORWARD_BOT_TOKEN')
MASTER_CHANNEL = os.environ.get('MASTER_CHANNEL')
TARGET_CHANNELS = os.environ.get('TARGET_CHANNELS', '').split(',')
TARGET_CHANNELS = [ch.strip() for ch in TARGET_CHANNELS if ch.strip()]


async def forward_to_channel(message, channel_id, retries=3):
    """Native forward message to a single channel with retry logic"""
    for attempt in range(retries):
        try:
            # NATIVE TELEGRAM FORWARD - Shows "Forwarded from Master Channel"
            await message.forward(chat_id=channel_id)
            logger.info(f"✅ Native forwarded to {channel_id}")
            return True
        except RetryAfter as e:
            # Telegram rate limit - wait and retry
            wait_time = e.retry_after + 1
            logger.warning(f"⏳ Rate limit hit for {channel_id}, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
        except TimedOut:
            logger.warning(f"⏱️ Timeout for {channel_id}, retrying ({attempt + 1}/{retries})...")
            await asyncio.sleep(2)
        except TelegramError as e:
            error_msg = str(e).lower()
            # Permanent errors - don't retry
            if any(err in error_msg for err in ['chat not found', 'bot was kicked', 'not a member', 'have no rights']):
                logger.error(f"❌ Permanent error {channel_id}: {e}")
                return False
            logger.error(f"❌ Error {channel_id} (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"❌ Unexpected error {channel_id}: {e}")
            return False
    
    logger.error(f"❌ Failed {channel_id} after {retries} attempts")
    return False


async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Native forward any message from master channel to all target channels"""
    
    message = update.channel_post
    
    if not message:
        return
    
    # Determine message type for logging
    msg_type = "text"
    if message.photo:
        msg_type = "photo"
    elif message.video:
        msg_type = "video"
    elif message.document:
        msg_type = "document"
    elif message.audio:
        msg_type = "audio"
    elif message.voice:
        msg_type = "voice"
    elif message.sticker:
        msg_type = "sticker"
    elif message.poll:
        msg_type = "poll"
    
    logger.info(f"📨 New {msg_type} message detected from master channel")
    logger.info(f"📤 Native forwarding to {len(TARGET_CHANNELS)} target channels...")
    
    successful = 0
    failed = 0
    
    # Forward in parallel batches (optimized for Telegram limits)
    batch_size = 20  # Conservative limit to avoid rate limits
    
    for i in range(0, len(TARGET_CHANNELS), batch_size):
        batch = TARGET_CHANNELS[i:i + batch_size]
        
        logger.info(f"🔄 Processing batch {i//batch_size + 1} ({len(batch)} channels)...")
        
        # Parallel forwarding within batch
        tasks = [forward_to_channel(message, ch_id) for ch_id in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful += sum(1 for r in results if r is True)
        failed += sum(1 for r in results if r is not True)
        
        # Delay between batches to stay within Telegram limits
        if i + batch_size < len(TARGET_CHANNELS):
            await asyncio.sleep(1)  # 1 second between batches
    
    logger.info("="*60)
    logger.info(f"✅ NATIVE FORWARD COMPLETE!")
    logger.info(f"📊 Success: {successful}/{len(TARGET_CHANNELS)} | Failed: {failed}")
    logger.info("="*60)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"❌ Update {update} caused error: {context.error}")


def main():
    # Validate environment variables
    if not FORWARD_BOT_TOKEN:
        logger.error("❌ FORWARD_BOT_TOKEN not set in environment variables!")
        sys.exit(1)
    
    if not MASTER_CHANNEL:
        logger.error("❌ MASTER_CHANNEL not set in environment variables!")
        sys.exit(1)
    
    if not TARGET_CHANNELS or len(TARGET_CHANNELS) == 0:
        logger.error("❌ TARGET_CHANNELS not set or empty!")
        sys.exit(1)
    
    try:
        master_id = int(MASTER_CHANNEL)
    except ValueError:
        logger.error(f"❌ MASTER_CHANNEL must be a valid integer ID: {MASTER_CHANNEL}")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("🤖 NATIVE AUTO FORWARD BOT STARTING")
    logger.info(f"📡 Master Channel: {MASTER_CHANNEL}")
    logger.info(f"📤 Target Channels: {len(TARGET_CHANNELS)}")
    logger.info(f"🔧 Bot Token: {FORWARD_BOT_TOKEN[:10]}...")
    logger.info(f"🔄 Mode: NATIVE TELEGRAM FORWARDING (shows 'Forwarded from')")
    logger.info("=" * 60)
    
    # Show first 5 target channels for verification
    logger.info("📋 Target channels preview:")
    for i, ch in enumerate(TARGET_CHANNELS[:5], 1):
        logger.info(f"  {i}. {ch}")
    if len(TARGET_CHANNELS) > 5:
        logger.info(f"  ...and {len(TARGET_CHANNELS) - 5} more")
    logger.info("=" * 60)
    
    app = Application.builder().token(FORWARD_BOT_TOKEN).build()
    
    # Listen ONLY to master channel
    app.add_handler(MessageHandler(
        filters.Chat(chat_id=master_id) & filters.ALL,
        forward_message
    ))
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    logger.info("✅ Native forward bot is now running!")
    logger.info("⏳ Waiting for messages from master channel...")
    logger.info("💡 All forwards will show 'Forwarded from [Master Channel]'")
    
    try:
        app.run_polling(allowed_updates=['channel_post'])
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
