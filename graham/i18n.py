from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


COMMON_LANGUAGE_CODES = [
    "en",
    "fr",
    "es",
    "de",
    "it",
    "pt",
    "nl",
    "pl",
    "tr",
    "ru",
    "ar",
    "hi",
    "ja",
    "ko",
    "zh-cn",
    "zh-tw",
]


@dataclass
class DisplayTranslator:
    language: str = "en"
    _translator_cache: dict[str, Any] = field(default_factory=dict)
    _text_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    _pending: set[tuple[str, str]] = field(default_factory=set)
    _lock: Lock = field(default_factory=Lock)
    _executor: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=2))
    _max_pending: int = 256

    def set_language(self, language: str) -> tuple[bool, str]:
        target = language.strip().lower()
        if not target:
            return False, "Language code is required."

        if target == self.language:
            return True, f"Language already set to: {self.language}"

        if target == "en":
            self.language = "en"
            return True, "Display language set to: en"

        self.language = target
        return True, f"Display language set to: {target}"

    def tr(self, text: str) -> str:
        if not text:
            return text
        language = self.language
        if language == "en":
            return text

        key = (language, text)
        with self._lock:
            cached = self._text_cache.get(key)
            if cached is not None:
                return cached
            if key in self._pending or len(self._pending) >= self._max_pending:
                return text
            self._pending.add(key)

        self._executor.submit(self._translate_and_store, key, text, language)
        return text

    def _translate_and_store(self, key: tuple[str, str], text: str, target: str) -> None:
        try:
            translated = self._translate_text(text, target)
            if not translated:
                translated = text
        except Exception:
            translated = text

        with self._lock:
            self._text_cache[key] = translated
            self._pending.discard(key)

    def _translate_text(self, text: str, target: str) -> str:
        translator = self._translator_cache.get(target)
        if translator is None:
            from deep_translator import GoogleTranslator

            translator = GoogleTranslator(source="auto", target=target)
            self._translator_cache[target] = translator
        return str(translator.translate(text))
