import json
import re
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, restricted, GEMINI_API_KEY, gemini_keys

try:
    from google import genai
    from google.genai.types import Part, Content

    def _create_client():
        """Create a Gemini client using the current API key."""
        key = gemini_keys.current_key
        if not key:
            return None
        return genai.Client(api_key=key)

    client = _create_client()
except ImportError:
    logger.warning("google.genai library not found. AI features will be disabled.")
    client = None

    def _create_client():
        return None

conversation_history: Dict[int, List[Dict]] = {}
MAX_HISTORY_LENGTH = 16

SYSTEM_PROMPT = """
You are Damisile AI — an elite, highly intelligent conversational AI assistant inside Telegram created by Ayoola Damisile.

Bot Capabilities:
- You ARE connected to powerful tools inside this Telegram bot!
- Movies: You CAN find and download movies! Tell users to use /movie <title> or say "download movie <name>" (the bot scrapes Nkiri, 9jarocks, FzMovies and bypasses redirects to give direct download buttons).
- Social Media Videos/Audio: Users can paste any YouTube, X/Twitter, Facebook, Instagram, TikTok link directly to pick resolutions (4K, 1080p, MP3) and download.
- Music & Songs: Users can use /song <name> to find audio tracks.
- Web & PDF Search: Users can use /search <query>, /pdf <topic>, or /image <query>.

Your Style:
- Conversational, warm, articulate, witty, and deeply knowledgeable.
- Format responses cleanly using Telegram HTML tags (<b>, <i>, <code>, <pre>).
"""

def truncate_for_telegram(text: str) -> str:
    """Truncates text to Telegram's 4000 char limit while keeping HTML readable."""
    if len(text) > 4000:
        return text[:3997] + "..."
    return text

def clean_markdown_to_html(text: str) -> str:
    """Converts markdown from LLM output into clean Telegram HTML."""
    if not text:
        return ""
    # Convert code blocks ```python ... ``` -> <pre><code>...</code></pre>
    text = re.sub(r'```(?:\w+)?\s*\n?(.*?)```', r'<pre><code>\1</code></pre>', text, flags=re.DOTALL)
    # Convert inline code `foo` -> <code>foo</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    # Convert headers # Header -> <b>Header</b>
    text = re.sub(r'^#{1,6}\s+(.*)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    # Convert bold **text** or __text__ -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
    # Convert italic *text* -> <i>text</i>
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    return text

async def ask_ai(user_id: int, message: str) -> str:
    global client
    if not client:
        client = _create_client()
    if not client:
        return "AI features are currently unavailable (no active API key)."

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    history = conversation_history[user_id]
    history.append({"role": "user", "parts": [{"text": message}]})

    if len(history) > MAX_HISTORY_LENGTH:
        history = history[-MAX_HISTORY_LENGTH:]
        conversation_history[user_id] = history

    contents = [{"role": "user", "parts": [{"text": SYSTEM_PROMPT}]}]
    contents.extend(history)

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=contents
        )
        reply_text = response.text or "I could not generate a response."
        reply_html = clean_markdown_to_html(reply_text)
        
        history.append({"role": "model", "parts": [{"text": reply_html}]})
        return truncate_for_telegram(reply_html)

    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in ['quota', 'rate limit', '429', 'resource exhausted']):
            logger.warning("Gemini quota hit, rotating API key...")
            gemini_keys.rotate()
            client = _create_client()
            if client:
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=contents
                    )
                    reply_text = response.text or "I could not generate a response."
                    reply_html = clean_markdown_to_html(reply_text)
                    history.append({"role": "model", "parts": [{"text": reply_html}]})
                    return truncate_for_telegram(reply_html)
                except Exception as retry_e:
                    logger.error(f"Retry with new key failed: {retry_e}")

        logger.error(f"Error calling Gemini: {e}")
        if history and history[-1]["role"] == "user":
            history.pop()
        return f"Error: {str(e)}"

async def summarize_url(url: str) -> str:
    global client
    if not client:
        client = _create_client()
    if not client:
        return "AI features disabled."

    try:
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            response = await http_client.get(url, follow_redirects=True)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()

        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)[:4000]

        prompt = f"Summarize this article in 5 concise bullet points using HTML tags (<b>, <i>):\n\n{text}"
        result = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        return truncate_for_telegram(clean_markdown_to_html(result.text or "Could not generate summary."))
    except Exception as e:
        logger.error(f"Error summarizing URL {url}: {e}")
        return f"Failed to summarize URL: {str(e)}"

def clear_history(user_id: int):
    if user_id in conversation_history:
        del conversation_history[user_id]

