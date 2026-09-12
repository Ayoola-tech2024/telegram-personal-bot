"""
Sheet Music & Hymn Fetcher Module
=================================
Fetches classical piano sheet music and church hymns from public domain
and music score archives (IMSLP mirrors, OpenHymnal, Mutopia Project, 8Notes, etc.)
and delivers them directly as ready-to-play PDF documents in Telegram.
"""

import asyncio
import html
import os
import re
import uuid
import urllib.parse
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import logger, restricted, DOWNLOAD_DIR
from database import log_download, log_search, log_activity
from modules.keyboards import sheet_music_keyboard


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def clean_score_title(raw_title: str) -> str:
    """Clean clutter like 'PDF', '[PDF]', 'Download free sheet music', etc. from score title."""
    t = raw_title
    t = re.sub(r'(?i)^\s*(pdf|\[pdf\]|free sheet music|sheet music)\s*[-:|]\s*', '', t)
    t = re.sub(r'(?i)\s*[-:|]\s*(pdf|\[pdf\]|free sheet music|sheet music|8notes\.com|free-scores\.com|imslp|open hymnal|mutopia project)\s*$', '', t)
    t = re.sub(r'(?i)\b(pdf|download|printable|free|sheet music for piano|sheet music)\b', '', t)
    t = re.sub(r'\s+', ' ', t).strip(' -_:|')
    return t or raw_title


def detect_source_name(url: str) -> str:
    """Identify the host archive for clear labeling."""
    u_lower = url.lower()
    if "imslp.org" in u_lower or "imslp.info" in u_lower:
        return "IMSLP"
    if "openhymnal.org" in u_lower:
        return "OpenHymnal"
    if "mutopiaproject.org" in u_lower:
        return "Mutopia"
    if "8notes.com" in u_lower:
        return "8Notes"
    if "free-scores.com" in u_lower:
        return "Free-Scores"
    if "hymnary.org" in u_lower:
        return "Hymnary"
    if "pianostreet.com" in u_lower:
        return "PianoStreet"
    
    # Extract domain name
    try:
        domain = urllib.parse.urlparse(url).netloc
        domain = re.sub(r'^www\.', '', domain)
        return domain.split('.')[0].capitalize()
    except Exception:
        return "Web Score"


async def verify_pdf_url(client: httpx.AsyncClient, url: str) -> Optional[int]:
    """
    Checks if a candidate URL points to a valid PDF document.
    Returns file size in bytes if valid PDF (< 50MB), otherwise None.
    """
    try:
        resp = await client.head(url, timeout=5.0)
        ct = resp.headers.get("content-type", "").lower()
        if "application/pdf" in ct or url.lower().endswith(".pdf"):
            cl = resp.headers.get("content-length")
            size = int(cl) if cl and cl.isdigit() else 1024 * 1024
            if 0 < size < 52428800:  # < 50 MB
                return size
    except Exception:
        pass

    # Fast GET probe for servers that reject HEAD
    try:
        resp = await client.get(url, headers={"Range": "bytes=0-1024"}, timeout=5.0)
        if resp.status_code in (200, 206):
            ct = resp.headers.get("content-type", "").lower()
            if "application/pdf" in ct or resp.content.startswith(b"%PDF"):
                cl = resp.headers.get("content-length")
                size = int(cl) if cl and cl.isdigit() else len(resp.content)
                if size < 52428800:
                    return size
    except Exception:
        pass

    return None


