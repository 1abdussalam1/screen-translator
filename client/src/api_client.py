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


class APIClient:
    """Async HTTP client for the translation server."""

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self._timeout = httpx.Timeout(30.0)

    def _headers(self) -> dict:
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key.strip()
        return headers

    async def translate(self, text: str, source_lang: str, target_lang: str) -> dict:
        """POST /api/v1/translate — returns {'translated_text': '...', 'source_language': '...'}"""
        url = f"{self.server_url}/api/v1/translate"
        payload = {
            'text': text,
            'source_language': source_lang,
            'target_language': target_lang
        }
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
