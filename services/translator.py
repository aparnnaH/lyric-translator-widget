import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from langdetect import DetectorFactory, LangDetectException, detect_langs
from lingua import Language, LanguageDetectorBuilder
import requests
from requests import RequestException


DEEPL_API_URL = "https://api-free.deepl.com/v2/translate"
MYMEMORY_API_URL = "https://api.mymemory.translated.net/get"
DetectorFactory.seed = 0

HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
CJK_SEGMENT_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\u3040-\u30ff]+"
    r"(?:\s+[\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\u3040-\u30ff]+)*"
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LETTER_OR_NUMBER_RE = re.compile(
    r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\u3040-\u30ff]"
)
SECTION_HEADER_RE = re.compile(r"^\[.+\]$")
VOCAL_TOKEN_RE = re.compile(r"[A-Za-z]+")
VOCAL_TOKENS = {
    "ah",
    "ay",
    "eh",
    "ey",
    "ha",
    "hey",
    "la",
    "na",
    "o",
    "oh",
    "oo",
    "ooh",
    "uh",
    "woah",
    "whoa",
    "woo",
    "yeah",
    "yea",
    "yo",
}
ROMANIZED_KOREAN_TOKENS = {
    "annyeong",
    "bangtan",
    "bultaoreune",
    "daebak",
    "eomma",
    "hyung",
    "jjeoreo",
    "mianhae",
    "naneun",
    "sarang",
}
LANGUAGE_NAMES = {
    "en": "English",
    "ko": "Korean",
    "ja": "Japanese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "zh": "Chinese",
    "und": "Unknown",
    "mixed": "Mixed",
}
LINGUA_LANGUAGES = [
    Language.CHINESE,
    Language.ENGLISH,
    Language.FRENCH,
    Language.GERMAN,
    Language.ITALIAN,
    Language.JAPANESE,
    Language.KOREAN,
    Language.PORTUGUESE,
    Language.SPANISH,
]
LINGUA_CODES = {
    Language.CHINESE: "zh",
    Language.ENGLISH: "en",
    Language.FRENCH: "fr",
    Language.GERMAN: "de",
    Language.ITALIAN: "it",
    Language.JAPANESE: "ja",
    Language.KOREAN: "ko",
    Language.PORTUGUESE: "pt",
    Language.SPANISH: "es",
}


class TranslationError(Exception):
    pass


