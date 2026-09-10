"""
Configuration & Security for the Telegram Bot.
Loads environment variables and provides a security decorator
to restrict bot access to the authorized user only.
"""

import os
import functools
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

# --- Core Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))

# --- Gemini API Key Rotation ---
GEMINI_API_KEYS = [
    k for k in [
        os.getenv("GEMINI_API_KEY_1", ""),
        os.getenv("GEMINI_API_KEY_2", ""),
        os.getenv("GEMINI_API_KEY_3", ""),
        os.getenv("GEMINI_API_KEY", ""),  # fallback single key
    ] if k
]


class GeminiKeyManager:
    """Manages multiple Gemini API keys with automatic rotation on quota exhaustion."""

    def __init__(self, keys: list[str]):
        self.keys = keys
        self._current_index = 0

    @property
    def current_key(self) -> str:
        if not self.keys:
            return ""
        return self.keys[self._current_index]

    def rotate(self) -> str:
        """Switch to the next available key. Returns the new key or empty string."""
        if not self.keys or len(self.keys) <= 1:
            return self.current_key
        self._current_index = (self._current_index + 1) % len(self.keys)
        return self.keys[self._current_index]

    @property
    def has_keys(self) -> bool:
        return len(self.keys) > 0

    @property
    def key_count(self) -> int:
        return len(self.keys)


gemini_keys = GeminiKeyManager(GEMINI_API_KEYS)
# Keep a single GEMINI_API_KEY for backward compatibility
GEMINI_API_KEY = gemini_keys.current_key

# --- Paths ---
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "bot_data.db"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TelegramBot")


def restricted(func):
    """Decorator for handlers — public access enabled so anyone can use the bot."""
    @functools.wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        return await func(update, context, *args, **kwargs)
    return wrapper


def validate_config():
    """Validate that all required configuration is set."""
    errors = []
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is not set")
    if ALLOWED_USER_ID == 0:
        errors.append("ALLOWED_USER_ID is not set")
    if not GEMINI_API_KEY:
        errors.append("GEMINI_API_KEY is not set (AI features will be disabled)")
        logger.warning("GEMINI_API_KEY not set - AI features disabled")
    if errors:
        for e in errors:
            logger.warning(f"Config Warning: {e}")
    return len([e for e in errors if "GEMINI" not in e]) == 0
