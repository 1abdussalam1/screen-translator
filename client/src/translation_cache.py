import hashlib
import sqlite3
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TranslationCache:
    def __init__(self, db_path: Path, max_entries: int = 10000):
        self.db_path = db_path
        self.max_entries = max_entries
        self._conn: Optional[sqlite3.Connection] = None
        self.init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def init_db(self) -> None:
        """Create the cache table and index if they don't exist."""
        conn = self._get_conn()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS translation_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_hash TEXT NOT NULL,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                source_language TEXT NOT NULL DEFAULT 'auto',
                target_language TEXT NOT NULL DEFAULT 'ar',
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 1
            )
        ''')
        conn.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_text_hash_lang
            ON translation_cache (text_hash, target_language)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_last_used
            ON translation_cache (last_used_at)
        ''')
        conn.commit()

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def get(self, text: str, target_lang: str) -> Optional[str]:
        """Look up a translation from cache. Returns translated text or None."""
        text_hash = self._hash_text(text)
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            row = conn.execute(
                'SELECT id, translated_text FROM translation_cache WHERE text_hash = ? AND target_language = ?',
                (text_hash, target_lang)
            ).fetchone()
            if row:
                conn.execute(
                    'UPDATE translation_cache SET last_used_at = ?, use_count = use_count + 1 WHERE id = ?',
                    (now, row['id'])
                )
                conn.commit()
                return row['translated_text']
        except sqlite3.Error as e:
            logger.error(f"Cache get error: {e}")
        return None

    def put(self, text: str, translation: str, source_lang: str, target_lang: str) -> None:
        """Insert a translation into cache, or ignore if already present."""
        text_hash = self._hash_text(text)
        now = datetime.utcnow().isoformat()
        try:
            conn = self._get_conn()
            conn.execute(
                '''INSERT OR IGNORE INTO translation_cache
                   (text_hash, source_text, translated_text, source_language, target_language, created_at, last_used_at, use_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1)''',
                (text_hash, text, translation, source_lang, target_lang, now, now)
            )
            conn.commit()
            self.evict_lru()
        except sqlite3.Error as e:
            logger.error(f"Cache put error: {e}")

    def evict_lru(self) -> None:
        """If count exceeds max_entries, delete the oldest 10% by last_used_at."""
        try:
            conn = self._get_conn()
            count = conn.execute('SELECT COUNT(*) FROM translation_cache').fetchone()[0]
            if count > self.max_entries:
                evict_count = max(1, int(count * 0.1))
                conn.execute(
                    '''DELETE FROM translation_cache WHERE id IN (
                        SELECT id FROM translation_cache ORDER BY last_used_at ASC LIMIT ?
                    )''',
                    (evict_count,)
                )
                conn.commit()
                logger.info(f"Evicted {evict_count} LRU cache entries.")
        except sqlite3.Error as e:
            logger.error(f"Cache evict error: {e}")

    def clear(self) -> None:
        """Delete all cache entries."""
        try:
            conn = self._get_conn()
            conn.execute('DELETE FROM translation_cache')
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Cache clear error: {e}")

    def get_stats(self) -> dict:
        """Return cache statistics."""
        try:
            conn = self._get_conn()
            count = conn.execute('SELECT COUNT(*) FROM translation_cache').fetchone()[0]
            size_bytes = 0
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
            return {
                'count': count,
                'max_entries': self.max_entries,
                'size_bytes': size_bytes
            }
        except (sqlite3.Error, OSError) as e:
            logger.error(f"Cache stats error: {e}")
            return {'count': 0, 'max_entries': self.max_entries, 'size_bytes': 0}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
