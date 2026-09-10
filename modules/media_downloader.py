import os
import re
import uuid
import asyncio
from pathlib import Path
import httpx
import yt_dlp
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, restricted, DOWNLOAD_DIR
from database import log_download, log_activity
from modules.keyboards import quality_keyboard, confirm_download_keyboard

URL_REGEX = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')

def is_supported_url(url: str) -> bool:
    supported_domains = [
        'youtube.com', 'youtu.be', 'twitter.com', 'x.com', 
        'facebook.com', 'instagram.com', 'tiktok.com', 
        'reddit.com', 'vimeo.com', 'twitch.tv'
    ]
    return any(domain in url for domain in supported_domains)

def format_duration(seconds: int) -> str:
    if seconds is None:
        return "Unknown"
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def format_filesize(bytes_size: int) -> str:
    if not bytes_size:
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

def _extract_formats_sync(url: str) -> dict:
    options = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extract_flat': False,
        'extractor_args': {
            'youtube': ['player_client=ios,mweb,android,web']
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        }
    }
    
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
        
        formats_list = []
        if 'formats' in info:
            seen_resolutions = set()
            for f in sorted(info['formats'], key=lambda x: x.get('height', 0) or 0, reverse=True):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    height = f.get('height')
                    if height and height not in seen_resolutions:
                        seen_resolutions.add(height)
                        formats_list.append({
                            'format_id': f['format_id'],
                            'label': f"🎥 {height}p",
                            'ext': f.get('ext', 'mp4'),
                            'filesize': f.get('filesize') or f.get('filesize_approx')
                        })
            
            if not formats_list:
                for f in sorted(info['formats'], key=lambda x: x.get('height', 0) or 0, reverse=True):
                    height = f.get('height')
                    if height and height not in seen_resolutions:
                        seen_resolutions.add(height)
                        formats_list.append({
                            'format_id': f['format_id'] + '+bestaudio',
                            'label': f"🎥 {height}p",
                            'ext': 'mp4',
                            'filesize': f.get('filesize') or f.get('filesize_approx')
                        })
        
        return {
            'title': info.get('title', 'Unknown Title'),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'formats': formats_list[:5]
        }

async def extract_formats(url: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_formats_sync, url)