class SheetMusicEngine:
    """Scrapes and indexes classical piano scores and hymn arrangements."""

    @staticmethod
    async def search_scores(query: str, max_results: int = 6) -> list[dict]:
        """
        Searches web score repositories for classical piano sheet music and hymn arrangements.
        Returns verified direct PDF scores.
        """
        clean_q = re.sub(r'(?i)\b(sheet music|notes|score|pdf|download|piano|hymn)\b', '', query).strip()
        if not clean_q:
            clean_q = query

        is_hymn = any(w in query.lower() for w in ["hymn", "worship", "praise", "choir", "faithfulness", "abide", "grace", "rugged", "cross", "glory", "holy", "salvation"])
        if is_hymn:
            queries = [
                f"{clean_q} hymn PDF score download",
                f"{clean_q} hymn sheet music piano SATB",
            ]
        else:
            queries = [
                f"{clean_q} piano sheet music IMSLP Mutopia",
                f"{clean_q} piano sheet music score PDF",
            ]

        candidate_links = []
        seen_urls = set()

        async with httpx.AsyncClient(timeout=10.0, headers=HEADERS, follow_redirects=True) as http_client:
            for q in queries:
                try:
                    resp = await http_client.post("https://html.duckduckgo.com/html/", data={"q": q})
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for a in soup.select("div.results_links h2 a"):
                            raw_href = a.get("href", "")
                            if "uddg=" in raw_href:
                                raw_href = urllib.parse.unquote(raw_href.split("uddg=")[1].split("&")[0])
                            
                            if raw_href and raw_href not in seen_urls:
                                seen_urls.add(raw_href)
                                title = a.text.strip()
                                candidate_links.append((raw_href, title))
                except Exception as search_err:
                    logger.warning(f"Score search error on query '{q}': {search_err}")

                if len(candidate_links) >= 10:
                    break

            # Verify which candidates are live downloadable PDFs (<50MB)
            verified_scores = []
            for url, raw_title in candidate_links:
                if len(verified_scores) >= max_results:
                    break

                # Filter for likely PDF links or score repositories
                u_lower = url.lower()
                is_promising = (
                    u_lower.endswith(".pdf") or
                    "/pdf" in u_lower or
                    "openhymnal.org" in u_lower or
                    "imslp" in u_lower or
                    "mutopiaproject.org" in u_lower or
                    "8notes.com" in u_lower or
                    "free-scores.com" in u_lower or
                    "hymnary.org" in u_lower or
                    "timelesstruths.org" in u_lower or
                    "greghowlett.com" in u_lower or
                    "mollychurchmusic.com" in u_lower
                )
                if not is_promising:
                    continue

                size = await verify_pdf_url(http_client, url)
                if size:
                    source = detect_source_name(url)
                    clean_title = clean_score_title(raw_title)
                    verified_scores.append({
                        "title": clean_title,
                        "source": source,
                        "url": url,
                        "size": size,
                        "score_type": "Hymn / Choral" if is_hymn or "openhymnal" in url.lower() else "Classical Piano"
                    })

        return verified_scores


