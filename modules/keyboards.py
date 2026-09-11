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


def movie_results_keyboard(movies: list[dict], page: int = 1, page_size: int = 5) -> InlineKeyboardMarkup:
    """
    Build a paginated keyboard for movie search results.

    Args:
        movies: List of dicts with 'id', 'title', 'year', 'quality', 'source' keys.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
    """
    total_items = len(movies)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_movies = movies[start_idx:end_idx]

    buttons = []
    for rel_i, movie in enumerate(page_movies):
        actual_i = start_idx + rel_i
        label = movie.get("title", "Unknown")
        year = movie.get("year", "")
        source = movie.get("source", "")
        source_tag = f" [{source}]" if source else ""
        year_tag = f" ({year})" if year else ""

        display = f"🎬 {label[:32]}{year_tag}{source_tag}"
        buttons.append([
            InlineKeyboardButton(
                text=display,
                callback_data=f"movie_select:{actual_i}",
            )
        ])

    # Pagination navigation row
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"movie_page:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton("⏹️", callback_data="noop"))

        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"movie_page:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton("⏹️", callback_data="noop"))
        buttons.append(nav_row)

    # Action row: Trigger another search / Deep Search
    buttons.append([
        InlineKeyboardButton("🔍 Search More Sites & Portals", callback_data=f"movie_deep:{page}")
    ])

    return InlineKeyboardMarkup(buttons)


def song_results_keyboard(session_id: str, options: list[dict], page: int = 1, page_size: int = 5) -> InlineKeyboardMarkup:
    """
    Build a paginated keyboard for song search results.

    Args:
        session_id: Unique session ID for this song query.
        options: List of track dicts with 'title', 'uploader', 'duration', 'url'.
        page: Current page (1-indexed).
        page_size: Number of tracks per page.
    """
    total_items = len(options)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_options = options[start_idx:end_idx]

    buttons = []
    for rel_i, opt in enumerate(page_options):
        actual_i = start_idx + rel_i
        title = opt.get('title', 'Unknown Track')
        label = f"🎵 {actual_i + 1}. {title[:36]}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"songselect:{session_id}:{actual_i}")
        ])

    # Pagination navigation row
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"songpage:{session_id}:{page - 1}"))
        else:
            nav_row.append(InlineKeyboardButton("⏹️", callback_data="noop"))

        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))

        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"songpage:{session_id}:{page + 1}"))
        else:
            nav_row.append(InlineKeyboardButton("⏹️", callback_data="noop"))
        buttons.append(nav_row)

    # Action row: Deep search for more tracks/mirrors
    buttons.append([
        InlineKeyboardButton("🔍 Search More Tracks & Audio Mirrors", callback_data=f"songdeep:{session_id}")
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


def confirm_download_keyboard(session_id: str) -> InlineKeyboardMarkup:
    """Simple confirm/cancel keyboard for direct file downloads."""
    buttons = [
        [InlineKeyboardButton("✅ Download Now", callback_data=f"directdl:{session_id}:confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"directdl:{session_id}:cancel")],
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