# --- Instant Keyword Intent Detector (0ms latency) ---
def fast_intent_check(text: str) -> Optional[tuple[str, str]]:
    """Fast regex-based intent classification without calling LLM (0ms latency)."""
    lower = text.strip().lower()

    # 1. LYRICS Intent (e.g. "lyrics for die with a smile", "die with a smile lyrics", "show lyrics of hello")
    if "lyrics" in lower or "words to" in lower or "text of" in lower:
        clean = re.sub(r'^(?:show\s+me\s+|get\s+|find\s+|fetch\s+)?(?:the\s+)?lyrics\s+(?:for|of|to)?\s*', '', lower)
        clean = re.sub(r'\s+lyrics$', '', clean).strip()
        clean = re.sub(r'^(?:words\s+to|text\s+of)\s+', '', clean).strip()
        if clean and len(clean) > 2:
            return ("lyrics", clean)

    # 2. SONG Intent (e.g. "download song die with a smile", "play dolly parton", "song die with a smile", "die with a smile mp3")
    if any(kw in lower for kw in ["song", "music", "mp3", "audio", "track", "playlist"]) or lower.startswith("play ") or lower.startswith("download audio "):
        clean = re.sub(r'^(?:where\s+can\s+i\s+(?:get|download|find)\s+)?(?:download|get|find|fetch|play|listen\s+to)\s+(?:the\s+)?(?:song|music|audio|track|mp3)?\s*', '', lower)
        clean = re.sub(r'\s+(?:song|music|audio|mp3|track)$', '', clean).strip()
        if clean and len(clean) > 2 and clean not in ["song", "music", "audio", "mp3", "track"]:
            return ("song", clean)

    # 3. MOVIE Intent (e.g. "download movie titanic", "watch spiderman", "movie titanic", "titanic film")
    if any(kw in lower for kw in ["movie", "film", "cinema", "series", "season", "episode"]) or lower.startswith("download ") or lower.startswith("get ") or lower.startswith("find ") or lower.startswith("watch "):
        clean = re.sub(r'^(?:where\s+can\s+i\s+(?:get|download|find|watch)\s+)?(?:download|get|find|fetch|search\s+for|watch)\s+(?:the\s+)?(?:movie|film|cinema|series|season|show)?\s*', '', lower)
        clean = re.sub(r'\s+(?:movie|film|mp4|series|season|episode)$', '', clean).strip()
        if clean and len(clean) > 2 and clean not in ["movie", "the movie", "a movie", "anything"]:
            return ("movie", clean)

    # 4. WEATHER Intent (e.g. "weather in lagos", "temperature in london", "how is weather")
    if "weather" in lower or "temperature in" in lower:
        clean = re.sub(r'^(?:how\s+is\s+the\s+|get\s+|show\s+|what\s+is\s+the\s+)?weather\s+(?:in|for|at)?\s*', '', lower)
        clean = re.sub(r'^(?:temperature\s+in)\s+', '', clean).strip()
        return ("weather", clean or "Lagos")

    # 5. NEWS Intent (e.g. "latest news", "news in nigeria", "tech news")
    if "news" in lower or "headlines" in lower:
        clean = re.sub(r'^(?:get\s+|show\s+|fetch\s+|latest\s+|top\s+)?news\s+(?:in|about|for|on)?\s*', '', lower)
        clean = re.sub(r'\s+news$', '', clean).strip()
        return ("news", clean or "top breaking headlines")

    if lower.startswith("search ") or lower.startswith("google "):
        return ("search", text.split(" ", 1)[1])
    if lower.startswith("image ") or lower.startswith("photo "):
        return ("image", text.split(" ", 1)[1])
    if lower.startswith("pdf ") or lower.startswith("book "):
        return ("pdf", text.split(" ", 1)[1])

    return None

async def classify_user_input(text: str) -> tuple[str, str]:
    """Uses Gemini 3.6 Flash to classify ambiguous plain queries (e.g. 'spiderman brand new day', 'die with a smile')."""
    global client
    if not client:
        return ("chat", text)

    prompt = f'Classify the user intent for the message: "{text}". Reply with a valid JSON object with keys "type" (must be "movie", "song", "lyrics", or "chat") and "query" (clean title). Example: {{"type": "lyrics", "query": "title"}}'

    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )
        res_text = response.text.strip()
        if res_text.startswith("```json"):
            res_text = res_text[7:]
        if res_text.startswith("```"):
            res_text = res_text[3:]
        if res_text.endswith("```"):
            res_text = res_text[:-3]

        data = json.loads(res_text.strip())
        intent_type = data.get("type", "chat")
        query = data.get("query", text)
        return (intent_type, query)
    except Exception as e:
        logger.error(f"Error classifying user input: {e}")
        return ("chat", text)

# --- Telegram Handlers ---