@restricted
async def sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /sheet and /hymn commands.
    Usage:
      /sheet <classical piece or hymn>
      /hymn <hymn title>
    """
    query = " ".join(context.args) if context.args else ""
    if not query:
        context.user_data["waiting_for_sheet"] = True
        await update.message.reply_text(
            "🎹 <b>What sheet music or hymn do you need?</b>\n\n"
            "Reply with any classical piece or hymn title, for example:\n"
            "• <code>Chopin Nocturne Op 9 No 2</code>\n"
            "• <code>Great Is Thy Faithfulness</code>\n"
            "• <code>Beethoven Moonlight Sonata</code>\n"
            "• <code>Abide With Me</code>\n"
            "• <code>Debussy Clair de Lune</code>",
            parse_mode="HTML",
        )
        return

    context.user_data.pop("waiting_for_sheet", None)
    await run_sheet_search(update, context, query)


async def run_sheet_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    """Core sheet music search runner for commands and AI natural messages."""
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "sheet_music_search", query)

    status_msg = await update.message.reply_text(
        f"🔍 Searching scores & hymn arrangements for <b>{html.escape(query)}</b>...",
        parse_mode="HTML"
    )

    try:
        engine = SheetMusicEngine()
        scores = await engine.search_scores(query, max_results=6)

        if not scores:
            await status_msg.edit_text(
                f"❌ <b>No direct sheet music PDFs found for:</b> <i>{html.escape(query)}</i>\n\n"
                "💡 <i>Tip: Try including the composer (e.g. <code>Chopin</code> or <code>Bach</code>) or hymnal title.</i>",
                parse_mode="HTML"
            )
            log_search(query, "sheet_music", 0)
            return

        session_id = uuid.uuid4().hex[:8]
        context.user_data[f"sheet_scores_{session_id}"] = scores
        context.user_data[f"sheet_query_{session_id}"] = query

        total_pages = max(1, (len(scores) + 4) // 5)
        keyboard = sheet_music_keyboard(session_id, scores, page=1, page_size=5)

        text = (
            f"🎼 <b>Sheet Music & Hymn Scores Found:</b>\n\n"
            f"Query: <i>{html.escape(query)}</i>\n"
            f"<i>Select an arrangement below to receive the printable PDF directly in this chat:</i>"
        )
        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        log_search(query, "sheet_music", len(scores))

    except Exception as e:
        logger.error(f"Error in run_sheet_search for '{query}': {e}")
        await status_msg.edit_text(f"❌ Failed to fetch sheet music: {str(e)}")


async def sheet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle sheet music selection callback:
    Pattern: ^sheet:(?P<session_id>[a-f0-9]+):(?P<action>.+)$
    """
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    if len(data) < 3:
        return

    session_id = data[1]
    action = data[2]

    if action == "cancel":
        context.user_data.pop(f"sheet_scores_{session_id}", None)
        context.user_data.pop(f"sheet_query_{session_id}", None)
        await query.edit_message_text("❌ Sheet music selection cancelled.")
        return

    scores = context.user_data.get(f"sheet_scores_{session_id}", [])
    if not scores:
        await query.answer("Score session expired. Please search again.", show_alert=True)
        return

    try:
        idx = int(action)
        selected_score = scores[idx]
    except (ValueError, IndexError):
        await query.answer("Invalid score selected.", show_alert=True)
        return

    title = selected_score["title"]
    source = selected_score["source"]
    pdf_url = selected_score["url"]
    score_type = selected_score.get("score_type", "Piano Score")

    status_msg = await query.edit_message_text(
        f"⬇️ <b>Downloading PDF sheet music for:</b>\n"
        f"🎼 <i>{html.escape(title)}</i> [{source}]\n\n"
        f"<i>Preparing document for direct Telegram delivery...</i>",
        parse_mode="HTML"
    )

    local_pdf = None
    try:
        # Download PDF locally to send via send_document
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        safe_filename = re.sub(r'[^a-zA-Z0-9_\-\. ]', '', title).replace(' ', '_')[:40]
        local_pdf = os.path.join(DOWNLOAD_DIR, f"{safe_filename}_{session_id}.pdf")

        async with httpx.AsyncClient(timeout=25.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(pdf_url)
            if resp.status_code == 200 and (resp.content.startswith(b"%PDF") or len(resp.content) > 1000):
                with open(local_pdf, "wb") as f:
                    f.write(resp.content)
            else:
                raise ValueError(f"Could not retrieve PDF payload (HTTP {resp.status_code})")

        file_size = os.path.getsize(local_pdf)
        size_kb = file_size / 1024
        size_str = f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.0f} KB"

        caption = (
            f"🎹 <b>{html.escape(title)}</b>\n"
            f"🎼 <b>Category:</b> {score_type}\n"
            f"🏛️ <b>Source Archive:</b> {source}\n"
            f"📦 <b>Size:</b> {size_str}\n\n"
            f"<i>Ready for your piano music stand & tablet!</i>"
        )

        with open(local_pdf, "rb") as doc_file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=doc_file,
                filename=f"{safe_filename}.pdf",
                caption=caption,
                parse_mode="HTML"
            )

        await status_msg.delete()
        log_download(pdf_url, title, "sheet_music", file_size)

        user = update.effective_user
        if user:
            log_activity(user.id, user.username, user.first_name, "sheet_music_download", title)

    except Exception as e:
        logger.error(f"Error downloading score PDF from {pdf_url}: {e}")
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open PDF in Browser", url=pdf_url)]
        ])
        await status_msg.edit_text(
            f"⚠️ <b>Could not stream PDF directly:</b> {str(e)}\n\n"
            f"You can open and save the sheet music directly using this link:\n"
            f"<a href='{pdf_url}'>Click here to open {html.escape(title)}</a>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    finally:
        if local_pdf and os.path.exists(local_pdf):
            try:
                os.remove(local_pdf)
            except Exception:
                pass


async def sheet_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for sheet music results."""
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    if len(data) < 3:
        return

    session_id = data[1]
    page = int(data[2])

    scores = context.user_data.get(f"sheet_scores_{session_id}", [])
    query_text = context.user_data.get(f"sheet_query_{session_id}", "Score")

    if not scores:
        await query.answer("Score session expired. Please search again.", show_alert=True)
        return

    total_pages = max(1, (len(scores) + 4) // 5)
    page = max(1, min(page, total_pages))

    text = (
        f"🎼 <b>Sheet Music & Hymn Scores Found:</b>\n\n"
        f"Query: <i>{html.escape(query_text)}</i>\n"
        f"<i>Select an arrangement below (Page {page}/{total_pages}):</i>"
    )
    keyboard = sheet_music_keyboard(session_id, scores, page=page, page_size=5)
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error updating sheet music page: {e}")
