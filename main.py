import os
import re
import logging
import asyncio
from datetime import datetime
import pytz
import json
from typing import Dict, List, Optional, Union, Tuple
from functools import lru_cache

# Telegram libraries
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler

# Bluesky library
from atproto import Client as BlueskyClient
from atproto import models

# Mastodon library
from mastodon import Mastodon

# For scheduling
import schedule
import time
import threading

# For env management
from pydantic_settings import BaseSettings, SettingsConfigDict

# Setup env variables
class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    BLUESKY_USERNAME: str
    BLUESKY_PASSWORD: str
    MASTODON_ACCESS_TOKEN: str
    AUTHORIZED_USERS: List[int]

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables (store these securely in a .env file or environment variables)
TELEGRAM_TOKEN = get_settings().TELEGRAM_TOKEN
BLUESKY_USERNAME = get_settings().BLUESKY_USERNAME
BLUESKY_PASSWORD = get_settings().BLUESKY_PASSWORD
MASTODON_ACCESS_TOKEN = get_settings().MASTODON_ACCESS_TOKEN
MASTODON_API_BASE_URL = "https://fosstodon.org"

# List of authorized Telegram user IDs who can use the bot
AUTHORIZED_USERS = get_settings().AUTHORIZED_USERS

# Conversation states
SELECTING_PLATFORMS, CONFIRMING_POST, SCHEDULING = range(3)

# Data storage
scheduled_posts = {}

# Initialize clients
bluesky_client = BlueskyClient()
mastodon_client = Mastodon(
    access_token=MASTODON_ACCESS_TOKEN,
    api_base_url=MASTODON_API_BASE_URL
)

# Function to login to Bluesky
def login_to_bluesky():
    try:
        bluesky_client.login(BLUESKY_USERNAME, BLUESKY_PASSWORD)
        logger.info("Logged in to Bluesky successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to login to Bluesky: {e}")
        return False

# Post to Bluesky
def post_to_bluesky(text: str) -> Tuple[bool, Optional[str]]:
    try:
        if not bluesky_client.me:  # Check if we're logged in
            if not login_to_bluesky():
                return False, None
        
        # Process the text for links and mentions
        facets = []
        
        # Process URLs
        url_pattern = re.compile(r'https?://\S+')
        for match in url_pattern.finditer(text):
            start, end = match.span()
            facets.append(models.AppBskyRichtextFacet.Main(
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byteStart=start,
                    byteEnd=end
                ),
                features=[models.AppBskyRichtextFacet.Link(uri=match.group())]
            ))
        
        # Process hashtags
        hashtag_pattern = re.compile(r'#(\w+)')
        for match in hashtag_pattern.finditer(text):
            start, end = match.span()
            tag = match.group(1)  # Get the tag without the # symbol
            facets.append(models.AppBskyRichtextFacet.Main(
                index=models.AppBskyRichtextFacet.ByteSlice(
                    byteStart=start,
                    byteEnd=end
                ),
                features=[models.AppBskyRichtextFacet.Tag(tag=tag)]
            ))
        
        # Process mentions (@username.bsky.social)
        mention_pattern = re.compile(r'@(\w+(?:\.\w+)*)')
        for match in mention_pattern.finditer(text):
            start, end = match.span()
            username = match.group(1)
            
            # Find the user's DID
            try:
                # Attempt to resolve the handle
                resolution = bluesky_client.app.bsky.actor.get_profile({'actor': username})
                did = resolution.did
                
                facets.append(models.AppBskyRichtextFacet.Main(
                    index=models.AppBskyRichtextFacet.ByteSlice(
                        byteStart=start,
                        byteEnd=end
                    ),
                    features=[models.AppBskyRichtextFacet.Mention(did=did)]
                ))
            except Exception as e:
                logger.warning(f"Failed to resolve mention for {username}: {e}")
                # Continue without adding this mention as a facet
        
        # Create the post with facets
        response = bluesky_client.send_post(
            text=text,
            facets=facets if facets else None
        )
        
        # Extract the post URI to create a link
        if hasattr(response, 'uri'):
            # Extract the repo and record ID from the URI
            uri_parts = response.uri.split('/')
            if len(uri_parts) >= 4:
                repo = uri_parts[2]
                record_id = uri_parts[4]
                post_link = f"https://bsky.app/profile/{repo}/post/{record_id}"
                logger.info(f"Posted to Bluesky successfully with link: {post_link}")
                return True, post_link
        
        logger.info("Posted to Bluesky successfully but couldn't generate link")
        return True, None
    except Exception as e:
        logger.error(f"Failed to post to Bluesky: {e}")
        return False, None

# Post to Mastodon (Fosstodon)
def post_to_mastodon(text: str) -> Tuple[bool, Optional[str]]:
    try:
        response = mastodon_client.status_post(text)
        
        # Extract post ID and create a link
        if hasattr(response, 'id') and hasattr(response, 'url'):
            post_link = response.url
            logger.info(f"Posted to Fosstodon successfully with link: {post_link}")
            return True, post_link
        
        logger.info("Posted to Fosstodon successfully but couldn't generate link")
        return True, None
    except Exception as e:
        logger.error(f"Failed to post to Fosstodon: {e}")
        return False, None

