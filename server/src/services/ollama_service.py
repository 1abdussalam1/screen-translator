import logging
from typing import Tuple, List
import httpx
from .. import config

logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = (
    "You are a TEXT TRANSLATOR. Your ONLY function is to translate text.\n"
    "Source language: {source_lang} → Target language: {target_lang}\n\n"
    "CRITICAL:\n"
    "- You receive PLAIN TEXT ONLY. You cannot and do not see any image.\n"
    "- Do NOT describe, mention, or react to any visual content. There are no visuals.\n"
    "- Do NOT say anything about images, graphics, screenshots, or what something looks like.\n"
    "- If the input has no real words to translate, output exactly: NO_TEXT\n\n"
    "TRANSLATION RULES:\n"
    "- Output ONLY in {target_lang}. No other language allowed.\n"
    "- Translate MEANING and CONTEXT, not word-for-word. Use natural fluent {target_lang}.\n"
    "- Use proper gaming vocabulary (items, skills, quests, lore, UI, dialogue).\n"
    "- Keep character names and place names unchanged.\n"
    "- SKIP: separator lines (----, ====), lone numbers, HP/MP values, UI decorations.\n"
    "- Output ONLY the translation. No explanations, no comments.\n\n"
    "Text:\n{text}"
)

_DETECT_TRANSLATE_PROMPT = (
    "You are a TEXT TRANSLATOR. Your ONLY function is to translate text.\n"
    "Target language: {target_lang}\n\n"
    "CRITICAL:\n"
    "- You receive PLAIN TEXT ONLY. You cannot and do not see any image.\n"
    "- Do NOT describe, mention, or react to any visual content. There are no visuals.\n"
    "- Do NOT say anything about images, graphics, screenshots, or what something looks like.\n"
    "- If the input has no real words to translate, output exactly: NO_TEXT\n\n"
    "TRANSLATION RULES:\n"
    "- Output ONLY in {target_lang}. No other language allowed.\n"
    "- First detect the source language, then translate MEANING and CONTEXT, not word-for-word.\n"
    "- Use natural fluent {target_lang} with proper gaming vocabulary.\n"
    "- Keep character names and place names unchanged.\n"
    "- SKIP: separator lines (----, ====), lone numbers, HP/MP values, UI decorations.\n"
    "- Output ONLY the translation. No explanations, no comments.\n\n"
    "Text:\n{text}"
)


def _build_prompt(text: str, source_lang: str, target_lang: str) -> str:
    if source_lang == "auto":
        return _DETECT_TRANSLATE_PROMPT.format(target_lang=target_lang, text=text)
    return _TRANSLATE_PROMPT.format(source_lang=source_lang, target_lang=target_lang, text=text)


class OllamaService:
    """Translation service supporting Ollama and OpenRouter backends."""

    def __init__(self):
        self.provider = config.LLM_PROVIDER  # "ollama" or "openrouter"

        # Ollama settings
        self.ollama_url = config.OLLAMA_URL.rstrip("/")
        self.ollama_model = config.OLLAMA_MODEL

        # OpenRouter settings
        self.openrouter_url = config.OPENROUTER_BASE_URL.rstrip("/")
        self.openrouter_key = config.OPENROUTER_API_KEY
        self.openrouter_model = config.OPENROUTER_MODEL

        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def model(self) -> str:
        if self.provider == "openrouter":
            return self.openrouter_model
        return self.ollama_model

    # ── Health ──────────────────────────────────────────────────────────
    async def check_health(self) -> bool:
        try:
            if self.provider == "openrouter":
                resp = await self._client.get(
                    f"{self.openrouter_url}/models",
                    headers={"Authorization": f"Bearer {self.openrouter_key}"},
                )
                return resp.status_code == 200
            else:
                resp = await self._client.get(f"{self.ollama_url}/api/tags")
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Health check failed (%s): %s", self.provider, exc)
            return False

    async def is_model_loaded(self) -> bool:
        try:
            if self.provider == "openrouter":
                return True  # OpenRouter always has models available
            resp = await self._client.get(f"{self.ollama_url}/api/tags")
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(self.ollama_model in m for m in models)
        except Exception:
            return False

    # ── List models ─────────────────────────────────────────────────────
    async def list_models(self) -> List[str]:
        try:
            if self.provider == "openrouter":
                resp = await self._client.get(
                    f"{self.openrouter_url}/models",
                    headers={"Authorization": f"Bearer {self.openrouter_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
            else:
                resp = await self._client.get(f"{self.ollama_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.error("Failed to list models (%s): %s", self.provider, exc)
            return []

    # ── Translate ───────────────────────────────────────────────────────
    async def translate(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "Arabic",
        model_override: str | None = None,
    ) -> Tuple[str, int, int]:
        """Returns (translation, input_tokens, output_tokens)."""
        prompt = _build_prompt(text, source_lang, target_lang)

        if self.provider == "openrouter":
            return await self._translate_openrouter(prompt, model_override)
        return await self._translate_ollama(prompt, model_override)

    async def _translate_ollama(self, prompt: str, model_override: str | None = None) -> Tuple[str, int, int]:
        model = model_override or self.ollama_model
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        }
        try:
            resp = await self._client.post(f"{self.ollama_url}/api/generate", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Cannot connect to Ollama at {self.ollama_url}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Ollama error: {exc.response.text}") from exc

        data = resp.json()
        response_text = data.get("response", "").strip()
        if response_text == "NO_TEXT":
            response_text = ""
        return (
            response_text,
            data.get("prompt_eval_count", 0),
            data.get("eval_count", 0),
        )

    async def _translate_openrouter(self, prompt: str, model_override: str | None = None) -> Tuple[str, int, int]:
        model = model_override or self.openrouter_model
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = await self._client.post(
                f"{self.openrouter_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError("Cannot connect to OpenRouter") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"OpenRouter error: {exc.response.text}") from exc

        data = resp.json()
        choices = data.get("choices", [])
        translation = choices[0]["message"]["content"].strip() if choices else ""
        usage = data.get("usage", {})
        return (
            translation,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )

    async def close(self):
        await self._client.aclose()


# Singleton instance
ollama_service = OllamaService()
