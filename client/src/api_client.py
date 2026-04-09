import logging
import tempfile
import os
from typing import Optional, Callable, Any

import httpx

logger = logging.getLogger(__name__)


def _compare_versions(v1: str, v2: str) -> int:
    """Compare version strings. Returns -1, 0, or 1."""
    def parse(v):
        return tuple(int(x) for x in v.strip().split('.'))
    t1, t2 = parse(v1), parse(v2)
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0


_DETECT_TRANSLATE_PROMPT = (
    "You are a TEXT TRANSLATOR. Your ONLY function is to translate text.\n"
    "Target language: {target_lang}\n\n"
    "CRITICAL:\n"
    "- You receive PLAIN TEXT ONLY. You cannot and do not see any image.\n"
    "- Do NOT describe, mention, or react to any visual content. There are no visuals.\n"
    "- If the input has no real words to translate, output exactly: NO_TEXT\n\n"
    "TRANSLATION RULES:\n"
    "- Output ONLY in {target_lang}. No other language allowed.\n"
    "- First detect the source language, then translate MEANING and CONTEXT, not word-for-word.\n"
    "- Use natural fluent {target_lang} with proper gaming vocabulary.\n"
    "- Keep character names and place names unchanged.\n"
    "- SKIP: separator lines, lone numbers, HP/MP values, UI decorations.\n"
    "- Output ONLY the translation. No explanations, no comments.\n\n"
    "Text:\n{text}"
)

_TRANSLATE_PROMPT = (
    "You are a TEXT TRANSLATOR. Your ONLY function is to translate text.\n"
    "Source: {source_lang} → Target: {target_lang}\n\n"
    "CRITICAL:\n"
    "- You receive PLAIN TEXT ONLY. You cannot and do not see any image.\n"
    "- Do NOT describe, mention, or react to any visual content. There are no visuals.\n"
    "- If the input has no real words to translate, output exactly: NO_TEXT\n\n"
    "TRANSLATION RULES:\n"
    "- Output ONLY in {target_lang}. No other language allowed.\n"
    "- Translate MEANING and CONTEXT, not word-for-word. Use natural fluent {target_lang}.\n"
    "- Use proper gaming vocabulary (items, skills, quests, lore, UI, dialogue).\n"
    "- Keep character names and place names unchanged.\n"
    "- SKIP: separator lines, lone numbers, HP/MP values, UI decorations.\n"
    "- Output ONLY the translation. No explanations, no comments.\n\n"
    "Text:\n{text}"
)