# Authorization check
def is_user_authorized(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this bot."
        )
        return
    
    await update.message.reply_text(
        "Welcome to the Social Media Cross-Poster Bot!\n\n"
        "Use /help to see the available commands.\n\n"
        "Use /post to create a new post.\n\n"
        "Use /schedule to schedule a post.\n\n"
        "Use /list_scheduled to view your scheduled posts.\n\n"
        "Use /delete_scheduled to remove a scheduled post.\n\n"
        "Use /cancel to cancel current operation.\n\n"        
    )

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /help is issued."""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this bot."
        )
        return
    
    await update.message.reply_text(
        "Welcome to the Social Media Cross-Poster Bot!\n\n"
        "Use /help to see the available commands.\n\n"
        "Use /post to create a new post.\n\n"
        "Use /schedule to schedule a post.\n\n"
        "Use /list_scheduled to view your scheduled posts.\n\n"
        "Use /delete_scheduled to remove a scheduled post.\n\n"
        "Use /cancel to cancel current operation.\n\n"        
    )

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the posting process."""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this bot."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "Please send the text you want to post to your social media accounts."
    )
    return SELECTING_PLATFORMS

async def receive_post_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the post text and ask for platforms to post to."""
    context.user_data["post_text"] = update.message.text
    
    keyboard = [
        [
            InlineKeyboardButton("Bluesky", callback_data="platform_bluesky"),
            InlineKeyboardButton("Fosstodon", callback_data="platform_fosstodon")
        ],
        [InlineKeyboardButton("Both", callback_data="platform_both")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Where would you like to post this?",
        reply_markup=reply_markup
    )
    return CONFIRMING_POST

async def select_platforms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle platform selection."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    platforms = query.data.replace("platform_", "")
    context.user_data["platforms"] = platforms
    
    # Ask for confirmation
    post_text = context.user_data.get("post_text", "")
    platform_text = "Bluesky" if platforms == "bluesky" else "Fosstodon" if platforms == "fosstodon" else "Bluesky and Fosstodon"
    
    keyboard = [
        [
            InlineKeyboardButton("Post Now", callback_data="post_now"),
            InlineKeyboardButton("Schedule", callback_data="schedule")
        ],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"You're about to post to {platform_text}:\n\n"
        f"{post_text}\n\n"
        "What would you like to do?",
        reply_markup=reply_markup
    )
    return CONFIRMING_POST

async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle post confirmation or scheduling."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    if query.data == "post_now":
        # Post immediately
        post_text = context.user_data.get("post_text", "")
        platforms = context.user_data.get("platforms", "")
        
        success_message = await post_to_platforms(platforms, post_text)
        await query.edit_message_text(success_message)
        return ConversationHandler.END
    
    if query.data == "schedule":
        await query.edit_message_text(
            "Please enter when you want to schedule this post in the format YYYY-MM-DD HH:MM (UTC).\n"
            "Example: 2025-03-05 15:30"
        )
        return SCHEDULING

async def handle_scheduling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Schedule the post for later."""
    try:
        schedule_time_str = update.message.text
        schedule_time = datetime.strptime(schedule_time_str, "%Y-%m-%d %H:%M")
        schedule_time = pytz.UTC.localize(schedule_time)
        
        post_text = context.user_data.get("post_text", "")
        platforms = context.user_data.get("platforms", "")
        
        user_id = update.effective_user.id
        
        # Create a unique ID for this scheduled post
        post_id = f"{user_id}_{int(time.time())}"
        
        # Store the scheduled post
        scheduled_posts[post_id] = {
            "user_id": user_id,
            "post_text": post_text,
            "platforms": platforms,
            "schedule_time": schedule_time.isoformat()
        }
        
        # Save to file for persistence
        save_scheduled_posts()
        
        # Schedule the post
        schedule_post(post_id)
        
        local_time = schedule_time.astimezone(pytz.timezone("UTC"))
        await update.message.reply_text(
            f"Your post has been scheduled for {local_time.strftime('%Y-%m-%d %H:%M')} UTC."
        )
        
    except ValueError:
        await update.message.reply_text(
            "Invalid date format. Please use YYYY-MM-DD HH:MM (UTC)."
        )
        return SCHEDULING
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel and end the conversation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def list_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled posts for the user."""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this bot."
        )
        return
    
    user_scheduled_posts = {k: v for k, v in scheduled_posts.items() if v["user_id"] == user_id}
    
    if not user_scheduled_posts:
        await update.message.reply_text("You don't have any scheduled posts.")
        return
    
    message = "Your scheduled posts:\n\n"
    
    for post_id, post_data in user_scheduled_posts.items():
        schedule_time = datetime.fromisoformat(post_data["schedule_time"])
        platforms = post_data["platforms"]
        platform_text = "Bluesky" if platforms == "bluesky" else "Fosstodon" if platforms == "fosstodon" else "Bluesky and Fosstodon"
        
        message += f"ID: {post_id}\n"
        message += f"Time: {schedule_time.strftime('%Y-%m-%d %H:%M')} UTC\n"
        message += f"Platforms: {platform_text}\n"
        message += f"Text: {post_data['post_text'][:50]}{'...' if len(post_data['post_text']) > 50 else ''}\n\n"
    
    await update.message.reply_text(message)

async def delete_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a scheduled post."""
    user_id = update.effective_user.id
    
    if not is_user_authorized(user_id):
        await update.message.reply_text(
            "Sorry, you are not authorized to use this bot."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "Please provide the post ID to delete. Use /list_scheduled to see your scheduled posts."
        )
        return
    
    post_id = context.args[0]
    
    if post_id not in scheduled_posts:
        await update.message.reply_text("Post ID not found.")
        return
    
    if scheduled_posts[post_id]["user_id"] != user_id:
        await update.message.reply_text("You can only delete your own scheduled posts.")
        return
    
    del scheduled_posts[post_id]
    save_scheduled_posts()
    
    await update.message.reply_text("Scheduled post deleted successfully.")

