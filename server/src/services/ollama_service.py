import logging
from typing import Tuple, List
import httpx
from .. import config

logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = (
    "You are a professional video game localizer specializing in {target_lang}.\n"
    "Source language: {source_lang}\n"
    "Target language: {target_lang}\n\n"
    "RULES:\n"
    "1. Output ONLY in {target_lang}. No other language.\n"
    "2. Input is plain text extracted via OCR from a game screenshot — no images, no visuals.\n"
    "3. Translate the MEANING and CONCEPT, not word-for-word. Use natural, fluent {target_lang}.\n"
    "   Example: 'A large-output battery that can be thrown' → convey it's a throwable power source, "
    "not a literal translation of each word.\n"
    "4. Use appropriate gaming vocabulary in {target_lang} (items, skills, quests, lore, dialogue).\n"
    "5. IGNORE: separator lines (----, ====), lone numbers, HP/MP values, UI symbols/decorations.\n"
    "6. Keep proper nouns (character names, place names) as-is.\n"
    "7. If there is NO translatable text, respond with exactly: NO_TEXT\n"
    "8. Output ONLY the translation — no explanations, no comments.\n\n"
    "Text:\n{text}"
)

_DETECT_TRANSLATE_PROMPT = (
    "You are a professional video game localizer specializing in {target_lang}.\n"
    "Target language: {target_lang}\n\n"
    "RULES:\n"
    "1. Output ONLY in {target_lang}. No other language.\n"
    "2. Input is plain text extracted via OCR from a game screenshot — no images, no visuals.\n"
    "3. First detect the source language, then translate the MEANING and CONCEPT, not word-for-word.\n"
    "   Use natural, fluent {target_lang} as a native game localizer would.\n"
    "   Example: 'A large-output battery that can be thrown' → convey it's a throwable power source, "
    "not a literal translation of each word.\n"
    "4. Use appropriate gaming vocabulary in {target_lang} (items, skills, quests, lore, dialogue).\n"
    "5. IGNORE: separator lines (----, ====), lone numbers, HP/MP values, UI symbols/decorations.\n"
    "6. Keep proper nouns (character names, place names) as-is.\n"
    "7. If there is NO translatable text, respond with exactly: NO_TEXT\n"
    "8. Output ONLY the translation — no explanations, no comments.\n\n"
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