class APIClient:
    """Async HTTP client supporting both server and OpenRouter backends."""

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.provider = 'server'  # 'server' or 'openrouter'
        self.ollama_model = ''  # server model override
        self.openrouter_key = ''
        self.openrouter_model = 'google/gemma-3-1b-it:free'
        self._timeout = httpx.Timeout(30.0)

    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key.strip()
        return headers

    async def translate(self, text: str, source_lang: str, target_lang: str) -> dict:
        if self.provider == 'openrouter':
            return await self._translate_openrouter(text, source_lang, target_lang)
        return await self._translate_server(text, source_lang, target_lang)

    async def _translate_server(self, text: str, source_lang: str, target_lang: str) -> dict:
        """POST /api/v1/translate via our server."""
        url = f"{self.server_url}/api/v1/translate"
        payload = {
            'text': text,
            'source_language': source_lang,
            'target_language': target_lang,
        }
        if self.ollama_model:
            payload['model'] = self.ollama_model
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise PermissionError("مفتاح API غير صالح أو مفقود")
                elif response.status_code == 429:
                    raise ConnectionAbortedError("تم تجاوز حد الطلبات، حاول لاحقاً")
                else:
                    raise RuntimeError(f"خطأ في الخادم: {response.status_code}")
        except httpx.ConnectError:
            raise ConnectionError("تعذّر الاتصال بالخادم")
        except httpx.TimeoutException:
            raise TimeoutError("انتهت مهلة الاتصال بالخادم")

    async def _translate_openrouter(self, text: str, source_lang: str, target_lang: str) -> dict:
        """Translate directly via OpenRouter API."""
        if source_lang == 'auto':
            prompt = _DETECT_TRANSLATE_PROMPT.format(target_lang=target_lang, text=text)
        else:
            prompt = _TRANSLATE_PROMPT.format(source_lang=source_lang, target_lang=target_lang, text=text)

        payload = {
            'model': self.openrouter_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
        }
        headers = {
            'Authorization': f'Bearer {self.openrouter_key}',
            'Content-Type': 'application/json',
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    'https://openrouter.ai/api/v1/chat/completions',
                    json=payload,
                    headers=headers,
                )
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get('choices', [])
                    translation = choices[0]['message']['content'].strip() if choices else ''
                    usage = data.get('usage', {})
                    return {
                        'translation': translation,
                        'source_language_detected': source_lang,
                        'tokens_used': usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0),
                        'processing_time_ms': 0,
                    }
                elif response.status_code == 401:
                    raise PermissionError("مفتاح OpenRouter غير صالح")
                elif response.status_code == 429:
                    raise ConnectionAbortedError("تم تجاوز حد الطلبات")
                else:
                    raise RuntimeError(f"خطأ OpenRouter: {response.status_code}")
        except httpx.ConnectError:
            raise ConnectionError("تعذّر الاتصال بـ OpenRouter")
        except httpx.TimeoutException:
            raise TimeoutError("انتهت مهلة الاتصال بـ OpenRouter")

    async def validate_key(self) -> dict:
        """POST /api/v1/auth/validate — validates the API key."""
        url = f"{self.server_url}/api/v1/auth/validate"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    return {'valid': False, 'message': 'مفتاح API غير صالح'}
                else:
                    return {'valid': False, 'message': f'خطأ: {response.status_code}'}
        except httpx.ConnectError:
            return {'valid': False, 'message': 'تعذّر الاتصال بالخادم'}
        except httpx.TimeoutException:
            return {'valid': False, 'message': 'انتهت مهلة الاتصال'}
        except Exception as e:
            return {'valid': False, 'message': str(e)}

    async def health_check(self) -> dict:
        """GET /api/v1/health — checks server health."""
        url = f"{self.server_url}/api/v1/health"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    return response.json()
                return {'status': 'error', 'code': response.status_code}
        except httpx.ConnectError:
            return {'status': 'unreachable', 'message': 'تعذّر الاتصال بالخادم'}
        except httpx.TimeoutException:
            return {'status': 'timeout', 'message': 'انتهت مهلة الاتصال'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def check_update(self, current_version: str) -> Optional[dict]:
        """
        GET /updates/latest — checks for a newer version.
        Returns update info dict if a newer version exists, else None.
        Expected response: {'version': '1.2.0', 'download_url': '...', 'release_notes': '...'}
        """
        url = f"{self.server_url}/updates/latest"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=self._headers())
                if response.status_code == 200:
                    data = response.json()
                    remote_version = data.get('version', '0.0.0')
                    if _compare_versions(current_version, remote_version) < 0:
                        return data
                    return None
                return None
        except Exception as e:
            logger.warning(f"Update check failed: {e}")
            return None

    async def download_update(
        self,
        download_url: str,
        progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> str:
        """
        Download the update installer to a temp file.
        progress_callback(downloaded_bytes, total_bytes) is called periodically.
        Returns the path to the downloaded file.
        """
        suffix = '.exe'
        if download_url.endswith('.msi'):
            suffix = '.msi'
        elif download_url.endswith('.zip'):
            suffix = '.zip'

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix='screen_translator_update_')
        os.close(tmp_fd)

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                async with client.stream('GET', download_url) as response:
                    response.raise_for_status()
                    total = int(response.headers.get('Content-Length', 0))
                    downloaded = 0
                    with open(tmp_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total)
        except Exception as e:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise RuntimeError(f"فشل تنزيل التحديث: {e}")

        return tmp_path
