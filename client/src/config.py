import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

APP_VERSION = '1.2.8'
APP_NAME = 'Screen Translator'

CONFIG_DIR = Path(os.environ.get('APPDATA', '~')) / 'ScreenTranslator'
CONFIG_FILE = CONFIG_DIR / 'config.json'
CACHE_DB = CONFIG_DIR / 'cache.db'

DEFAULT_CONFIG = {
    'provider': 'server',
    'server_url': 'https://translate.example.com',
    'api_key': '',
    'openrouter': {
        'api_key': '',
        'model': 'google/gemma-3-1b-it:free',
    },
    'source_language': 'auto',
    'target_language': 'ar',
    'capture_interval_seconds': 2,
    'ocr_engine': 'auto',
    'appearance': {
        'capture_border_color': '#00FF00',
        'capture_border_width': 2,
        'translation_bg_color': '#000000',
        'translation_bg_opacity': 0.8,
        'translation_text_color': '#FFFFFF',
        'translation_font_family': 'Arial',
        'translation_font_size': 16,
        'translation_text_alignment': 'center',
        'toggle_button_color': '#333333',
        'toggle_button_opacity': 0.7,
        'toggle_button_size': 32,
    },
    'capture_region': {
        'x': 100,
        'y': 100,
        'width': 400,
        'height': 200
    },
    'cache': {
        'enabled': True,
        'max_entries': 10000
    }
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """Load config from JSON file, merging with defaults."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            return _deep_merge(DEFAULT_CONFIG, user_config)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load config: {e}. Using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config dict to JSON file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to save config: {e}")
