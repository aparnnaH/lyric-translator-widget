import os
import re
from functools import lru_cache
from urllib.parse import quote_plus

import requests
from requests import RequestException


LRCLIB_API_URL = "https://lrclib.net/api"
TIMESTAMP_RE = re.compile(r"\[(?:(\d+):)?(\d+):(\d{2})(?:\.(\d{1,3}))?\]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff]")
KOREAN_ARTIST_HINTS = {
    "agust d",
    "blackpink",
    "bts",
    "j-hope",
    "jimin",
    "jin",
    "jungkook",
    "newjeans",
    "rm",
    "suga",
    "txt",
    "v",
    "방탄소년단",
}
JAPANESE_VERSION_HINTS = {
    "japanese",
    "japanese ver",
    "japanese version",
    "jpn",
    "jp ver",
    "日本語",
}


class LrcLibError(Exception):
    pass


class LrcLibClient:
    def __init__(self):
        self.api_url = os.getenv("LRCLIB_API_URL", LRCLIB_API_URL).rstrip("/")

    def _headers(self):
        return {"User-Agent": "music-translator-web/1.0"}

    def _parse_time(self, match):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        fraction = match.group(4) or "0"
        milliseconds = int(fraction.ljust(3, "0")[:3])
        return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000

    def _parse_synced_lyrics(self, synced_lyrics):
        lines = []
        for raw_line in synced_lyrics.splitlines():
            matches = list(TIMESTAMP_RE.finditer(raw_line))
            if not matches:
                continue

            text = TIMESTAMP_RE.sub("", raw_line).strip()
            if not text:
                continue

            for match in matches:
                lines.append({"time": self._parse_time(match), "text": text})

        return sorted(lines, key=lambda line: line["time"])

    def _plain_lines(self, plain_lyrics):
        return [line.strip() for line in plain_lyrics.splitlines() if line.strip()]

    def _record_text(self, record):
        return "\n".join(
            value for value in [
                record.get("trackName") or "",
                record.get("plainLyrics") or "",
                record.get("syncedLyrics") or "",
            ] if value
        )

    def _script_counts_for_text(self, text):
        return len(HANGUL_RE.findall(text)), len(JAPANESE_RE.findall(text))

    def _script_counts(self, record):
        return self._script_counts_for_text(self._record_text(record))

    def _is_korean_artist(self, artist):
        normalized_artist = artist.lower()
        return any(hint in normalized_artist for hint in KOREAN_ARTIST_HINTS)

    def _is_japanese_version_request(self, title):
        normalized_title = title.lower()
        return any(hint in normalized_title for hint in JAPANESE_VERSION_HINTS)

    def _is_wrong_japanese_match(self, record, artist, title):
        if not self._is_korean_artist(artist) or self._is_japanese_version_request(title):
            return False

        hangul_count, japanese_count = self._script_counts(record)
        return japanese_count >= 3 and hangul_count == 0

    def _is_wrong_japanese_lyrics(self, lyrics, artist, title):
        if not self._is_korean_artist(artist) or self._is_japanese_version_request(title):
            return False

        hangul_count, japanese_count = self._script_counts_for_text("\n".join(lyrics))
        return japanese_count >= 3 and hangul_count == 0

    def _score_record(self, record, artist, title):
        artist_name = record.get("artistName", "").lower()
        track_name = record.get("trackName", "").lower()
        normalized_artist = artist.lower()
        normalized_title = title.lower()
        hangul_count, japanese_count = self._script_counts(record)

        score = 0
        if record.get("syncedLyrics"):
            score += 10
        if record.get("plainLyrics"):
            score += 4
        if track_name == normalized_title:
            score += 6
        elif normalized_title in track_name or track_name in normalized_title:
            score += 3
        if artist_name == normalized_artist:
            score += 5
        elif normalized_artist in artist_name or artist_name in normalized_artist:
            score += 2
        if self._is_korean_artist(artist) and not self._is_japanese_version_request(title):
            if hangul_count:
                score += 8
            if japanese_count >= 3 and hangul_count == 0:
                score -= 20
        return score

    def _format_result(self, record, artist, title):
        synced_lines = self._parse_synced_lyrics(record.get("syncedLyrics") or "")
        if synced_lines:
            lyrics = [line["text"] for line in synced_lines]
        else:
            lyrics = self._plain_lines(record.get("plainLyrics") or "")

        if not lyrics and not record.get("instrumental"):
            raise LrcLibError("LRCLIB did not return lyric lines for this song.")
        if self._is_wrong_japanese_lyrics(lyrics, artist, title):
            raise LrcLibError(
                "LRCLIB returned Japanese-version lyrics for this Korean song."
            )

        query = quote_plus(f"{artist} {title}")
        has_synced = bool(synced_lines)
        return {
            "lyrics": lyrics,
            "synced_lyrics": synced_lines,
            "timing_source": "lrclib" if has_synced else "estimated",
            "lyric_source": "LRCLIB",
            "info": {
                "about": (
                    "Synced lyrics are available from LRCLIB."
                    if has_synced
                    else "Plain lyrics are available from LRCLIB."
                ),
                "source": "LRCLIB",
                "source_url": f"https://lrclib.net/search/{query}",
            },
        }

    @lru_cache(maxsize=128)
    def get_lyrics(self, artist, title):
        try:
            response = requests.get(
                f"{self.api_url}/search",
                params={"artist_name": artist, "track_name": title},
                headers=self._headers(),
                timeout=10,
            )
        except RequestException as exc:
            raise LrcLibError("LRCLIB search failed.") from exc

        if response.status_code == 404:
            raise LrcLibError("No LRCLIB lyrics were found for this song.")
        if response.status_code >= 400:
            raise LrcLibError("LRCLIB search failed.")

        try:
            records = response.json()
        except ValueError as exc:
            raise LrcLibError("LRCLIB returned an invalid response.") from exc
        if not records:
            raise LrcLibError("No LRCLIB lyrics were found for this song.")

        records = [
            record for record in records
            if not self._is_wrong_japanese_match(record, artist, title)
        ]
        if not records:
            raise LrcLibError(
                "LRCLIB only returned Japanese-version lyrics for this Korean song."
            )

        records = sorted(
            records,
            key=lambda record: self._score_record(record, artist, title),
            reverse=True,
        )
        return self._format_result(records[0], artist, title)
