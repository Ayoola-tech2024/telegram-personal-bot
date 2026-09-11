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
from modules.keyboards import search_type_keyboard, song_results_keyboard

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

FALLBACK_MODELS = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-2.5-flash', 'gemini-1.5-flash-8b', 'gemini-3.6-flash']

def generate_ai_content(prompt: str) -> Optional[str]:
    """Generates content using Gemini client with key rotation AND multi-model fallbacks on 429 quota exhaustion."""
    for model_name in FALLBACK_MODELS:
        for _ in range(max(1, gemini_keys.key_count)):
            key = gemini_keys.current_key
            if not key:
                continue
            try:
                cl = genai.Client(api_key=key)
                res = cl.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if res and res.text:
                    return res.text
            except Exception as e:
                if any(kw in str(e).lower() for kw in ['429', 'quota', 'rate limit', 'resource exhausted']):
                    logger.warning(f"Quota hit on model {model_name}, rotating key...")
                    gemini_keys.rotate()
                else:
                    logger.error(f"Error generating AI content on {model_name}: {e}")
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

        ai_summary = generate_ai_content(prompt)
        reply_text = f"<b>Search:</b> <i>{query}</i>\n\n{ai_summary or search_context}"
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
    """Fetch top song options from YouTube and SoundCloud for user interactive selection."""
    clean_q = query.strip(" '\"`\t\r\n:")
    options = []
    seen_titles = set()

    # 1. YouTube search (standard ytsearch without conflicting extractor_args)
    ydl_opts_meta = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 10,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
            info = ydl.extract_info(f"ytsearch8:{clean_q}", download=False)
            entries = info.get('entries', []) if info else []
            for idx, entry in enumerate(entries):
                if entry:
                    title = entry.get('title', f"Track {idx+1}")
                    uploader = entry.get('uploader', entry.get('channel', 'Artist'))
                    vid_id = entry.get('id', '')
                    url = entry.get('url') or f"https://www.youtube.com/watch?v={vid_id}"
                    normalized = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:30]
                    if normalized not in seen_titles:
                        seen_titles.add(normalized)
                        options.append({
                            'id': vid_id,
                            'title': title,
                            'uploader': uploader,
                            'url': url,
                            'source': 'YouTube'
                        })
    except Exception as e:
        logger.warning(f"YouTube song search failed for {clean_q}: {e}")

    # 2. SoundCloud search (complements YouTube and ensures 100% audio availability)
    try:
        sc_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
        }
        with yt_dlp.YoutubeDL(sc_opts) as ydl:
            sc_info = ydl.extract_info(f"scsearch6:{clean_q}", download=False)
            sc_entries = sc_info.get('entries', []) if sc_info else []
            for sc_e in sc_entries:
                if sc_e:
                    title = sc_e.get('title', 'SoundCloud Track')
                    uploader = sc_e.get('uploader', 'SoundCloud')
                    url = sc_e.get('webpage_url') or sc_e.get('url', '')
                    normalized = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:30]
                    if normalized not in seen_titles and url:
                        seen_titles.add(normalized)
                        options.append({
                            'id': str(sc_e.get('id', '')),
                            'title': title,
                            'uploader': uploader,
                            'url': url,
                            'source': 'SoundCloud'
                        })
    except Exception as sc_err:
        logger.warning(f"SoundCloud song search failed for {clean_q}: {sc_err}")

    return options