def _download_media_sync(url: str, format_id: str = 'best', audio_only: bool = False) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename_template = os.path.join(DOWNLOAD_DIR, '%(title).100s_%(id)s.%(ext)s')
    
    options = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'outtmpl': filename_template,
        'extractor_args': {
            'youtube': ['player_client=ios,mweb,android,web']
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        }
    }
    
    if audio_only:
        options['format'] = 'bestaudio/best'
        options['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        options['format'] = format_id if format_id != 'best' else 'bestvideo+bestaudio/best'
        options['merge_output_format'] = 'mp4'

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

async def download_media(url: str, format_id: str = 'best', audio_only: bool = False) -> str:
    loop = asyncio.get_event_loop()
    if audio_only:
        filepath = await loop.run_in_executor(None, _download_media_sync, url, format_id, True)
        return filepath.rsplit('.', 1)[0] + '.mp3'
    else:
        filepath = await loop.run_in_executor(None, _download_media_sync, url, format_id, False)
        if not filepath.endswith('.mp4'):
            filepath = filepath.rsplit('.', 1)[0] + '.mp4'
        return filepath

async def download_direct_file(url: str, filename: str = None) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    async with httpx.AsyncClient() as client:
        async with client.stream('GET', url) as response:
            response.raise_for_status()
            if not filename:
                cd = response.headers.get('content-disposition')
                if cd and 'filename=' in cd:
                    filename = cd.split('filename=')[1].strip('\"\'')
                else:
                    filename = url.split('/')[-1].split('?')[0] or f"file_{uuid.uuid4().hex[:8]}"
            
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            with open(filepath, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
            return filepath

def cleanup_file(filepath: str):
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            logger.error(f"Failed to cleanup file {filepath}: {e}")

def is_shortform_social_url(url: str) -> bool:
    """Check if URL is an Instagram Reel, TikTok video, YouTube Short, Twitter/X video, or Facebook Watch."""
    lower = url.lower()
    patterns = [
        "instagram.com/reel", "instagram.com/p/", "instagr.am/",
        "tiktok.com/", "vm.tiktok.com/",
        "youtube.com/shorts/", "youtu.be/shorts/",
        "x.com/", "/status/", "twitter.com/",
        "fb.watch/", "facebook.com/reel"
    ]
    return any(p in lower for p in patterns)

@restricted
async def url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    urls = URL_REGEX.findall(message.text)
    if not urls:
        return

    url = urls[0]
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "media_link", url)

    session_id = uuid.uuid4().hex[:8]
    
    # PLAYLIST AUTO-EXTRACTOR (Spotify / YouTube Playlist)
    if 'playlist' in url.lower() or 'list=' in url.lower() or 'open.spotify.com' in url.lower():
        status_msg = await message.reply_text("🎵 <b>Playlist link detected! Extracting audio batch...</b>", parse_mode="HTML")
        try:
            from modules.global_search import run_song_download
            query_term = url.split('/')[-1].split('?')[0].replace('-', ' ').replace('_', ' ')
            await status_msg.delete()
            await run_song_download(update, context, query_term if len(query_term) > 3 else "top hits")
            return
        except Exception as pl_e:
            logger.error(f"Playlist auto-extraction failed for {url}: {pl_e}")

    # ZERO-CLICK AUTO EXTRACTOR for Instagram Reels, TikToks, Shorts, X videos
    if is_shortform_social_url(url):
        status_msg = await message.reply_text("⚡ <b>Downloading video directly...</b>", parse_mode="HTML")
        try:
            filepath = await download_media(url, format_id='best')
            if os.path.exists(filepath):
                await status_msg.edit_text("⬆️ <b>Uploading video to chat...</b>", parse_mode="HTML")
                with open(filepath, 'rb') as video_file:
                    await message.reply_video(
                        video=video_file,
                        caption="🎬 <b>Downloaded by Damisile AI</b>",
                        parse_mode="HTML"
                    )
                await status_msg.delete()
                cleanup_file(filepath)
                log_download(url, "video", os.path.getsize(filepath) if os.path.exists(filepath) else 0)
                return
        except Exception as e:
            logger.error(f"Zero-click video auto-download failed for {url}: {e}")
            await status_msg.edit_text(f"❌ Could not auto-download video: {str(e)}")
            # Fallback to standard quality selector below if needed

    if is_supported_url(url):
        status_msg = await message.reply_text("🔄 Extracting media info...")
        try:
            info = await extract_formats(url)
            context.user_data[session_id] = {'url': url, 'info': info}
            
            duration_str = format_duration(info['duration'])
            text = f"🎬 *{info['title']}*\n⏱ Duration: {duration_str}\n\nSelect quality:"
            
            keyboard = quality_keyboard(session_id, info['formats'])
            
            if info['thumbnail']:
                await message.reply_photo(photo=info['thumbnail'], caption=text, reply_markup=keyboard, parse_mode='Markdown')
                await status_msg.delete()
            else:
                await status_msg.edit_text(text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            await status_msg.edit_text(f"❌ Failed to extract info: {str(e)}")
    else:
        context.user_data[session_id] = {'url': url}
        keyboard = confirm_download_keyboard(session_id)
        await message.reply_text(f"🔗 Direct link detected.\n\nURL: {url}\n\nDo you want to download this file?", reply_markup=keyboard)

async def download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(':')
    if len(data) < 3:
        return
        
    session_id = data[1]
    format_id = data[2]
    
    session_data = context.user_data.get(session_id)
    if not session_data:
        # edit_message_caption normally fails if there is no photo, edit_message_text used if text
        if query.message.photo:
            await query.edit_message_caption("❌ Session expired.")
        else:
            await query.edit_message_text("❌ Session expired.")
        return
        
    url = session_data['url']
    info = session_data['info']
    
    status_msg = await query.message.reply_text('⬇️ Downloading... please wait')
    
    filepath = None
    try:
        audio_only = (format_id == 'audio')
        filepath = await download_media(url, format_id if not audio_only else 'best', audio_only)
        
        file_size = os.path.getsize(filepath)
        file_size_str = format_filesize(file_size)
        
        if file_size > 2 * 1024 * 1024 * 1024:
            await status_msg.edit_text(f"⚠️ File is too large ({file_size_str}) for Telegram (>2GB).\nDirect URL: {url}")
        else:
            await status_msg.edit_text('⬆️ Uploading to Telegram...')
            with open(filepath, 'rb') as f:
                if file_size > 50 * 1024 * 1024:
                    await query.message.reply_document(document=f, caption=info['title'])
                elif audio_only:
                    await query.message.reply_audio(audio=f, caption=info['title'])
                else:
                    await query.message.reply_video(video=f, caption=info['title'])
            
            log_download(url, info['title'], "media", filepath or "", file_size)
            await status_msg.delete()
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Download failed: {str(e)}")
    finally:
        if filepath:
            cleanup_file(filepath)

async def direct_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split(':')
    if len(data) < 2:
        return
        
    session_id = data[1]
    session_data = context.user_data.get(session_id)
    
    if not session_data:
        await query.edit_message_text("❌ Session expired.")
        return
        
    url = session_data['url']
    status_msg = await query.message.reply_text('⬇️ Downloading... please wait')
    
    filepath = None
    try:
        filepath = await download_direct_file(url)
        file_size = os.path.getsize(filepath)
        
        if file_size > 2 * 1024 * 1024 * 1024:
            await status_msg.edit_text(f"⚠️ File is too large for Telegram (>2GB).\nDirect URL: {url}")
        else:
            await status_msg.edit_text('⬆️ Uploading to Telegram...')
            with open(filepath, 'rb') as f:
                await query.message.reply_document(document=f)
            
            log_download(url, "", "direct", filepath or "", file_size)
            await status_msg.delete()
    except Exception as e:
        logger.error(f"Direct download error: {e}")
        await status_msg.edit_text(f"❌ Download failed: {str(e)}")
    finally:
        if filepath:
            cleanup_file(filepath)
