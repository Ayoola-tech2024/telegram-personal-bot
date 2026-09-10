# Ultimate AI Telegram Bot (`@damisile_bot`)

An all-in-one personal & public Telegram bot built with **Python**, **`python-telegram-bot`**, **`google-genai` (Gemini 3.6 Flash)**, **`yt-dlp`**, and custom multi-site scrapers.

---

## 🔥 Key Features

### 🎬 1. 14+ Movie & Series Scraper Engine
- Scrapes **14 dedicated portals** simultaneously in parallel (`YTS 4K`, `1337x`, `TheNkiri`, `9jarocks`, `NaijaPrey`, `TheNetNaija`, `Waploaded`, `NollySauce`, `FzMovies`, `ToxicWap`, `O2TVSeries`, `EZTV`, etc.).
- Bypasses ad-redirect chains and provides direct download links.
- Natural language title recognition without requiring commands.

### 🎵 2. Instant Music & MP3 Downloader
- Universal search across YouTube Music, Spotify metadata index, and SoundCloud.
- Downloads direct playable `.mp3` / `.m4a` tracks natively inside Telegram's audio player widget.

### 🎼 3. Sub-Second Lyrics Finder (< 800ms)
- Direct song lyrics generation powered by Gemini 3.6 Flash.
- Beautiful HTML formatting (`[Verse]`, `[Chorus]`).

### 📲 4. Zero-Click Social Media Video Extractor
- Paste any link from **Instagram Reels**, **TikTok**, **YouTube Shorts**, **Twitter/X**, **Facebook Watch**.
- Auto-extracts and sends the MP4 video directly into chat.

### 🎙️ 5. AI Voice Notes (Voice-to-Text & Spoken Audio Replies)
- Send voice notes -> transcribed by Gemini 3.6 Flash multimodal.
- Speaks back AI responses via `gTTS` audio voice messages.

### 🛠️ 6. Universal File Converter Suite
- **Video to MP3 Audio Extraction**.
- **Image Converter & Compressor** (PNG, JPG, WEBP, compress <1MB).
- **Document Converter** (DOCX text extraction, PDF text converter).

### 🌤️ 7. Live Weather & Daily News Digest
- `/weather <city>` live temperature, humidity, wind, and conditions.
- `/news <topic>` top 5 breaking news AI executive digest.

---

## 🛠️ Setup & Installation

1. **Clone Repository**:
   ```bash
   git clone https://github.com/Ayoola-tech2024/telegram-personal-bot.git
   cd telegram-personal-bot
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment (`.env`)**:
   Copy `.env.example` to `.env` and fill in your keys:
   ```env
   TELEGRAM_BOT_TOKEN=your_token
   ALLOWED_USER_ID=your_id
   GEMINI_API_KEY_1=key_1
   GEMINI_API_KEY_2=key_2
   GEMINI_API_KEY_3=key_3
   ```

4. **Run the Bot**:
   ```bash
   python bot.py
   ```