# Helper functions
async def post_to_platforms(platforms: str, text: str) -> str:
    """Post to the selected platforms and return success message with links."""
    success_message = "Post results:\n"
    
    if platforms in ["bluesky", "both"]:
        success, post_link = post_to_bluesky(text)
        if success:
            success_message += "✅ Posted to Bluesky successfully\n"
            if post_link:
                success_message += f"🔗 {post_link}\n"
        else:
            success_message += "❌ Failed to post to Bluesky\n"
    
    if platforms in ["fosstodon", "both"]:
        success, post_link = post_to_mastodon(text)
        if success:
            success_message += "✅ Posted to Fosstodon successfully\n"
            if post_link:
                success_message += f"🔗 {post_link}\n"
        else:
            success_message += "❌ Failed to post to Fosstodon\n"
    
    return success_message

def save_scheduled_posts():
    """Save scheduled posts to a file for persistence."""
    with open("scheduled_posts.json", "w") as f:
        json.dump(scheduled_posts, f)

def load_scheduled_posts():
    """Load scheduled posts from file if exists."""
    global scheduled_posts
    try:
        with open("scheduled_posts.json", "r") as f:
            scheduled_posts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        scheduled_posts = {}

def schedule_post(post_id: str):
    """Schedule a post to be published at the specified time."""
    post_data = scheduled_posts.get(post_id)
    if not post_data:
        return
    
    schedule_time = datetime.fromisoformat(post_data["schedule_time"])
    current_time = datetime.now(pytz.UTC)
    
    if schedule_time <= current_time:
        # It's already past the scheduled time, execute immediately
        asyncio.create_task(execute_scheduled_post(post_id))
    else:
        # Calculate seconds until the scheduled time
        seconds_until = (schedule_time - current_time).total_seconds()
        # Schedule the post
        threading.Timer(seconds_until, lambda: asyncio.run(execute_scheduled_post(post_id))).start()

async def execute_scheduled_post(post_id: str):
    """Execute a scheduled post."""
    post_data = scheduled_posts.get(post_id)
    if not post_data:
        return
    
    platforms = post_data["platforms"]
    text = post_data["post_text"]
    user_id = post_data["user_id"]
    
    success_message = await post_to_platforms(platforms, text)
    logger.info(f"Scheduled post {post_id} executed: {success_message}")
    
    # Notify the user
    await notify_user_of_scheduled_post(user_id, post_id, success_message)
    
    # Remove the post from scheduled posts
    if post_id in scheduled_posts:
        del scheduled_posts[post_id]
        save_scheduled_posts()

async def notify_user_of_scheduled_post(user_id: int, post_id: str, message: str):
    """Notify the user that their scheduled post has been published."""
    try:
        # Create an application for sending messages
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Send a message to the user with the result
        await application.bot.send_message(
            chat_id=user_id,
            text=f"Your scheduled post (ID: {post_id}) has been published:\n\n{message}"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id} about scheduled post {post_id}: {e}")

def schedule_checker():
    """Periodically check for scheduled posts to execute."""
    while True:
        current_time = datetime.now(pytz.UTC)
        
        for post_id, post_data in list(scheduled_posts.items()):
            schedule_time = datetime.fromisoformat(post_data["schedule_time"])
            
            if schedule_time <= current_time:
                asyncio.run(execute_scheduled_post(post_id))
        
        time.sleep(60)  # Check every minute

def main() -> None:
    """Set up and run the bot."""
    # Load scheduled posts
    load_scheduled_posts()
    
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Set up conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("post", post_command)],
        states={
            SELECTING_PLATFORMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_post_text)],
            CONFIRMING_POST: [CallbackQueryHandler(select_platforms, pattern="^platform_"), 
                             CallbackQueryHandler(confirm_post, pattern="^(post_now|schedule|cancel)$")],
            SCHEDULING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_scheduling)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("list_scheduled", list_scheduled))
    application.add_handler(CommandHandler("delete_scheduled", delete_scheduled))
    
    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=schedule_checker, daemon=True)
    scheduler_thread.start()
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    # Login to services
    login_to_bluesky()
    main()