import logging
from typing import Tuple, List
import httpx
from .. import config

logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = (
    "You are an expert game translator. You translate text captured from video games.\n"
    "Source language: {source_lang}\n"
    "Target language: {target_lang}\n\n"
    "Context: The text comes from screen capture (OCR) of a video game. "
    "It may include dialogue, quests, item descriptions, menus, HUD elements, or cutscene subtitles.\n\n"
    "Rules:\n"
    "- Translate ONLY actual readable words and sentences.\n"
    "- Understand game context: quests, items, skills, dialogue, lore, UI labels.\n"
    "- Use natural gaming terminology in the target language.\n"
    "- Keep character names, place names, and game-specific terms as-is.\n"
    "- IGNORE completely: lines/borders (----, ====, ____), decorative symbols, "
    "HP/MP bars, damage numbers, UI frames, or any non-text visual elements.\n"
    "- If the input has no real words (only symbols, lines, numbers, or garbage), "
    "respond with exactly: NO_TEXT\n"
    "- Do NOT add explanations or notes. Output ONLY the translated text.\n\n"
    "Text to translate:\n{text}"
)

_DETECT_TRANSLATE_PROMPT = (
    "You are an expert game translator. You translate text captured from video games.\n"
    "Target language: {target_lang}\n\n"
    "Context: The text comes from screen capture (OCR) of a video game. "
    "It may include dialogue, quests, item descriptions, menus, HUD elements, or cutscene subtitles.\n\n"
    "Rules:\n"
    "- First detect the source language of the text.\n"
    "- Translate ONLY actual readable words and sentences.\n"
    "- Understand game context: quests, items, skills, dialogue, lore, UI labels.\n"
    "- Use natural gaming terminology in the target language.\n"
    "- Keep character names, place names, and game-specific terms as-is.\n"
    "- IGNORE completely: lines/borders (----, ====, ____), decorative symbols, "
    "HP/MP bars, damage numbers, UI frames, or any non-text visual elements.\n"
    "- If the input has no real words (only symbols, lines, numbers, or garbage), "
    "respond with exactly: NO_TEXT\n"
    "- Do NOT add explanations or notes. Output ONLY the translated text.\n\n"
    "Text to translate:\n{text}"
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
    ) -> Tuple[str, int, int]:
        """Returns (translation, input_tokens, output_tokens)."""
        prompt = _build_prompt(text, source_lang, target_lang)

        if self.provider == "openrouter":
            return await self._translate_openrouter(prompt)
        return await self._translate_ollama(prompt)

    async def _translate_ollama(self, prompt: str) -> Tuple[str, int, int]:
        payload = {
            "model": self.ollama_model,
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

    async def _translate_openrouter(self, prompt: str) -> Tuple[str, int, int]:
        payload = {
            "model": self.openrouter_model,
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
