import asyncio
import os
import re
from typing import Optional
import httpx
import yt_dlp
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from google import genai
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from config import logger, restricted, GEMINI_API_KEY, gemini_keys, DOWNLOAD_DIR
from database import log_search, log_activity
from modules.keyboards import search_type_keyboard

try:
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:
    client = None


def clean_song_title(title: str) -> str:
    """Clean YouTube clutter and video tags from song title."""
    title = re.sub(r'(?i)\((lyrics|official music video|official video|audio|video|lyric video|4k upgrade|hd|remix)\)', '', title)
    title = re.sub(r'(?i)\[(lyrics|official music video|official video|audio|video|lyric video|4k upgrade|hd|remix)\]', '', title)
    title = re.sub(r'(?i)\b(lyrics|official video|music video|audio)\b', '', title)
    return title.strip(' -_\t\r\n')


def _get_gemini_client():
    """Get a Gemini client, creating with current rotated key."""
    global client
    key = gemini_keys.current_key
    if not key:
        return None
    client = genai.Client(api_key=key)
    return client

def generate_ai_content(prompt: str) -> Optional[str]:
    """Generates content using Gemini client with automatic key rotation on 429 quota exhaustion."""
    for _ in range(max(1, gemini_keys.key_count)):
        key = gemini_keys.current_key
        if not key:
            return None
        try:
            cl = genai.Client(api_key=key)
            res = cl.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            if res and res.text:
                return res.text
        except Exception as e:
            if any(kw in str(e).lower() for kw in ['429', 'quota', 'rate limit', 'resource exhausted']):
                logger.warning("Quota hit in global_search, rotating key...")
                gemini_keys.rotate()
            else:
                logger.error(f"Error generating AI content: {e}")
                break
    return None

@restricted
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /search <query>")
        return

    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "web_search", query)

    status_msg = await update.message.reply_text('🔍 Searching...', parse_mode='HTML')
    
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: DDGS().text(query, max_results=5))
            
        if not results:
            await status_msg.edit_text("No results found for your query.")
            log_search(query, "text", 0)
            return

        log_search(query, "text", len(results))

        snippets = []
        for r in results:
            title = r.get('title', 'No title')
            body = r.get('body', 'No description')
            link = r.get('href', '')
            snippets.append(f"Title: {title}\nSummary: {body}\nLink: {link}")

        search_context = "\n\n".join(snippets)
        prompt = (
            f"You are a helpful search assistant. Based on the following web search results for the query '{query}', "
            f"write a concise, informative summary. "
            f"Include inline citations to the sources using HTML links (<a href='url'>Link text</a>). "
            f"Format the output using ONLY these HTML tags: <b>, <i>, <a>, <code>, <pre>. "
            f"Do not use markdown formatting like ** or *.\n\n"
            f"Search Results:\n{search_context}"
        )

        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt
        )

        reply_text = f"<b>Search:</b> <i>{query}</i>\n\n{response.text}"
        await status_msg.edit_text(reply_text, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in search_command: {e}")
        await status_msg.edit_text("An error occurred while searching.")

@restricted
async def image_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /image <query>")
        return

    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "image_search", query)

    status_msg = await update.message.reply_text('🔍 Searching for images...', parse_mode='HTML')
    
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: DDGS().images(query, max_results=4))

        if not results:
            await status_msg.edit_text("No images found for your query.")
            log_search(query, "image", 0)
            return

        log_search(query, "image", len(results))
        
        media_group = []
        for res in results:
            image_url = res.get('image')
            if image_url:
                media_group.append(InputMediaPhoto(media=image_url))

        if media_group:
            await update.message.reply_media_group(media=media_group)
            await status_msg.delete()
        else:
            await status_msg.edit_text("Could not retrieve images.")

    except Exception as e:
        logger.error(f"Error in image_search_command: {e}")
        await status_msg.edit_text("An error occurred while searching for images.")

def search_song_options(query: str) -> list[dict]:
    """Fetch top 5 song options for user interactive selection."""
    search_query = f"ytsearch5:{query} audio"
    ydl_opts_meta = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
    }
    options = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
            info = ydl.extract_info(search_query, download=False)
            entries = info.get('entries', []) if info else []
            for idx, entry in enumerate(entries[:5]):
                title = entry.get('title', f"Track {idx+1}")
                uploader = entry.get('uploader', entry.get('channel', 'Artist'))
                vid_id = entry.get('id', '')
                url = entry.get('url') or f"https://www.youtube.com/watch?v={vid_id}"
                options.append({
                    'id': vid_id,
                    'title': title,
                    'uploader': uploader,
                    'url': url
                })
    except Exception as e:
        logger.error(f"Error fetching song options for {query}: {e}")
    return options

