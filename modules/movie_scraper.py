import asyncio
import re
import urllib.parse
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes

from config import logger, restricted, DOWNLOAD_DIR
from database import log_download, log_activity
from modules.keyboards import movie_results_keyboard, movie_download_keyboard

from duckduckgo_search import DDGS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

class MovieScraper:
    async def _fetch(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=3.0, verify=False) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
        return None

    async def search_9jarocks(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://www.my9jarocks.bz/findx?search={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "/videodownload/" in href and href not in seen:
                if not title:
                    title = href.split("/")[-1].replace(".html", "").replace("-", " ").title()

                seen.add(href)
                year_match = re.search(r"\b(19|20)\d{2}\b", title)
                year = year_match.group(0) if year_match else ""

                results.append({
                    "id": f"9j_{len(results)}",
                    "title": title,
                    "year": year,
                    "quality": "HD",
                    "poster_url": "",
                    "page_url": href if href.startswith("http") else f"https://www.my9jarocks.bz{href}",
                    "source": "9jarocks"
                })
        return results[:8]

    async def search_thenkiri(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://thenkiri.com/?s={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "thenkiri.com/" in href and "-download-" in href and href not in seen:
                if title and title.lower() not in ["continue reading", "download"]:
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"nk_{len(results)}",
                        "title": title.replace(" | Download Hollywood Movie", "").replace(" | Download Hollywood Documentary", ""),
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href,
                        "source": "TheNkiri"
                    })
        return results[:8]

    async def search_naijaprey(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://www.naijaprey.tv/?s={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "naijaprey.tv/" in href and href.count("/") >= 4 and href not in seen:
                if title and len(title) > 3 and not title.isdigit() and title != "[…]":
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"np_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href,
                        "source": "NaijaPrey"
                    })
        return results[:8]

    async def search_thenetnaija(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://thenetnaija.com.ng/?s={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "thenetnaija.com.ng/" in href and href.count("/") >= 4 and href not in seen:
                if title and len(title) > 3 and not title.isdigit() and title != "[…]":
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"nn_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href,
                        "source": "TheNetNaija"
                    })
        return results[:8]

    async def search_seriezloaded(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://www.seriezloaded.com.ng/?s={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "seriezloaded" in href and href.count("/") >= 4 and href not in seen:
                if title and len(title) > 3 and title != "[…]":
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"sl_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href,
                        "source": "SeriezLoaded"
                    })
        return results[:8]

    async def search_nollysauce(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://nollysaucemovies.blogspot.com/search?q={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "nollysaucemovies.blogspot.com/" in href and ".html" in href and href not in seen:
                if title and len(title) > 3 and "search?" not in href:
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"ns_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href,
                        "source": "NollySauce"
                    })
        return results[:8]

    async def search_waploaded(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://films.waploaded.com/search.php?keyword={urllib.parse.quote(query)}"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "waploaded.com/" in href and href.count("/") >= 4 and href not in seen:
                if title and len(title) > 3 and not title.isdigit():
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"wl_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD",
                        "poster_url": "",
                        "page_url": href if href.startswith("http") else f"https://films.waploaded.com{href}",
                        "source": "Waploaded"
                    })
        return results[:8]

    async def search_1337x(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://1337x.to/search/{urllib.parse.quote(query)}/1/"
        html = await self._fetch(url)
        results = []
        if not html:
            return results

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)
        seen = set()

        for a in a_tags:
            href = a["href"]
            title = a.text.strip()
            if "/torrent/" in href and href not in seen:
                if title and len(title) > 3:
                    seen.add(href)
                    year_match = re.search(r"\b(19|20)\d{2}\b", title)
                    year = year_match.group(0) if year_match else ""
                    results.append({
                        "id": f"tx_{len(results)}",
                        "title": title,
                        "year": year,
                        "quality": "HD Torrent",
                        "poster_url": "",
                        "page_url": f"https://1337x.to{href}" if href.startswith("/") else href,
                        "source": "1337x Torrent"
                    })
        return results[:8]

    async def search_web_indexer(self, query: str) -> List[Dict[str, Any]]:
        """Index results across user's movie list via web search engine."""
        results = []
        try:
            loop = asyncio.get_event_loop()
            search_query = f"{query} site:nollysaucemovies.blogspot.com OR site:films.waploaded.com OR site:fzmovies.net OR site:1337x.to OR site:9jarocks.net OR site:thenkiri.com OR site:naijaprey.tv OR site:thenetnaija.com.ng"
            ddg_res = await loop.run_in_executor(None, lambda: DDGS().text(search_query, max_results=6))
            if ddg_res:
                for idx, r in enumerate(ddg_res):
                    title = r.get("title", "")
                    href = r.get("href", "")
                    if title and href:
                        domain = urllib.parse.urlparse(href).netloc.replace("www.", "")
                        results.append({
                            "id": f"wi_{idx}",
                            "title": title,
                            "year": "",
                            "quality": "HD",
                            "poster_url": "",
                            "page_url": href,
                            "source": domain.split(".")[0].title()
                        })
        except Exception as e:
            logger.error(f"Error in search_web_indexer: {e}")
        return results

    async def search_all(self, query: str) -> List[Dict[str, Any]]:
        tasks = [
            self.search_9jarocks(query),
            self.search_thenkiri(query),
            self.search_naijaprey(query),
            self.search_thenetnaija(query),
            self.search_seriezloaded(query),
            self.search_nollysauce(query),
            self.search_waploaded(query),
            self.search_1337x(query),
            self.search_yts(query),
            self.search_fzmovies(query),
            self.search_toxicwap(query),
            self.search_o2tvseries(query),
            self.search_eztv(query),
        ]
        
        async def run_fast(coro):
            try:
                return await asyncio.wait_for(coro, timeout=2.5)
            except Exception:
                return []

        fast_tasks = [run_fast(t) for t in tasks]
        results_lists = await asyncio.gather(*fast_tasks, return_exceptions=True)

        merged_results = []
        seen_urls = set()

        for r_list in results_lists:
            if isinstance(r_list, list):
                for res in r_list:
                    if res["page_url"] not in seen_urls:
                        seen_urls.add(res["page_url"])
                        merged_results.append(res)

        # Subject-based relevance filtering (eliminates random posts like Mayday when searching Spider-Man)
        query_words = [w.lower().replace("-", "") for w in query.strip().split() if len(w) > 2]

        filtered_results = []
        if query_words:
            primary_word = query_words[0]  # e.g. "spiderman" or "spider"
            for res in merged_results:
                t_clean = res["title"].lower().replace("-", "").replace(":", "")
                p_clean = res["page_url"].lower().replace("-", "")

                # Must match primary word OR match multiple query words
                matches = sum(1 for w in query_words if w in t_clean or w in p_clean)
                if primary_word in t_clean or primary_word in p_clean or matches >= max(1, len(query_words) - 1):
                    res["score"] = matches + (5 if primary_word in t_clean else 0)
                    filtered_results.append(res)

        if filtered_results:
            filtered_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            return filtered_results

        if not merged_results:
            web_results = await self.search_web_indexer(query)
            if web_results:
                return web_results

        return merged_results

    async def get_download_links(self, page_url: str) -> List[Dict[str, str]]:
        html = await self._fetch(page_url)
        links = []
        if not html:
            return links

        soup = BeautifulSoup(html, "html.parser")
        a_tags = soup.find_all("a", href=True)

        for a in a_tags:
            text = a.text.strip()
            href = a["href"]

            if href.startswith("//"):
                href = "https:" + href
            elif not href.startswith("http"):
                href = urllib.parse.urljoin(page_url, href)

            href_lower = href.lower()
            text_lower = text.lower()

            if any(skip in href_lower for skip in ["how-to-download", "advertisement", "privacy", "telegram", "imdb", "requests-upload", "category", "tag", "#", "cant-download", "dmca"]):
                continue

            is_file_server = any(server in href_lower for server in [
                "loadedfiles.net", "downloadwella.com", "np-downloader.com", "dldownload.com.ng",
                "gofile.io", "mediafire.com", "mega.nz", "sdm_downloads", ".mp4", ".mkv", "associationfoam"
            ])

            if is_file_server:
                label = text if (len(text) > 3 and "download" in text_lower) else "DOWNLOAD SERVER"
                if "server 1" in text_lower or "loadedfiles" in href_lower:
                    label = "🚀 SERVER 1 (Direct HD)"
                elif "server 2" in text_lower or "downloadwella" in href_lower:
                    label = "🚀 SERVER 2 (Fast Mirror)"
                elif "np-downloader" in href_lower or "dldownload" in href_lower:
                    label = "⚡ HIGH-SPEED SERVER"
                else:
                    label = f"💾 {label}"

                links.append({"label": label, "url": href})

        if not links:
            for a in a_tags:
                text = a.text.strip()
                href = a["href"]
                if "download" in text.lower() and len(text) < 40:
                    if not any(skip in href.lower() for skip in ["how-to-download", "privacy", "telegram", "imdb"]):
                        links.append({"label": f"💾 {text}", "url": urllib.parse.urljoin(page_url, href)})

        unique_links = []
        seen_urls = set()
        for link in links:
            if link["url"] not in seen_urls:
                seen_urls.add(link["url"])
                unique_links.append(link)

        return unique_links

    async def resolve_redirect(self, url: str) -> str:
        current_url = url
        try:
            async with httpx.AsyncClient(headers=HEADERS, max_redirects=10, follow_redirects=True, timeout=20.0, verify=False) as client:
                response = await client.get(current_url)
                current_url = str(response.url)
                html = response.text

                meta_refresh = re.search(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\']\d+;\s*url=([^"\']+)["\']', html, re.IGNORECASE)
                if meta_refresh:
                    next_url = meta_refresh.group(1).strip()
                    current_url = urllib.parse.urljoin(current_url, next_url)

                js_redirect = re.search(r'window\.location\.(?:href|replace)\s*=\s*["\']([^"\']+)["\']', html)
                if js_redirect:
                    next_url = js_redirect.group(1).strip()
                    current_url = urllib.parse.urljoin(current_url, next_url)

                soup = BeautifulSoup(html, "html.parser")
                dl_a = soup.find("a", id=re.compile(r'download', re.I)) or soup.find("a", class_=re.compile(r'download', re.I))
                if dl_a and dl_a.get("href"):
                    current_url = urllib.parse.urljoin(current_url, dl_a["href"])

        except Exception as e:
            logger.error(f"Error resolving redirect for {url}: {e}")

        return current_url