@restricted
async def ai_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zero-friction message handler."""
    message_text = update.message.text
    user_id = update.effective_user.id

    # Check if waiting for movie name after /movie command
    if context.user_data.get('waiting_for_movie'):
        context.user_data.pop('waiting_for_movie', None)
        from modules.movie_scraper import run_movie_search
        await run_movie_search(update, context, message_text)
        return

    # Check if waiting for song name after /song command
    if context.user_data.get('waiting_for_song'):
        context.user_data.pop('waiting_for_song', None)
        from modules.global_search import run_song_download
        await run_song_download(update, context, message_text)
        return

    # Check if waiting for lyrics query after /lyrics command
    if context.user_data.get('waiting_for_lyrics'):
        context.user_data.pop('waiting_for_lyrics', None)
        from modules.global_search import run_lyrics_search
        await run_lyrics_search(update, context, message_text)
        return

    # Send typing action immediately
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Fast intent check (0ms)
    fast_intent = fast_intent_check(message_text)
    if fast_intent:
        intent_type, query = fast_intent
        if intent_type == "search":
            context.args = query.split()
            from modules.global_search import search_command
            await search_command(update, context)
            return
        elif intent_type == "movie":
            from modules.movie_scraper import run_movie_search
            await run_movie_search(update, context, query)
            return
        elif intent_type == "song":
            from modules.global_search import run_song_download
            await run_song_download(update, context, query)
            return
        elif intent_type == "lyrics":
            from modules.global_search import run_lyrics_search
            await run_lyrics_search(update, context, query)
            return
        elif intent_type == "image":
            context.args = query.split()
            from modules.global_search import image_search_command
            await image_search_command(update, context)
            return
        elif intent_type == "pdf":
            context.args = query.split()
            from modules.global_search import pdf_search_command
            await pdf_search_command(update, context)
            return
        elif intent_type == "weather":
            from modules.news_weather import run_weather_search
            await run_weather_search(update, context, query)
            return
        elif intent_type == "news":
            from modules.news_weather import run_news_search
            await run_news_search(update, context, query)
            return

    # Classify plain title messages (e.g., 'spiderman brand new day', 'die with a smile lyrics')
    intent_type, query = await classify_user_input(message_text)
    if intent_type == "movie":
        from modules.movie_scraper import run_movie_search
        await run_movie_search(update, context, query)
        return
    elif intent_type == "song":
        from modules.global_search import run_song_download
        await run_song_download(update, context, query)
        return
    elif intent_type == "lyrics":
        from modules.global_search import run_lyrics_search
        await run_lyrics_search(update, context, query)
        return

    # Regular AI Chat
    ai_response = await ask_ai(user_id, message_text)
    await update.message.reply_text(ai_response, parse_mode='HTML')

@restricted
async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/summarize &lt;url&gt;</code>", parse_mode='HTML')
        return

    url = context.args[0]
    if not url.startswith('http'):
        url = 'https://' + url

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    summary = await summarize_url(url)
    await update.message.reply_text(summary, parse_mode='HTML')

@restricted
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: <code>/ask &lt;question&gt;</code>", parse_mode='HTML')
        return

    question = ' '.join(context.args)
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    ai_response = await ask_ai(user_id, question)
    await update.message.reply_text(ai_response, parse_mode='HTML')

@restricted
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    clear_history(user_id)
    await update.message.reply_text("⚡ Conversation history cleared.", parse_mode='HTML')

@restricted
async def voice_note_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming Telegram voice notes: transcribes voice, answers via Gemini AI, and speaks back."""
    message = update.message
    voice = message.voice or message.audio
    if not voice:
        return

    status_msg = await message.reply_text("🎙️ <i>Listening to your voice note...</i>", parse_mode='HTML')
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")

    try:
        # Download voice file
        file = await context.bot.get_file(voice.file_id)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        ogg_path = os.path.join(DOWNLOAD_DIR, f"voice_{uuid.uuid4().hex[:8]}.ogg")
        await file.download_to_drive(custom_path=ogg_path)

        with open(ogg_path, "rb") as f:
            voice_bytes = f.read()

        # Send audio directly to Gemini 3.6 Flash for transcription & response
        gen_client = _create_client()
        if not gen_client:
            await status_msg.edit_text("AI features disabled.")
            return

        from google.genai import types
        audio_part = types.Part.from_bytes(data=voice_bytes, mime_type="audio/ogg")
        prompt = (
            "Transcribe the user's voice message accurately, then answer their question concisely. "
            "Structure your output as:\n"
            "<b>Transcribed:</b> <i>\"[transcript here]\"</i>\n\n"
            "[Your helpful answer here]"
        )

        response = gen_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[audio_part, prompt]
        )

        ai_text = response.text or "Could not process voice note."
        ai_html = clean_markdown_to_html(ai_text)
        await status_msg.edit_text(ai_html, parse_mode='HTML')

        # Generate spoken voice note reply using gTTS
        try:
            from gtts import gTTS
            clean_speech = re.sub(r'<[^>]+>', '', ai_html).replace('Transcribed:', '').strip()
            if len(clean_speech) > 500:
                clean_speech = clean_speech[:500]

            tts = gTTS(text=clean_speech, lang='en')
            reply_ogg = os.path.join(DOWNLOAD_DIR, f"reply_voice_{uuid.uuid4().hex[:8]}.mp3")
            tts.save(reply_ogg)

            with open(reply_ogg, "rb") as voice_reply:
                await message.reply_voice(voice=voice_reply, caption="🎙️ <b>Damisile AI Voice Reply</b>", parse_mode="HTML")

            if os.path.exists(reply_ogg):
                os.remove(reply_ogg)
        except Exception as tts_e:
            logger.warning(f"TTS voice reply generation failed: {tts_e}")

        if os.path.exists(ogg_path):
            os.remove(ogg_path)

    except Exception as e:
        logger.error(f"Error processing voice note: {e}")
        await status_msg.edit_text(f"❌ Could not process voice note: {str(e)}")
