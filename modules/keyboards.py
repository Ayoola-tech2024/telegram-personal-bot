"""
Telegram Inline Keyboard builders for interactive quality selection,
movie results, and search navigation.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def quality_keyboard(video_id: str, formats: list[dict]) -> InlineKeyboardMarkup:
    """
    Build a quality selection keyboard from available formats.

    Args:
        video_id: Unique identifier for this download session.
        formats: List of dicts with 'format_id', 'label', 'filesize' keys.
    """
    buttons = []
    for fmt in formats:
        size_str = ""
        if fmt.get("filesize"):
            size_mb = fmt["filesize"] / (1024 * 1024)
            size_str = f" ({size_mb:.0f}MB)"

        buttons.append([
            InlineKeyboardButton(
                text=f"{fmt['label']}{size_str}",
                callback_data=f"dl:{video_id}:{fmt['format_id']}",
            )
        ])

    # Add audio-only option
    buttons.append([
        InlineKeyboardButton(
            text="🎵 Audio Only (MP3)",
            callback_data=f"dl:{video_id}:audio",
        )
    ])

    # Add cancel button
    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"dl:{video_id}:cancel")
    ])

    return InlineKeyboardMarkup(buttons)


def movie_results_keyboard(movies: list[dict]) -> InlineKeyboardMarkup:
    """
    Build a keyboard for movie search results.

    Args:
        movies: List of dicts with 'id', 'title', 'year', 'quality' keys.
    """
    buttons = []
    for i, movie in enumerate(movies[:10]):  # Limit to 10 results
        label = movie.get("title", "Unknown")
        year = movie.get("year", "")
        quality = movie.get("quality", "")
        display = f"🎬 {label}"
        if year:
            display += f" ({year})"

        buttons.append([
            InlineKeyboardButton(
                text=display,
                callback_data=f"movie_select:{i}",
            )
        ])

    return InlineKeyboardMarkup(buttons)


def movie_download_keyboard(movie_id: str, links: list[dict]) -> InlineKeyboardMarkup:
    """
    Build download buttons for a movie with multiple quality/episode links.

    Args:
        movie_id: Unique movie identifier.
        links: List of dicts with 'label', 'url' keys.
    """
    buttons = []
    for i, link in enumerate(links[:15]):  # Limit to 15 links
        buttons.append([
            InlineKeyboardButton(
                text=f"💾 {link['label']}",
                callback_data=f"moviedl:{movie_id}:{i}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"moviedl:{movie_id}:cancel")
    ])

    return InlineKeyboardMarkup(buttons)


def search_type_keyboard() -> InlineKeyboardMarkup:
    """Build a keyboard to select search type."""
    buttons = [
        [
            InlineKeyboardButton("🌐 Web", callback_data="stype:web"),
            InlineKeyboardButton("🖼️ Images", callback_data="stype:images"),
        ],
        [
            InlineKeyboardButton("🎵 Music", callback_data="stype:music"),
            InlineKeyboardButton("🎬 Movies", callback_data="stype:movies"),
        ],
        [
            InlineKeyboardButton("📄 PDF/Docs", callback_data="stype:pdf"),
            InlineKeyboardButton("📜 Lyrics", callback_data="stype:lyrics"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def confirm_download_keyboard(url: str, file_id: str = "0") -> InlineKeyboardMarkup:
    """Simple confirm/cancel keyboard for direct file downloads."""
    buttons = [
        [InlineKeyboardButton("✅ Download Now", callback_data=f"directdl:{file_id}:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"directdl:{file_id}:cancel")],
    ]
    return InlineKeyboardMarkup(buttons)


def pagination_keyboard(current_page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    """Build pagination buttons."""
    buttons = []
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}:page:{current_page - 1}"))
    row.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}:page:{current_page + 1}"))
    buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def voice_summary_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Build keyboard for voice notes to choose Spoken Reply or AI Executive Summary."""
    buttons = [
        [
            InlineKeyboardButton("🎙️ Spoken Voice Reply", callback_data=f"voice_action:speak:{session_id}"),
            InlineKeyboardButton("📝 AI Executive Summary", callback_data=f"voice_action:summary:{session_id}"),
        ]
    ]
    return InlineKeyboardMarkup(buttons)


def playlist_download_keyboard(playlist_id: str, count: int) -> InlineKeyboardMarkup:
    """Build keyboard for playlist batch download."""
    buttons = [
        [InlineKeyboardButton(f"📥 Download {count} Tracks Batch", callback_data=f"playlist_dl:{playlist_id}:all")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"playlist_dl:{playlist_id}:cancel")]
    ]
    return InlineKeyboardMarkup(buttons)