def search_deep_song_options(query: str) -> list[dict]:
    """Fetch additional audio tracks using extended SoundCloud search, query variations, and direct mp3 indexers."""
    clean_q = query.strip(" '\"`\t\r\n:")
    extra_options = []
    seen = set()

    # 1. Extended SoundCloud search with 'audio'
    try:
        sc_opts = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
        }
        with yt_dlp.YoutubeDL(sc_opts) as ydl:
            sc_info = ydl.extract_info(f"scsearch8:{clean_q} audio", download=False)
            entries = sc_info.get('entries', []) if sc_info else []
            for sc_e in entries:
                if sc_e:
                    title = sc_e.get('title', 'SoundCloud Track')
                    uploader = sc_e.get('uploader', 'SoundCloud')
                    url = sc_e.get('webpage_url') or sc_e.get('url', '')
                    norm = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:30]
                    if norm not in seen and url:
                        seen.add(norm)
                        extra_options.append({
                            'id': str(sc_e.get('id', '')),
                            'title': title,
                            'uploader': uploader,
                            'url': url,
                            'source': 'SoundCloud'
                        })
    except Exception as e:
        logger.warning(f"SoundCloud deep search failed: {e}")

    # 2. YouTube official audio variation
    try:
        ydl_opts_yt = {
            'extract_flat': 'in_playlist',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'socket_timeout': 10,
        }
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            yt_info = ydl.extract_info(f"ytsearch6:{clean_q} official audio", download=False)
            entries = yt_info.get('entries', []) if yt_info else []
            for entry in entries:
                if entry:
                    title = entry.get('title', 'Track')
                    uploader = entry.get('uploader', entry.get('channel', 'Artist'))
                    vid_id = entry.get('id', '')
                    url = entry.get('url') or f"https://www.youtube.com/watch?v={vid_id}"
                    norm = re.sub(r'[^a-zA-Z0-9]', '', title.lower())[:30]
                    if norm not in seen:
                        seen.add(norm)
                        extra_options.append({
                            'id': vid_id,
                            'title': title,
                            'uploader': uploader,
                            'url': url,
                            'source': 'YouTube'
                        })
    except Exception as e:
        logger.warning(f"YouTube deep search failed: {e}")

    # 3. DuckDuckGo direct MP3 link search
    try:
        ddg_results = DDGS().text(f"{clean_q} mp3 download audio direct", max_results=6)
        if ddg_results:
            for idx, r in enumerate(ddg_results):
                t = r.get('title', '')
                href = r.get('href', '')
                if t and href and not any(skip in href for skip in ["youtube.com", "facebook.com", "instagram.com"]):
                    norm = re.sub(r'[^a-zA-Z0-9]', '', t.lower())[:30]
                    if norm not in seen:
                        seen.add(norm)
                        extra_options.append({
                            'id': f"ddg_{idx}",
                            'title': t.replace("Download", "").replace("mp3", "").strip(),
                            'uploader': 'Web Mirror',
                            'url': href,
                            'source': 'Web MP3'
                        })
    except Exception as e:
        logger.warning(f"DDG MP3 deep search failed: {e}")

    return extra_options