class TranslationCache:
    def __init__(self, path):
        self.path = Path(path)
        self._ensure_schema()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS song_translations (
                    cache_key TEXT PRIMARY KEY,
                    track_id TEXT,
                    artist TEXT,
                    title TEXT,
                    lyrics_hash TEXT NOT NULL,
                    detected_source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    translation_status TEXT NOT NULL,
                    language_detection_confidence REAL NOT NULL,
                    provider TEXT,
                    translated_lines_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recent_songs (
                    track_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album_art TEXT,
                    source_url TEXT,
                    playback_source TEXT,
                    translation_status TEXT,
                    translation_label TEXT,
                    target_language TEXT,
                    lyrics_source TEXT,
                    play_count INTEGER NOT NULL DEFAULT 1,
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def get(self, cache_key):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    detected_source_language,
                    target_language,
                    translation_status,
                    language_detection_confidence,
                    provider,
                    translated_lines_json,
                    metadata_json
                FROM song_translations
                WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()

        if not row:
            return None

        return {
            "detected_source_language": row[0],
            "target_language": row[1],
            "translation_status": row[2],
            "language_detection_confidence": row[3],
            "provider": row[4],
            "lines": json.loads(row[5]),
            "metadata": json.loads(row[6]),
        }

    def set(self, cache_key, track, lyrics_hash, result):
        now = int(time.time())
        metadata = {
            "translation_label": result["translation_label"],
            "line_languages": result["line_languages"],
            "reused_repeated_lines": result.get("reused_repeated_lines", False),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO song_translations (
                    cache_key,
                    track_id,
                    artist,
                    title,
                    lyrics_hash,
                    detected_source_language,
                    target_language,
                    translation_status,
                    language_detection_confidence,
                    provider,
                    translated_lines_json,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    detected_source_language = excluded.detected_source_language,
                    target_language = excluded.target_language,
                    translation_status = excluded.translation_status,
                    language_detection_confidence = excluded.language_detection_confidence,
                    provider = excluded.provider,
                    translated_lines_json = excluded.translated_lines_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    cache_key,
                    track.get("id", ""),
                    track.get("artist", ""),
                    track.get("title", ""),
                    lyrics_hash,
                    result["detected_source_language"],
                    result["target_language"],
                    result["translation_status"],
                    result["language_detection_confidence"],
                    result.get("provider"),
                    json.dumps(result["lines"], ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def delete_for_track(self, track, target_language=None):
        """Remove cached translations for one track, optionally limited to a target language."""
        track_id = track.get("id", "")
        artist = track.get("artist", "")
        title = track.get("title", "")
        target = (target_language or "").lower()

        clauses = []
        params = []
        if track_id:
            clauses.append("track_id = ?")
            params.append(track_id)
        if artist and title:
            clauses.append("(artist = ? AND title = ?)")
            params.extend([artist, title])
        if not clauses:
            return 0

        where = f"({' OR '.join(clauses)})"
        if target:
            where = f"{where} AND lower(target_language) = ?"
            params.append(target)

        with self._connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM song_translations WHERE {where}",
                tuple(params),
            )
            return cursor.rowcount

    def add_recent_song(self, track, result, lyrics_source):
        track_id = track.get("id", "")
        if not track_id.startswith("spotify:track:") or track.get("is_ad"):
            return

        now = int(time.time())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO recent_songs (
                    track_id,
                    title,
                    artist,
                    album_art,
                    source_url,
                    playback_source,
                    translation_status,
                    translation_label,
                    target_language,
                    lyrics_source,
                    play_count,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album_art = excluded.album_art,
                    source_url = excluded.source_url,
                    playback_source = excluded.playback_source,
                    translation_status = excluded.translation_status,
                    translation_label = excluded.translation_label,
                    target_language = excluded.target_language,
                    lyrics_source = excluded.lyrics_source,
                    play_count = recent_songs.play_count + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    track_id,
                    track.get("title", ""),
                    track.get("artist", ""),
                    track.get("album_art", ""),
                    track.get("source_url", ""),
                    track.get("playback_source", ""),
                    result.get("translation_status", ""),
                    result.get("translation_label", ""),
                    result.get("target_language", ""),
                    lyrics_source,
                    now,
                ),
            )

    def get_recent_songs(self, limit=8):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    track_id,
                    title,
                    artist,
                    album_art,
                    source_url,
                    playback_source,
                    translation_status,
                    translation_label,
                    target_language,
                    lyrics_source,
                    play_count,
                    updated_at
                FROM recent_songs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "id": row[0],
                "title": row[1],
                "artist": row[2],
                "album_art": row[3],
                "source_url": row[4],
                "playback_source": row[5],
                "translation_status": row[6],
                "translation_label": row[7],
                "target_language": row[8],
                "lyrics_source": row[9],
                "play_count": row[10],
                "updated_at": row[11],
            }
            for row in rows
        ]


class TranslatorClient:
    def __init__(self):
        self.provider = os.getenv("TRANSLATION_PROVIDER", "mymemory").lower()
        self.source_lang = os.getenv("TRANSLATION_SOURCE_LANG", "auto")
        self.deepl_api_key = os.getenv("DEEPL_API_KEY", "").strip()
        self.deepl_api_url = os.getenv("DEEPL_API_URL", DEEPL_API_URL)
        self.mymemory_api_url = os.getenv("MYMEMORY_API_URL", MYMEMORY_API_URL)
        self.contact_email = os.getenv("MYMEMORY_EMAIL")
        self.confidence_threshold = float(os.getenv("LANGUAGE_CONFIDENCE_THRESHOLD", "0.72"))
        self.short_line_chars = int(os.getenv("LANGUAGE_SHORT_LINE_CHARS", "12"))
        self.detector = LanguageDetectorBuilder.from_languages(*LINGUA_LANGUAGES).build()
        self.cache = TranslationCache(
            os.getenv("TRANSLATION_CACHE_PATH", ".cache/translations.sqlite3")
        )

    def _target_lang(self, target_lang, provider="mymemory"):
        normalized = target_lang.upper()
        if provider == "deepl":
            language_map = {
                "EN": "EN-US",
                "KO": "KO",
                "JA": "JA",
                "DE": "DE",
                "ES": "ES",
                "FR": "FR",
                "IT": "IT",
                "PT-BR": "PT-BR",
            }
            return language_map.get(normalized, normalized)

        language_map = {
            "DE": "de",
            "ES": "es",
            "FR": "fr",
            "IT": "it",
            "JA": "ja",
            "KO": "ko",
            "EN": "en",
            "PT-BR": "pt-br",
        }
        return language_map.get(normalized, target_lang.lower())

    def _normalized_lang(self, language):
        return (language or "und").lower().split("-")[0]

    def _language_name(self, language):
        return LANGUAGE_NAMES.get(self._normalized_lang(language), language.upper())

    def _lyrics_hash(self, lines):
        text = "\n".join(lines)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_key(self, track, lines, target_lang):
        provider = "deepl" if self.provider == "deepl" and self.deepl_api_key else "mymemory"
        payload = {
            "track_id": track.get("id", ""),
            "artist": track.get("artist", ""),
            "title": track.get("title", ""),
            "lyrics_hash": self._lyrics_hash(lines),
            "target": self._target_lang(target_lang, provider),
            "provider": provider,
            "version": 4,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def has_cached_translation(self, lines, target_lang="EN", track=None):
        """Return True when this track/lyric/target translation is already cached."""
        if not lines:
            return True
        cache_key = self._cache_key(track or {}, lines, target_lang)
        return self.cache.get(cache_key) is not None

    def clear_cached_track(self, track, target_lang=None):
        """Clear cached translations for a track when the user asks to fix it."""
        target = None
        if target_lang:
            target = self._normalized_lang(self._target_lang(target_lang, "mymemory"))
        return self.cache.delete_for_track(track or {}, target)

    def remember_recent_song(self, track, result, lyrics_source):
        self.cache.add_recent_song(track or {}, result or {}, lyrics_source or "")

    def get_recent_songs(self, limit=8):
        return self.cache.get_recent_songs(limit)

    def _is_punctuation_only(self, line):
        return bool(line.strip()) and not LETTER_OR_NUMBER_RE.search(line)

    def _is_vocal_only(self, line):
        if HANGUL_RE.search(line) or JAPANESE_RE.search(line):
            return False
        tokens = [token.lower() for token in VOCAL_TOKEN_RE.findall(line)]
        if not tokens:
            return False
        return all(token in VOCAL_TOKENS for token in tokens) and len(tokens) <= 6

    def _is_non_lyric(self, line):
        stripped = line.strip()
        return (
            not stripped
            or SECTION_HEADER_RE.match(stripped)
            or self._is_punctuation_only(stripped)
            or self._is_vocal_only(stripped)
        )

    def _is_short_line(self, line):
        tokens = VOCAL_TOKEN_RE.findall(line)
        return len(line.strip()) < self.short_line_chars or len(tokens) <= 2

    def _script_locked_language(self, text):
        if HANGUL_RE.search(text):
            return "ko", 0.99
        if JAPANESE_RE.search(text):
            return "ja", 0.96
        romanized_tokens = {
            token.lower() for token in VOCAL_TOKEN_RE.findall(text)
        }
        if romanized_tokens & ROMANIZED_KOREAN_TOKENS:
            return "ko", 0.58
        return None

    def _detect_language(self, text):
        if not text.strip():
            return "und", 0.0
        locked_language = self._script_locked_language(text)
        if locked_language:
            return locked_language

        has_latin = bool(LATIN_RE.search(text))
        has_cjk = bool(CJK_RE.search(text))

        confidence_values = self.detector.compute_language_confidence_values(text)
        if confidence_values:
            for candidate in confidence_values:
                language_code = LINGUA_CODES.get(candidate.language)
                if not language_code:
                    continue
                if has_latin and not has_cjk and language_code in {"ja", "ko", "zh"}:
                    continue
                if has_cjk and language_code == "ja":
                    continue
                return language_code, float(candidate.value)

        try:
            candidates = detect_langs(text)
        except LangDetectException:
            return "und", 0.0

        if not candidates:
            return "und", 0.0
        for candidate in candidates:
            language_code = self._normalized_lang(candidate.lang)
            if has_latin and not has_cjk and language_code in {"ja", "ko", "zh"}:
                continue
            if has_cjk and language_code == "ja":
                continue
            return candidate.lang, float(candidate.prob)
        return "und", 0.0

    def _should_use_japanese_context(self, line, context_source):
        if self._normalized_lang(context_source) != "ja":
            return False
        if HANGUL_RE.search(line) or LATIN_RE.search(line):
            return False
        return bool(JAPANESE_RE.search(line) or CJK_RE.search(line))

    def _verse_groups(self, lines):
        groups = []
        current = []
        for index, line in enumerate(lines):
            if SECTION_HEADER_RE.match(line.strip()):
                if current:
                    groups.append(current)
                    current = []
                continue
            current.append(index)
        if current:
            groups.append(current)
        return groups

    def _analysis_for_lines(self, lines, target_lang):
        target = self._normalized_lang(self._target_lang(target_lang, "mymemory"))
        analysis = [
            {
                "index": index,
                "line": line,
                "source": "und",
                "confidence": 0.0,
                "non_lyric": self._is_non_lyric(line),
                "low_confidence": False,
                "needs_translation": False,
                "verse_indexes": [],
            }
            for index, line in enumerate(lines)
        ]

        for group in self._verse_groups(lines):
            lyric_indexes = [
                index for index in group if not analysis[index]["non_lyric"]
            ]
            context_text = "\n".join(lines[index] for index in lyric_indexes)
            context_source, context_confidence = self._detect_language(context_text)

            for index in lyric_indexes:
                line = lines[index]
                line_source, line_confidence = self._detect_language(line)
                if self._should_use_japanese_context(line, context_source):
                    line_source = context_source
                    line_confidence = max(line_confidence, min(context_confidence, 0.9))
                normalized_line_source = self._normalized_lang(line_source)
                use_context = (
                    self._is_short_line(line)
                    and line_confidence < self.confidence_threshold
                    and normalized_line_source != target
                )

                if use_context:
                    source, confidence = context_source, context_confidence
                else:
                    source, confidence = line_source, line_confidence
                    if (
                        confidence < self.confidence_threshold
                        and self._normalized_lang(source) != target
                    ):
                        source, confidence = context_source, min(confidence, context_confidence)
                        use_context = True

                normalized_source = self._normalized_lang(source)
                needs_translation = normalized_source not in {"und", target}
                analysis[index].update(
                    {
                        "source": normalized_source,
                        "confidence": confidence,
                        "low_confidence": confidence < self.confidence_threshold,
                        "needs_translation": needs_translation,
                        "verse_indexes": lyric_indexes if use_context else [index],
                    }
                )

        return analysis

    def _source_summary(self, analysis):
        meaningful = [
            item for item in analysis if not item["non_lyric"] and item["source"] != "und"
        ]
        if not meaningful:
            return "und", 0.0

        languages = []
        for item in meaningful:
            if item["source"] not in languages:
                languages.append(item["source"])

        average_confidence = sum(item["confidence"] for item in meaningful) / len(meaningful)
        if len(languages) > 1:
            return "mixed", average_confidence
        return languages[0], average_confidence

    def _translation_label(self, source, target, status, analysis):
        target_name = self._language_name(target)
        if status == "translation_not_required":
            return f"Already in {target_name}"
        if status == "translation_failed":
            return "Translation failed"
        if source == "mixed":
            languages = []
            for item in analysis:
                source_lang = item["source"]
                if item["non_lyric"] or source_lang in {"und"}:
                    continue
                if source_lang not in languages:
                    languages.append(source_lang)
            names = [self._language_name(language) for language in languages[:3]]
            return f"Mixed {' and '.join(names)}"
        return f"Translated from {self._language_name(source)}"

    def _translate_texts_deepl(self, texts, target):
        if not self.deepl_api_key:
            raise TranslationError("DeepL API key is not configured.")
        if not texts:
            return []

        data = [("target_lang", target)]
        if self.source_lang.lower() != "auto":
            data.append(("source_lang", self._target_lang(self.source_lang, "deepl")))
        for text in texts:
            data.append(("text", text))

        try:
            response = requests.post(
                self.deepl_api_url,
                data=data,
                headers={"Authorization": f"DeepL-Auth-Key {self.deepl_api_key}"},
                timeout=20,
            )
        except RequestException as exc:
            raise TranslationError("DeepL translation failed.") from exc

        if response.status_code >= 400:
            raise TranslationError("DeepL translation failed.")

        translations = response.json().get("translations", [])
        if len(translations) != len(texts):
            raise TranslationError("DeepL returned an incomplete translation.")
        return [translation.get("text", original) for translation, original in zip(translations, texts)]

    def _translate_text_mymemory(self, text, source, target):
        params = {"q": text, "langpair": f"{source}|{target}"}
        if self.contact_email:
            params["de"] = self.contact_email

        try:
            response = requests.get(self.mymemory_api_url, params=params, timeout=15)
        except RequestException as exc:
            raise TranslationError("MyMemory translation failed.") from exc

        if response.status_code >= 400:
            raise TranslationError("MyMemory translation failed.")

        translated_text = response.json().get("responseData", {}).get("translatedText")
        if not translated_text:
            raise TranslationError("MyMemory translation failed.")
        return translated_text

    def _translate_texts_mymemory(self, texts, sources, target):
        return [
            self._translate_text_mymemory(text, source, target)
            for text, source in zip(texts, sources)
        ]

    def _provider_translate(self, texts, sources, target_lang):
        if not texts:
            return [], None

        if self.provider == "deepl":
            try:
                return self._translate_texts_deepl(
                    texts,
                    self._target_lang(target_lang, "deepl"),
                ), "deepl"
            except TranslationError:
                pass

        return self._translate_texts_mymemory(
            texts,
            sources,
            self._target_lang(target_lang, "mymemory"),
        ), "mymemory"

    def _split_block_translation(self, translated_text, expected_count):
        lines = [line.strip() for line in translated_text.splitlines()]
        lines = [line for line in lines if line]
        if len(lines) == expected_count:
            return lines
        return None

    def _should_retry_mixed_script_line(self, original, translated_text, source, target_lang):
        target = self._normalized_lang(self._target_lang(target_lang, "mymemory"))
        return (
            self._normalized_lang(source) != target
            and original.strip() == translated_text.strip()
            and CJK_SEGMENT_RE.search(original)
            and LATIN_RE.search(original)
        )

    def _translate_mixed_script_segments(self, line, source, target_lang):
        matches = list(CJK_SEGMENT_RE.finditer(line))
        if not matches:
            return line, None

        translated_segments, provider_used = self._provider_translate(
            [match.group(0) for match in matches],
            [source for _ in matches],
            target_lang,
        )

        pieces = []
        cursor = 0
        for match, translated_segment in zip(matches, translated_segments):
            pieces.append(line[cursor:match.start()])
            pieces.append(translated_segment)
            cursor = match.end()
        pieces.append(line[cursor:])
        return "".join(pieces), provider_used

    def _translation_reuse_key(self, text, source):
        normalized_text = re.sub(r"\s+", " ", text).strip().casefold()
        return (self._normalized_lang(source), normalized_text)

    def _translate_needed_lines(self, lines, analysis, target_lang):
        translated = list(lines)
        direct_items = []
        block_items = []
        used_indexes = set()

        for item in analysis:
            if not item["needs_translation"] or item["index"] in used_indexes:
                continue
            if item["low_confidence"] and len(item["verse_indexes"]) > 1:
                indexes = [
                    index for index in item["verse_indexes"]
                    if analysis[index]["needs_translation"]
                ]
                used_indexes.update(indexes)
                block_items.append(
                    {
                        "indexes": indexes,
                        "text": "\n".join(lines[index] for index in indexes),
                        "source": item["source"],
                    }
                )
            else:
                used_indexes.add(item["index"])
                direct_items.append(item)

        unique_direct_items = []
        direct_duplicates = {}
        for item in direct_items:
            key = self._translation_reuse_key(item["line"], item["source"])
            if key not in direct_duplicates:
                direct_duplicates[key] = []
                unique_direct_items.append(item)
            direct_duplicates[key].append(item)

        texts = [item["line"] for item in unique_direct_items]
        sources = [item["source"] for item in unique_direct_items]
        provider_used = None

        if texts:
            translated_texts, provider_used = self._provider_translate(texts, sources, target_lang)
            for item, translated_text in zip(unique_direct_items, translated_texts):
                if self._should_retry_mixed_script_line(
                    item["line"],
                    translated_text,
                    item["source"],
                    target_lang,
                ):
                    translated_text, segment_provider = self._translate_mixed_script_segments(
                        item["line"],
                        item["source"],
                        target_lang,
                    )
                    provider_used = provider_used or segment_provider
                for duplicate_item in direct_duplicates[
                    self._translation_reuse_key(item["line"], item["source"])
                ]:
                    translated[duplicate_item["index"]] = translated_text

        unique_block_items = []
        block_duplicates = {}
        for block in block_items:
            key = self._translation_reuse_key(block["text"], block["source"])
            if key not in block_duplicates:
                block_duplicates[key] = []
                unique_block_items.append(block)
            block_duplicates[key].append(block)

        for block in unique_block_items:
            block_translations, block_provider = self._provider_translate(
                [block["text"]],
                [block["source"]],
                target_lang,
            )
            provider_used = provider_used or block_provider
            split_lines = self._split_block_translation(
                block_translations[0],
                len(block["indexes"]),
            )
            for duplicate_block in block_duplicates[
                self._translation_reuse_key(block["text"], block["source"])
            ]:
                if split_lines:
                    for index, translated_text in zip(duplicate_block["indexes"], split_lines):
                        translated[index] = translated_text
                else:
                    for index in duplicate_block["indexes"]:
                        translated[index] = (
                            block_translations[0]
                            if index == duplicate_block["indexes"][0]
                            else lines[index]
                        )

        reused_repeated_lines = any(len(items) > 1 for items in direct_duplicates.values())
        reused_repeated_lines = reused_repeated_lines or any(
            len(items) > 1 for items in block_duplicates.values()
        )

        return translated, provider_used, reused_repeated_lines

    def _status_for_result(self, analysis, provider_used, failed=False):
        if failed:
            return "translation_failed"
        translatable = [item for item in analysis if item["needs_translation"]]
        if not translatable:
            return "translation_not_required"
        untouched_lyric = [
            item for item in analysis
            if not item["non_lyric"] and not item["needs_translation"]
        ]
        if untouched_lyric:
            return "partially_translated"
        return "translated" if provider_used else "translation_not_required"

    def translate_lyrics(self, lines, target_lang="EN", track=None):
        """Detect lyric language before calling any translation provider."""
        track = track or {}
        if not lines:
            return {
                "lines": [],
                "detected_source_language": "und",
                "target_language": self._normalized_lang(target_lang),
                "translation_status": "translation_not_required",
                "language_detection_confidence": 0.0,
                "translation_label": f"Already in {self._language_name(target_lang)}",
                "line_languages": [],
                "provider": None,
                "cache_hit": False,
                "reused_repeated_lines": False,
            }

        cache_key = self._cache_key(track, lines, target_lang)
        cached = self.cache.get(cache_key)
        if cached:
            metadata = cached.get("metadata", {})
            return {
                "lines": cached["lines"],
                "detected_source_language": cached["detected_source_language"],
                "target_language": cached["target_language"],
                "translation_status": cached["translation_status"],
                "language_detection_confidence": cached["language_detection_confidence"],
                "translation_label": metadata.get("translation_label", ""),
                "line_languages": metadata.get("line_languages", []),
                "provider": cached.get("provider"),
                "cache_hit": True,
                "reused_repeated_lines": metadata.get("reused_repeated_lines", False),
            }

        target = self._normalized_lang(self._target_lang(target_lang, "mymemory"))
        analysis = self._analysis_for_lines(lines, target_lang)
        source, confidence = self._source_summary(analysis)
        provider_used = None

        try:
            translated_lines, provider_used, reused_repeated_lines = self._translate_needed_lines(
                lines,
                analysis,
                target_lang,
            )
            status = self._status_for_result(analysis, provider_used)
        except TranslationError:
            translated_lines = list(lines)
            reused_repeated_lines = False
            status = "translation_failed"

        result = {
            "lines": translated_lines,
            "detected_source_language": source,
            "target_language": target,
            "translation_status": status,
            "language_detection_confidence": round(confidence, 4),
            "translation_label": self._translation_label(source, target, status, analysis),
            "line_languages": [
                {
                    "index": item["index"],
                    "language": item["source"],
                    "confidence": round(item["confidence"], 4),
                    "translated": item["needs_translation"] and status != "translation_failed",
                }
                for item in analysis
            ],
            "provider": provider_used,
            "cache_hit": False,
            "reused_repeated_lines": reused_repeated_lines,
        }
        self.cache.set(cache_key, track, self._lyrics_hash(lines), result)
        return result

    def translate_lines(self, lines, target_lang="EN"):
        """Backward-compatible wrapper for older callers."""
        return self.translate_lyrics(lines, target_lang)["lines"]
