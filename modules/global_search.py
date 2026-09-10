import asyncio
import os
import httpx
import yt_dlp
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from google import genai
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from config import logger, restricted, GEMINI_API_KEY, gemini_keys, DOWNLOAD_DIR
from database import log_search
from modules.keyboards import search_type_keyboard

try:
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:
    client = None


def _get_gemini_client():
    """Get a Gemini client, creating with current rotated key."""
    global client
    key = gemini_keys.current_key
    if not key:
        return None
    client = genai.Client(api_key=key)
    return client

@restricted
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /search <query>")
        return

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

def _download_audio_track(query: str) -> dict:
    """Download audio track from YouTube / Spotify / YouTube Music using yt-dlp."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        'default_search': 'ytsearch1:',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if 'entries' in info and info['entries']:
            entry = info['entries'][0]
        else:
            entry = info
        filename = ydl.prepare_filename(entry)
        return {
            'filepath': filename,
            'title': entry.get('title', query),
            'uploader': entry.get('uploader', entry.get('artist', 'Damisile Music')),
            'duration': entry.get('duration', 0)
        }

@restricted
async def song_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        context.user_data['waiting_for_song'] = True
        await update.message.reply_text("🎵 <b>What song or playlist would you like to download?</b>\n\nJust reply with the song name (e.g. <code>Die With A Smile</code>, <code>Dolly Parton Jolene</code>, <code>Alan Walker</code>)!", parse_mode="HTML")
        return

    context.user_data.pop('waiting_for_song', None)
    await run_song_download(update, context, query)

async def run_song_download(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    status_msg = await update.message.reply_text(f"🎧 Fetching audio track for <b>{query}</b>...", parse_mode="HTML")

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: _download_audio_track(query))

        filepath = res['filepath']
        title = res['title']
        uploader = res['uploader']

        if os.path.exists(filepath):
            await status_msg.edit_text("⚡ Uploading audio track to chat...", parse_mode="HTML")
            with open(filepath, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer=uploader,
                    caption=f"🎧 <b>{title}</b>\n\n<i>Fetched by Damisile AI</i>",
                    parse_mode="HTML"
                )
            await status_msg.delete()
            log_search(query, "song", 1)

            try:
                os.remove(filepath)
            except Exception:
                pass
        else:
            await status_msg.edit_text("Could not download audio track.")

    except Exception as e:
        logger.error(f"Error downloading song {query}: {e}")
        await status_msg.edit_text(f"Failed to fetch song audio: {str(e)}")

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
    status_msg = await update.message.reply_text(f"🎤 Fetching lyrics for <b>{query}</b>...", parse_mode='HTML')
    lyrics_found = None

    # Ultra-Fast Primary Engine: Gemini 3.6 Flash Direct Lyrics (~800ms response)
    try:
        gen_client = _get_gemini_client()
        if gen_client:
            prompt = (
                f"Provide the complete, accurate song lyrics for '{query}'. "
                f"Format the lyrics beautifully for Telegram using HTML tags: <b>[Verse 1]</b>, <b>[Chorus]</b>, <i>lyrics line</i>. "
                f"Output ONLY the song title and full lyrics. Do NOT add conversational intros, outros, or markdown syntax."
            )
            ai_res = gen_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            if ai_res and ai_res.text:
                lyrics_found = ai_res.text
    except Exception as e:
        logger.error(f"Instant AI lyrics failed for {query}: {e}")

    # Fallback Engine: Web Scraping if AI fails
    if not lyrics_found:
        try:
            search_query = f"{query} lyrics genius OR azlyrics"
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=2))
            if results:
                lyrics_url = results[0].get('href', '')
                async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client_http:
                    headers = {"User-Agent": "Mozilla/5.0"}
                    resp = await client_http.get(lyrics_url, headers=headers)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        lyrics_found = soup.get_text(separator='\n', strip=True)[:4000]
        except Exception as e:
            logger.warning(f"Web lyrics fallback failed for {query}: {e}")

    if lyrics_found:
        reply_text = f"🎼 <b>Lyrics for {query.title()}</b>\n\n" + lyrics_found
        if len(reply_text) > 4000:
            reply_text = reply_text[:3950] + "\n\n<i>... (truncated)</i>"
        await status_msg.edit_text(reply_text, parse_mode='HTML', disable_web_page_preview=True)
        log_search(query, "lyrics", 1)
    else:
        await status_msg.edit_text(f"Could not find lyrics for '<b>{query}</b>'.", parse_mode='HTML')

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