def _download_audio_track(selected_url: str) -> dict:
    """Download audio track from selected URL."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 30,
        'retries': 3,
        'extractor_args': {'youtube': ['player_client=android']},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(selected_url, download=True)
        if 'entries' in info and info['entries']:
            entry = info['entries'][0]
        else:
            entry = info
        filename = ydl.prepare_filename(entry)
        return {
            'filepath': filename,
            'title': entry.get('title', selected_url),
            'uploader': entry.get('uploader', entry.get('artist', 'Damisile Music')),
            'duration': entry.get('duration', 0)
        }

@restricted
async def song_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        context.user_data['waiting_for_song'] = True
        await update.message.reply_text("🎵 <b>What song or playlist would you like to download?</b>\n\nJust reply with the song name (e.g. <code>Die With A Smile</code>, <code>Fade</code>, <code>Those Eyes</code>)!", parse_mode="HTML")
        return

    context.user_data.pop('waiting_for_song', None)
    await run_song_download(update, context, query)

async def run_song_download(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "song_search", query)

    status_msg = await update.message.reply_text(f"🔍 Searching audio tracks for <b>{query}</b>...", parse_mode="HTML")

    try:
        loop = asyncio.get_event_loop()
        options = await loop.run_in_executor(None, lambda: search_song_options(query))

        if not options:
            await status_msg.edit_text(f"No audio tracks found for '<b>{query}</b>'.", parse_mode="HTML")
            return

        import uuid
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        session_id = uuid.uuid4().hex[:8]

        # Store options in user_data
        context.user_data[f"song_options_{session_id}"] = options

        buttons = []
        for idx, opt in enumerate(options):
            label = f"🎵 {idx+1}. {opt['title'][:40]}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"songselect:{session_id}:{idx}")])

        keyboard = InlineKeyboardMarkup(buttons)
        text = f"🎶 <b>Select track to download:</b>\n\nQuery: <i>{query}</i>"
        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        log_search(query, "song", len(options))

    except Exception as e:
        logger.error(f"Error in run_song_download for {query}: {e}")
        await status_msg.edit_text(f"Failed to fetch song tracks: {str(e)}")

async def song_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles song track selection from interactive menu."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) < 3:
        return

    session_id = data[1]
    idx = int(data[2])

    options = context.user_data.get(f"song_options_{session_id}")
    if not options or idx >= len(options):
        await query.edit_message_text("❌ Song selection session expired.")
        return

    selected_track = options[idx]
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "song_download", selected_track['title'])

    await query.edit_message_text(f"⚡ Downloading <b>{selected_track['title']}</b>...", parse_mode="HTML")

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: _download_audio_track(selected_track['url']))

        filepath = res['filepath']
        title = res['title']
        uploader = res['uploader']

        if os.path.exists(filepath):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            context.user_data[f"songtitle_{session_id}"] = title
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("📜 View Song Lyrics", callback_data=f"songlyrics:{session_id}")]])

            with open(filepath, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer=uploader,
                    caption=f"🎧 <b>{title}</b>\n\n<i>Fetched by Damisile AI</i>",
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            await query.message.delete()

            try:
                os.remove(filepath)
            except Exception:
                pass
        else:
            await query.message.reply_text("Could not download selected audio track.")

    except Exception as e:
        logger.error(f"Error downloading selected track: {e}")
        await query.message.reply_text(f"Failed to download audio track: {str(e)}")

async def song_lyrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles '📜 View Song Lyrics' button clicks on audio messages."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) < 2:
        return

    session_id = data[1]
    title = context.user_data.get(f"songtitle_{session_id}", "")
    if not title:
        await query.message.reply_text("❌ Lyrics session expired.")
        return

    await run_lyrics_search(update, context, title)

@restricted
async def lyrics_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        context.user_data['waiting_for_lyrics'] = True
        await update.message.reply_text("📜 <b>What song's lyrics are you looking for?</b>\n\nJust reply with the song title (e.g. <code>Die With A Smile</code>, <code>Bohemian Rhapsody</code>)!", parse_mode="HTML")
        return

    context.user_data.pop('waiting_for_lyrics', None)
    await run_lyrics_search(update, context, query)

async def run_lyrics_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    msg_target = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg_target:
        return

    clean_title = clean_song_title(query)
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "lyrics", clean_title)
    status_msg = await msg_target.reply_text(f"🎤 Fetching lyrics for <b>{clean_title}</b>...", parse_mode='HTML')
    lyrics_found = None

    # Step 1: Web Search ground-truth lyrics lookup
    web_text = ""
    try:
        search_query = f"{clean_title} lyrics genius"
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=3))
        if results:
            snippets = []
            for r in results:
                snippets.append(f"Title: {r.get('title','')}\nSnippet: {r.get('body','')}")
            web_text = "\n\n".join(snippets)
    except Exception as e:
        logger.warning(f"Web lyrics search failed for {clean_title}: {e}")

    # Step 2: Extract lyrics using Gemini with Web Grounding
    if web_text:
        try:
            prompt = (
                f"You are a song lyrics assistant. Extract and format the complete, accurate song lyrics for '{clean_title}' "
                f"using the following search results as the primary source of truth:\n\n"
                f"Search Context:\n{web_text}\n\n"
                f"Format the lyrics for Telegram using ONLY HTML tags: <b>[Verse 1]</b>, <b>[Chorus]</b>, <i>line</i>. "
                f"Output ONLY the song title header and lyrics. Do NOT add intros, outros, conversational comments or markdown syntax."
            )
            lyrics_found = generate_ai_content(prompt)
        except Exception as e:
            logger.error(f"AI lyrics extraction with web context failed for {clean_title}: {e}")

    # Step 3: Web Scraping Fallback (Genius / AZLyrics page scraper)
    if not lyrics_found:
        try:
            search_query = f"{clean_title} lyrics genius OR azlyrics"
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=2))
            if results:
                lyrics_url = results[0].get('href', '')
                async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client_http:
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    resp = await client_http.get(lyrics_url, headers=headers)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        page_text = soup.get_text(separator='\n', strip=True)[:4000]
                        prompt = (
                            f"Extract and clean the song lyrics for '{clean_title}' from this web page content. "
                            f"Format nicely with HTML tags (e.g. <b>[Chorus]</b>). Output ONLY title and lyrics:\n\n{page_text}"
                        )
                        lyrics_found = generate_ai_content(prompt)
        except Exception as e:
            logger.warning(f"Web page scrape fallback failed for {clean_title}: {e}")

    # Step 4: Direct AI Prompt Fallback
    if not lyrics_found:
        try:
            prompt = (
                f"Provide the complete, accurate song lyrics for '{clean_title}'. "
                f"Format with Telegram HTML tags: <b>[Verse 1]</b>, <b>[Chorus]</b>. Output ONLY song title and lyrics."
            )
            lyrics_found = generate_ai_content(prompt)
        except Exception as e:
            logger.error(f"Direct AI lyrics fallback failed for {clean_title}: {e}")

    if lyrics_found:
        reply_text = f"🎼 <b>Lyrics for {clean_title.title()}</b>\n\n" + lyrics_found
        if len(reply_text) > 4000:
            reply_text = reply_text[:3950] + "\n\n<i>... (truncated)</i>"
        await status_msg.edit_text(reply_text, parse_mode='HTML', disable_web_page_preview=True)
        log_search(clean_title, "lyrics", 1)
    else:
        await status_msg.edit_text(f"Could not find lyrics for '<b>{clean_title}</b>'.", parse_mode='HTML')

@restricted
async def pdf_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /pdf <query>")
        return

    status_msg = await update.message.reply_text('🔍 Searching for PDFs...', parse_mode='HTML')
    search_query = f"{query} filetype:pdf"

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=5))

        if not results:
            await status_msg.edit_text("No PDF results found.")
            log_search(query, "pdf", 0)
            return

        log_search(query, "pdf", len(results))

        response_text = f"<b>PDF Results for:</b> <i>{query}</i>\n\n"
        for i, res in enumerate(results, 1):
            title = res.get('title', 'Unknown Document')
            link = res.get('href', '')
            response_text += f"{i}. <a href='{link}'>{title}</a>\n"
            
        await status_msg.edit_text(response_text, parse_mode='HTML', disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Error in pdf_search_command: {e}")
        await status_msg.edit_text("An error occurred while searching for PDFs.")

@restricted
async def movie_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Please provide a movie title. Usage: /movie <title>")
        return

    status_msg = await update.message.reply_text('🔍 Searching for movies...', parse_mode='HTML')
    search_query = f"{query} site:nkiri.com OR site:9jarocks.com OR site:nollysource.com OR site:netnaija.com OR site:fzmovies.net"

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=7))

        if not results:
            await status_msg.edit_text("No movie results found on known sites.")
            log_search(query, "movie", 0)
            return

        log_search(query, "movie", len(results))

        response_text = f"<b>Movie Results for:</b> <i>{query}</i>\n\n"
        for i, res in enumerate(results, 1):
            title = res.get('title', 'Unknown Movie')
            link = res.get('href', '')
            site = "Unknown Site"
            if "nkiri" in link.lower(): site = "Nkiri"
            elif "9jarocks" in link.lower(): site = "9jarocks"
            elif "nollysource" in link.lower(): site = "Nollysource"
            elif "netnaija" in link.lower(): site = "Netnaija"
            elif "fzmovies" in link.lower(): site = "Fzmovies"
            
            response_text += f"{i}. <b>[{site}]</b> <a href='{link}'>{title}</a>\n"
            
        await status_msg.edit_text(response_text, parse_mode='HTML', disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"Error in movie_search_command: {e}")
        await status_msg.edit_text("An error occurred while searching for the movie.")
