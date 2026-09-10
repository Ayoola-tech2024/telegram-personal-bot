"""
Ultimate AI Telegram Bot - Main Entrypoint
==========================================
An all-in-one personal Telegram bot featuring:
- Lightning-fast global search (web, images, songs, lyrics, PDFs)
- Universal media downloader (YouTube, X, Facebook, Instagram, TikTok, etc.)
- Movie scraper with redirect bypass (Nkiri, 9jarocks, FzMovies)
- AI-powered conversational assistant (Gemini)
"""

import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, validate_config, logger
from database import init_db

# Import module handlers
from modules.global_search import (
    search_command,
    image_search_command,
    song_search_command,
    lyrics_search_command,
    pdf_search_command,
    movie_search_command,
)
from modules.movie_scraper import (
    movie_command,
    movie_callback,
    movie_download_callback,
)
from modules.media_downloader import (
    url_handler,
    download_callback,
    direct_download_callback,
)
from modules.ai_engine import (
    ai_message_handler,
    summarize_command,
    ask_command,
    clear_command,
    voice_note_handler,
)
from modules.file_converter import (
    document_upload_handler,
    converter_callback,
)
from modules.news_weather import (
    weather_command,
    news_command,
)


HELP_TEXT = """
<b>🤖 Ultimate AI Telegram Bot</b>

<b>🔍 Search & Info Commands:</b>
/search &lt;query&gt; - Search the web with AI summary
/image &lt;query&gt; - Search & send high-res images
/song &lt;query&gt; - Find songs and audio files
/lyrics &lt;song&gt; - Get song lyrics
/pdf &lt;query&gt; - Search for PDF documents
/movie &lt;title&gt; - Search movies across 14+ portals
/weather &lt;city&gt; - Live weather report
/news &lt;topic&gt; - Daily news digest

<b>🎬 Movies & Music:</b>
Just type movie names (e.g. <code>spiderman</code>) or song names (e.g. <code>die with a smile</code>) directly!

<b>📹 Zero-Click Social Media Download:</b>
Paste any Instagram Reel, TikTok, Shorts, or X video link to get the video directly!

<b>🎙️ AI Voice Notes:</b>
Send a voice note to transcribe and get a spoken AI response back!

<b>🛠️ File Converter Suite:</b>
Send any image, video, DOCX, or PDF file to convert format or extract audio/text.

<b>🧠 AI Assistant:</b>
/ask &lt;question&gt; - Ask AI anything
/summarize &lt;url&gt; - Summarize any web page
/clear - Clear AI chat history
"""


async def start_command(update: Update, context):
    """Handle /start command."""
    await update.message.reply_text(
        "👋 <b>Welcome to your Ultimate AI Bot!</b>\n\n"
        "I can download movies from 14+ portals, fetch MP3 songs, "
        "auto-extract Instagram Reels & TikToks, transcribe voice notes, "
        "convert files, report live weather, and answer anything with AI.\n\n"
        "Type /help to see all commands!",
        parse_mode="HTML",
    )


async def help_command(update: Update, context):
    """Handle /help command."""
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def history_command(update: Update, context):
    """Handle /history command to show recent downloads."""
    from database import get_recent_downloads

    downloads = get_recent_downloads(10)
    if not downloads:
        await update.message.reply_text("📭 No download history yet.")
        return

    text = "<b>📥 Recent Downloads:</b>\n\n"
    for i, dl in enumerate(downloads, 1):
        title = dl.get("title") or "Untitled"
        file_type = dl.get("file_type", "unknown")
        created = dl.get("created_at", "")
        text += f"{i}. <b>{title}</b> [{file_type}] - {created}\n"

    await update.message.reply_text(text, parse_mode="HTML")


async def set_bot_commands(application: Application):
    """Set the bot command menu in Telegram."""
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show all commands"),
        BotCommand("search", "Search the web"),
        BotCommand("image", "Search for images"),
        BotCommand("song", "Find a song"),
        BotCommand("lyrics", "Get song lyrics"),
        BotCommand("pdf", "Search for PDFs"),
        BotCommand("movie", "Search 14+ movie sites"),
        BotCommand("weather", "Live weather report"),
        BotCommand("news", "Daily news digest"),
        BotCommand("ask", "Ask AI a question"),
        BotCommand("summarize", "Summarize a webpage"),
        BotCommand("clear", "Clear AI chat history"),
        BotCommand("history", "Recent download history"),
    ]
    await application.bot.set_my_commands(commands)


def main():
    """Main bot setup and runner."""
    # Validate configuration
    if not validate_config():
        logger.error("Invalid configuration. Please check your .env file.")
        return

    # Initialize database
    init_db()

    # Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Register Command Handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history_command))

    # Search commands
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("image", image_search_command))
    app.add_handler(CommandHandler("song", song_search_command))
    app.add_handler(CommandHandler("lyrics", lyrics_search_command))
    app.add_handler(CommandHandler("pdf", pdf_search_command))
    app.add_handler(CommandHandler("movie", movie_command))
    app.add_handler(CommandHandler("weather", weather_command))
    app.add_handler(CommandHandler("news", news_command))

    # AI commands
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("summarize", summarize_command))
    app.add_handler(CommandHandler("clear", clear_command))

    # --- Register Callback Query Handlers (Inline Button Clicks) ---
    app.add_handler(CallbackQueryHandler(download_callback, pattern=r"^dl:"))
    app.add_handler(CallbackQueryHandler(direct_download_callback, pattern=r"^directdl:"))
    app.add_handler(CallbackQueryHandler(movie_callback, pattern=r"^movie_"))
    app.add_handler(CallbackQueryHandler(movie_download_callback, pattern=r"^moviedl:"))
    app.add_handler(CallbackQueryHandler(converter_callback, pattern=r"^conv:"))

    # --- Register Message Handlers ---
    # Voice notes & audio messages
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, voice_note_handler))

    # Document & photo upload converter
    app.add_handler(MessageHandler((filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND, document_upload_handler))

    # URL auto-detection for media downloads (must come before the AI catch-all)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Entity("url"),
            url_handler,
        )
    )

    # AI catch-all for text messages without commands or URLs
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            ai_message_handler,
        )
    )

    # --- Post-init: Set bot command menu ---
    app.post_init = set_bot_commands

    # --- Start the bot ---
    logger.info("🚀 Bot is starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
