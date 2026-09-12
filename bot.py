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
import threading
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, validate_config, logger
from database import init_db, get_analytics_stats, log_activity

# Import module handlers
from modules.global_search import (
    search_command,
    image_search_command,
    song_search_command,
    lyrics_search_command,
    pdf_search_command,
    song_lyrics_callback,
    song_select_callback,
    song_page_callback,
    song_deep_callback,
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
from modules.sheet_music import (
    sheet_command,
    sheet_callback,
    sheet_page_callback,
)


HELP_TEXT = """
🤖 <b>Damisile AI - Master Command Center</b>

<b>🎬 Movies & Series:</b>
• Just type the title: <code>spiderman</code> or <code>the hunted</code>
• Or use: <code>/movie &lt;title&gt;</code> (searches 14+ movie streaming portals)

<b>🎵 Songs & Lyrics:</b>
• Just type: <code>play sailor song</code> or <code>die with a smile</code>
• Or use: <code>/song &lt;title&gt;</code> (multi-portal MP3 search & direct download)
• Lyrics: <code>/lyrics &lt;song title&gt;</code>

<b>🎹 Sheet Music & Hymns (Classical Pianist Suite):</b>
• <code>/sheet &lt;piece&gt;</code> - Classical piano scores (Chopin, Bach, Beethoven, Debussy, etc.)
• <code>/hymn &lt;title&gt;</code> - Church hymns, 4-part SATB harmonies, & lead sheets
• Or just type: <code>sheet music for moonlight sonata</code> or <code>hymn great is thy faithfulness</code>
• Ready-to-play PDF scores delivered directly into this chat!

<b>📹 Universal Social Media Downloader:</b>
• Paste any link from Instagram, TikTok, Twitter/X, YouTube, Reddit, Facebook
• Instant auto-download with direct video sent back!

<b>🎙️ AI Voice Notes:</b>
• Send or forward a voice note: transcribes your audio and replies back with a spoken voice note!

<b>🛠️ File & Media Converter:</b>
• Send any photo, video, PDF, or Word DOCX document to convert formats or extract audio/text.

<b>🔍 Global Web & Document Search:</b>
• <code>/search &lt;query&gt;</code> - Web search with AI synthesized summary
• <code>/image &lt;query&gt;</code> - High-res photo gallery
• <code>/pdf &lt;query&gt;</code> - Direct PDF book & document finder
• <code>/weather &lt;city&gt;</code> - Live temperature & forecast
• <code>/news &lt;topic&gt;</code> - Daily news digest

<b>🧠 AI Chat & Tools:</b>
• Just chat naturally or use: <code>/ask &lt;question&gt;</code>
• <code>/summarize &lt;url&gt;</code> - Instant webpage summary
• <code>/clear</code> - Reset AI conversation history
• <code>/stats</code> - Live web analytics dashboard
"""

PUBLIC_DASHBOARD_URL = "https://telegram-personal-bot-kzo4.onrender.com/"

def self_ping_loop(port: int):
    """Periodically pings local and public web server every 9 minutes to prevent sleep/spindowns."""
    import time
    import httpx
    while True:
        time.sleep(540)
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/stats", timeout=5.0)
        except Exception:
            pass
        try:
            if PUBLIC_DASHBOARD_URL:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DamisileKeepAlive/1.0"}
                httpx.get(f"{PUBLIC_DASHBOARD_URL.rstrip('/')}/api/stats", headers=headers, timeout=10.0)
        except Exception:
            pass

def start_dashboard_server():
    """Start Flask web analytics dashboard in a background thread."""
    try:
        import os
        from dashboard import app
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        port = int(os.getenv("PORT", 5000))

        # Launch self-ping thread
        ping_thread = threading.Thread(target=self_ping_loop, args=(port,), daemon=True)
        ping_thread.start()

        logger.info(f"🌐 Web Analytics Dashboard server running on port {port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Error starting dashboard server: {e}")

async def start_command(update: Update, context):
    """Handle /start command."""
    user = update.effective_user
    name = user.first_name if user and user.first_name else "friend"
    if user:
        log_activity(user.id, user.username, user.first_name, "command", "/start")

    welcome_text = (
        f"👋 <b>Welcome, {name}!</b>\n\n"
        "I am your all-in-one personal AI assistant & media powerhouse. Here is what I can do for you right away:\n\n"
        "🎬 <b>Find Movies & Series:</b> Type any title (e.g. <code>spiderman</code>) or <code>/movie &lt;title&gt;</code>\n"
        "🎵 <b>Download MP3 Songs:</b> Type a song name (e.g. <code>sailor song</code>) or <code>/song &lt;title&gt;</code>\n"
        "🎹 <b>Piano Scores & Hymns:</b> Type <code>/sheet &lt;piece&gt;</code> or <code>/hymn &lt;title&gt;</code> for direct PDF scores\n"
        "📹 <b>Social Video Downloader:</b> Paste any Instagram Reel, TikTok, Shorts, or X link\n"
        "🎙️ <b>AI Voice Notes:</b> Send a voice message and I will transcribe and talk back\n"
        "🛠️ <b>File Converter:</b> Upload any photo, video, PDF, or Word document\n"
        "🧠 <b>AI Assistant:</b> Chat with me anytime or use <code>/ask &lt;question&gt;</code>\n\n"
        "💡 <i>Tip: Tap /help anytime to explore all commands and features!</i>"
    )

    await update.message.reply_text(welcome_text, parse_mode="HTML")


async def help_command(update: Update, context):
    """Handle /help command."""
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "command", "/help")
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def stats_command(update: Update, context):
    """Handle /stats or /admin command for live telemetry dashboard link."""
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "command", "/stats")

    stats = get_analytics_stats()
    text = (
        f"📊 <b>Damisile AI - Live Usage & Intelligence Dashboard</b>\n\n"
        f"• <b>Total Bot Interactions:</b> {stats['total_logs']}\n"
        f"• <b>Media & Song Downloads:</b> {stats['total_downloads']}\n"
        f"• <b>AI & Web Searches:</b> {stats['total_searches']}\n"
        f"• <b>Active Authorized Users:</b> {len(stats['top_users'])}\n\n"
        f"🌐 <b>Live Public Web Dashboard (View Anywhere):</b>\n"
        f"<a href='{PUBLIC_DASHBOARD_URL}'>{PUBLIC_DASHBOARD_URL}</a>"
    )
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def history_command(update: Update, context):
    """Handle /history command to show recent downloads."""
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "command", "/history")

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
        BotCommand("stats", "Live telemetry dashboard"),
        BotCommand("search", "Search the web"),
        BotCommand("image", "Search for images"),
        BotCommand("song", "Find a song"),
        BotCommand("lyrics", "Get song lyrics"),
        BotCommand("sheet", "Piano sheet music & scores PDF"),
        BotCommand("hymn", "Church hymns & SATB score PDF"),
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


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent response for pagination indicator clicks."""
    if update.callback_query:
        await update.callback_query.answer()


def main():
    """Main bot setup and runner."""
    # Validate configuration
    if not validate_config():
        logger.error("Invalid configuration. Please check your .env file.")
        return

    # Initialize database
    init_db()

    # Start Flask Web Dashboard Server in background thread
    dashboard_thread = threading.Thread(target=start_dashboard_server, daemon=True)
    dashboard_thread.start()
    logger.info("🌐 Web Analytics Dashboard running on http://localhost:5000")

    # Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Register Command Handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("admin", stats_command))

    # Search commands
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("image", image_search_command))
    app.add_handler(CommandHandler("song", song_search_command))
    app.add_handler(CommandHandler("lyrics", lyrics_search_command))
    app.add_handler(CommandHandler("sheet", sheet_command))
    app.add_handler(CommandHandler("hymn", sheet_command))
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
    app.add_handler(CallbackQueryHandler(sheet_callback, pattern=r"^sheet:"))
    app.add_handler(CallbackQueryHandler(sheet_page_callback, pattern=r"^sheetpage:"))
    app.add_handler(CallbackQueryHandler(song_lyrics_callback, pattern=r"^songlyrics:"))
    app.add_handler(CallbackQueryHandler(song_select_callback, pattern=r"^songselect:"))
    app.add_handler(CallbackQueryHandler(song_page_callback, pattern=r"^songpage:"))
    app.add_handler(CallbackQueryHandler(song_deep_callback, pattern=r"^songdeep:"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))

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

