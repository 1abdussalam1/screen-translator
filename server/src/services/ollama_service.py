import logging
from typing import Tuple
import httpx
from .. import config

logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = (
    "You are a professional translator. "
    "Translate the following text to {target_lang}. "
    "Return ONLY the translation, no explanations, no notes.\n\n"
    "{text}"
)

_DETECT_TRANSLATE_PROMPT = (
    "You are a professional translator. "
    "Detect the language of the following text and translate it to {target_lang}. "
    "Return ONLY the translated text, nothing else.\n\n"
    "{text}"
)


class OllamaService:
    def __init__(self):
        self.base_url = config.OLLAMA_URL.rstrip("/")
        self.model = config.OLLAMA_MODEL
        self._client = httpx.AsyncClient(timeout=120.0)

    async def check_health(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            return resp.status_code == 200
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False

    async def is_model_loaded(self) -> bool:
        try:
            resp = await self._client.get(f"{self.base_url}/api/tags")
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(self.model in m for m in models)
        except Exception:
            return False

    async def translate(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "Arabic",
    ) -> Tuple[str, int, int]:
        """
        Returns (translation, input_tokens, output_tokens).
        """
        if source_lang == "auto":
            prompt = _DETECT_TRANSLATE_PROMPT.format(
                target_lang=target_lang, text=text
            )
        else:
            prompt = _TRANSLATE_PROMPT.format(
                target_lang=target_lang, text=text
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
            },
        }

        try:
            resp = await self._client.post(
                f"{self.base_url}/api/generate", json=payload
            )
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("Cannot connect to Ollama at %s: %s", self.base_url, exc)
            raise RuntimeError(
                f"Cannot connect to Ollama service at {self.base_url}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error: %s", exc)
            raise RuntimeError(f"Ollama returned error: {exc.response.text}") from exc

        data = resp.json()
        translation = data.get("response", "").strip()
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return translation, input_tokens, output_tokens

    async def close(self):
        await self._client.aclose()


# Singleton instance
ollama_service = OllamaService()