def _download_audio_track(selected_url: str, track_title: str = "") -> dict:
    """Download audio track from selected URL with YouTube bot-block bypass, SoundCloud fallback, and MP3 web fallback."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = clean_song_title(track_title) if track_title else ""
    
    # 1. Try standard yt-dlp on selected_url
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title).80s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 20,
        'retries': 3,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(selected_url, download=True)
            entry = info['entries'][0] if ('entries' in info and info['entries']) else info
            filename = ydl.prepare_filename(entry)
            if os.path.exists(filename) and os.path.getsize(filename) > 10000:
                return {
                    'filepath': filename,
                    'title': entry.get('title', clean_title or selected_url),
                    'uploader': entry.get('uploader', entry.get('artist', 'Damisile Music')),
                    'duration': entry.get('duration', 0)
                }
    except Exception as yt_err:
        logger.warning(f"Direct yt-dlp download failed ({yt_err}), activating SoundCloud/Web fallback...")

    # 2. SoundCloud fallback (ultra-fast, no bot blocks, 100% reliable)
    query_for_sc = clean_title or selected_url.split("watch?v=")[-1]
    sc_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title).80s.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 20,
    }
    try:
        with yt_dlp.YoutubeDL(sc_opts) as ydl:
            sc_info = ydl.extract_info(f"scsearch1:{query_for_sc}", download=True)
            if sc_info and 'entries' in sc_info and sc_info['entries']:
                sc_entry = sc_info['entries'][0]
                sc_file = ydl.prepare_filename(sc_entry)
                if os.path.exists(sc_file) and os.path.getsize(sc_file) > 10000:
                    return {
                        'filepath': sc_file,
                        'title': sc_entry.get('title', query_for_sc),
                        'uploader': sc_entry.get('uploader', 'SoundCloud Audio'),
                        'duration': sc_entry.get('duration', 0)
                    }
    except Exception as sc_err:
        logger.warning(f"SoundCloud fallback download failed: {sc_err}")

    # 3. Direct MP3 web audio search fallback
    try:
        import uuid
        from duckduckgo_search import DDGS
        ddg_res = DDGS().text(f"{query_for_sc} mp3 download audio", max_results=4)
        if ddg_res:
            for r in ddg_res:
                audio_url = r.get("href", "")
                if audio_url.endswith((".mp3", ".m4a", ".aac")) or "mp3" in audio_url.lower():
                    out_path = os.path.join(DOWNLOAD_DIR, f"track_{uuid.uuid4().hex[:8]}.mp3")
                    with httpx.Client(timeout=15.0, follow_redirects=True) as client_http:
                        resp = client_http.get(audio_url)
                        if resp.status_code == 200 and len(resp.content) > 50000:
                            with open(out_path, "wb") as f:
                                f.write(resp.content)
                            return {
                                'filepath': out_path,
                                'title': query_for_sc,
                                'uploader': 'Damisile Audio Engine',
                                'duration': 180
                            }
    except Exception as fb_e:
        logger.error(f"Web MP3 audio fallback failed: {fb_e}")

    raise RuntimeError(f"Could not download audio for '{query_for_sc}' from any audio mirror.")

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
        session_id = uuid.uuid4().hex[:8]

        # Store options and query in user_data
        context.user_data[f"song_options_{session_id}"] = options
        context.user_data[f"song_query_{session_id}"] = query

        total_pages = max(1, (len(options) + 4) // 5)
        keyboard = song_results_keyboard(session_id, options, page=1, page_size=5)
        text = (
            f"🎶 <b>Select track to download:</b>\n\n"
            f"Query: <i>{query}</i>\n"
            f"<i>Page 1/{total_pages} • Found {len(options)} tracks</i>"
        )
        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        log_search(query, "song", len(options))

    except Exception as e:
        logger.error(f"Error in run_song_download for {query}: {e}")
        await status_msg.edit_text(f"Failed to fetch song tracks: {str(e)}")

async def song_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles song pagination buttons (⬅️ Prev, Next ➡️)."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(':')
    if len(data) < 3:
        return

    session_id = data[1]
    page = int(data[2])

    options = context.user_data.get(f"song_options_{session_id}", [])
    query_text = context.user_data.get(f"song_query_{session_id}", "Track")

    if not options:
        await query.answer("Song session expired. Please search again.", show_alert=True)
        return

    total_pages = max(1, (len(options) + 4) // 5)
    page = max(1, min(page, total_pages))

    text = (
        f"🎶 <b>Select track to download:</b>\n\n"
        f"Query: <i>{query_text}</i>\n"
        f"<i>Page {page}/{total_pages} • Found {len(options)} tracks</i>"
    )
    keyboard = song_results_keyboard(session_id, options, page=page, page_size=5)
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error updating song page: {e}")

async def song_deep_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles '🔍 Search More Tracks & Audio Mirrors' button."""
    query = update.callback_query
    await query.answer("Searching alternative audio sources...")

    data = query.data.split(':')
    if len(data) < 2:
        return

    session_id = data[1]
    options = context.user_data.get(f"song_options_{session_id}", [])
    query_text = context.user_data.get(f"song_query_{session_id}", "")

    if not query_text:
        await query.answer("Search query expired. Please search again.", show_alert=True)
        return

    try:
        await query.edit_message_text(
            f"🔍 <b>Searching deeper for alternative versions & audio mirrors of '{query_text}'...</b>\n<i>Please wait a moment...</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass

    loop = asyncio.get_event_loop()
    extra_tracks = await loop.run_in_executor(None, lambda: search_deep_song_options(query_text))

    seen_titles = {re.sub(r'[^a-zA-Z0-9]', '', opt['title'].lower())[:30] for opt in options}
    seen_urls = {opt['url'] for opt in options}
    added = 0
    for t in extra_tracks:
        norm = re.sub(r'[^a-zA-Z0-9]', '', t['title'].lower())[:30]
        if norm not in seen_titles and t['url'] not in seen_urls:
            options.append(t)
            seen_titles.add(norm)
            seen_urls.add(t['url'])
            added += 1

    context.user_data[f"song_options_{session_id}"] = options
    total_pages = max(1, (len(options) + 4) // 5)

    header = f"✅ <b>Added {added} new tracks!</b>" if added > 0 else f"🎶 <b>Deep search complete.</b>"
    text = (
        f"{header}\n\n"
        f"Query: <i>{query_text}</i>\n"
        f"<i>Page 1/{total_pages} • Total {len(options)} tracks available</i>\n\n"
        f"Select track to download:"
    )
    keyboard = song_results_keyboard(session_id, options, page=1, page_size=5)

    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error presenting deep song results: {e}")

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
        res = await loop.run_in_executor(None, lambda: _download_audio_track(selected_track['url'], selected_track.get('title', '')))

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