scraper = MovieScraper()

@restricted
async def movie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        context.user_data['waiting_for_movie'] = True
        await update.message.reply_text("🎬 <b>What movie would you like to search for?</b>\n\nJust reply with the movie name (e.g. <code>Titanic</code>, <code>Moana</code>, <code>Spider-Man</code>)!", parse_mode="HTML")
        return

    query = " ".join(context.args)
    context.user_data.pop('waiting_for_movie', None)
    await run_movie_search(update, context, query)

async def run_movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    query = query.strip(" '\"`\t\r\n")
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "movie_search", query)

    msg = await update.message.reply_text(
        f"🔍 <b>Searching 14+ portals & global databases for '{query}'...</b>\n"
        f"<i>Scanning Nkiri, 9jarocks, FzMovies, 1337x, NetNaija...</i>",
        parse_mode="HTML"
    )

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    results = await scraper.search_all(query)

    if not results:
        await msg.edit_text(f"❌ No movies found for '<b>{query}</b>'. Try another title like <code>Avatar</code> or <code>Spiderman</code>!", parse_mode="HTML")
        return

    context.user_data['movie_results'] = results

    first_movie = results[0]
    text = (
        f"🎬 <b>{first_movie['title']}</b>\n"
        f"📅 Year: {first_movie.get('year', 'N/A')}\n"
        f"🔗 Source: {first_movie['source']}\n\n"
        f"<i>Select movie or click below to extract download servers:</i>"
    )
    keyboard = movie_results_keyboard(results)

    try:
        if first_movie.get('poster_url'):
            try:
                await update.message.reply_photo(
                    photo=first_movie['poster_url'],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                await msg.delete()
                return
            except Exception as img_err:
                logger.warning(f"Could not send poster photo for {first_movie['title']}: {img_err}")

        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error sending movie results: {e}")
        try:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            pass

async def movie_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("movie_page:"):
        index = int(data.split(":")[1])
        results = context.user_data.get('movie_results', [])
        if not results or index >= len(results) or index < 0:
            return

        movie = results[index]
        text = f"🎬 <b>{movie['title']}</b>\n📅 Year: {movie.get('year', 'N/A')}\n🔗 Source: {movie['source']}"
        keyboard = movie_results_keyboard(results)

        try:
            if query.message.photo and movie.get('poster_url'):
                await query.edit_message_media(
                    media=InputMediaPhoto(media=movie['poster_url'], caption=text, parse_mode="HTML"),
                    reply_markup=keyboard
                )
            else:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error updating movie page: {e}")

    elif data.startswith("movie_select:"):
        index = int(data.split(":")[1])
        results = context.user_data.get('movie_results', [])
        if not results or index >= len(results):
            return

        movie = results[index]

        status_text = f"⚡ <b>Extracting HD download servers for '{movie['title']}'...</b>\n<i>Connecting to high-speed file mirrors...</i>"
        if query.message.photo:
            await query.edit_message_caption(caption=status_text, parse_mode="HTML")
        else:
            await query.edit_message_text(status_text, parse_mode="HTML")

        links = await scraper.get_download_links(movie['page_url'])
        context.user_data['movie_links'] = links

        if not links:
            text = f"🎬 <b>{movie['title']}</b>\n\nDirect download page: <a href='{movie['page_url']}'>Click here to open page</a>"
            if query.message.photo:
                await query.edit_message_caption(caption=text, parse_mode="HTML", disable_web_page_preview=False)
            else:
                await query.edit_message_text(text, parse_mode="HTML", disable_web_page_preview=False)
            return

        text = f"🎬 <b>{movie['title']}</b>\n\nSelect a download server below:"
        keyboard = movie_download_keyboard(str(index), links)

        if query.message.photo:
            await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

async def movie_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Bypassing redirects...")

    data = query.data
    parts = data.split(":")
    if len(parts) >= 3 and parts[2] == "cancel":
        if query.message.photo:
            await query.edit_message_caption(caption="❌ Movie selection cancelled.")
        else:
            await query.edit_message_text("❌ Movie selection cancelled.")
        return

    try:
        index = int(parts[2]) if len(parts) >= 3 else 0
    except ValueError:
        index = 0

    links = context.user_data.get('movie_links', [])

    if not links or index >= len(links):
        await query.answer("Download link expired. Please search again.", show_alert=True)
        return

    selected_link = links[index]
    original_url = selected_link['url']

    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🔗 Resolving direct download link..."
    )

    direct_url = await scraper.resolve_redirect(original_url)

    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "movie_download", selected_link['label'])

    # Check if direct link is a small video file (<50MB) for direct in-Telegram streaming
    sent_in_telegram = False
    if direct_url.lower().endswith(('.mp4', '.mkv', '.avi')) or 'sdm_downloads' in direct_url.lower():
        try:
            await status_msg.edit_text("⚡ <b>Downloading video directly to Telegram chat...</b>", parse_mode="HTML")
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as http_c:
                head_resp = await http_c.head(direct_url)
                content_len = int(head_resp.headers.get("content-length", 0))
                if 0 < content_len < 52428800:  # < 50MB
                    import os
                    from modules.media_downloader import download_direct_file, cleanup_file
                    file_path = await download_direct_file(direct_url)
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as vid:
                            await update.effective_chat.send_video(
                                video=vid,
                                caption=f"🎬 <b>{selected_link['label']}</b>\n\n<i>Fetched by Damisile AI</i>",
                                parse_mode="HTML"
                            )
                        cleanup_file(file_path)
                        await status_msg.delete()
                        sent_in_telegram = True
        except Exception as stream_e:
            logger.warning(f"Direct Telegram video stream upload skipped: {stream_e}")

    if not sent_in_telegram:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ Direct HD Download / Stream", url=direct_url)],
            [InlineKeyboardButton("🔗 High-Speed Mirror", url=original_url)]
        ])

        await status_msg.edit_text(
            text=f"🎬 <b>{selected_link['label']}</b>\n\n"
                 f"✅ <b>Direct HD Link Resolved!</b>\n\n"
                 f"Click below to download or stream directly:\n<code>{direct_url}</code>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    log_download(direct_url, selected_link['label'], "movie")
