from __future__ import annotations

from dataclasses import dataclass, field

from deep_translator import GoogleTranslator


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
    _translator_cache: dict[str, GoogleTranslator] = field(default_factory=dict)
    _text_cache: dict[tuple[str, str], str] = field(default_factory=dict)

    def set_language(self, language: str) -> tuple[bool, str]:
        target = language.strip().lower()
        if not target:
            return False, "Language code is required."

        if target == self.language:
            return True, f"Language already set to: {self.language}"

        if target == "en":
            self.language = "en"
            return True, "Display language set to: en"

        try:
            translated = self._translate_text("Display language set successfully.", target)
            if not translated:
                raise ValueError("Empty translation response.")
        except Exception as exc:
            return False, f"Unsupported language or translation error: {exc}"

        self.language = target
        return True, f"Display language set to: {target}"

    def tr(self, text: str) -> str:
        if not text or self.language == "en":
            return text
        key = (self.language, text)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached

        try:
            translated = self._translate_text(text, self.language)
        except Exception:
            translated = text
        self._text_cache[key] = translated
        return translated

    def _translate_text(self, text: str, target: str) -> str:
        translator = self._translator_cache.get(target)
        if translator is None:
            translator = GoogleTranslator(source="auto", target=target)
            self._translator_cache[target] = translator
        return str(translator.translate(text))
