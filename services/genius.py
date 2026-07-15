import os
import re
from functools import lru_cache

import requests
from bs4 import BeautifulSoup


GENIUS_API_URL = "https://api.genius.com"
INFO_STOP_RE = re.compile(r"^\[.+\]")
LANGUAGE_LABELS = {
    "Translations",
    "Romanization",
    "English",
    "العربية",
    "Български",
    "Česky",
    "Deutsch",
    "Español",
    "Français",
    "Italiano",
    "日本語 (Japanese)",
    "Português",
    "Русский (Russian)",
    "Tiếng Việt",
    "ไทย (Thai)",
    "Türkçe",
    "Українська",
}


class LyricsNotFoundError(Exception):
    pass


class GeniusClient:
    def __init__(self):
        self.access_token = os.getenv("GENIUS_ACCESS_TOKEN")

    def _headers(self):
        """Build authorized Genius API headers."""
        if not self.access_token:
            raise LyricsNotFoundError("Genius API token is not configured.")
        return {"Authorization": f"Bearer {self.access_token}"}

    def _search_song(self, artist, title):
        """Search Genius and return the best matching song result."""
        response = requests.get(
            f"{GENIUS_API_URL}/search",
            params={"q": f"{artist} {title}"},
            headers=self._headers(),
            timeout=10,
        )
        if response.status_code >= 400:
            raise LyricsNotFoundError("Genius search failed.")

        hits = response.json().get("response", {}).get("hits", [])
        if not hits:
            raise LyricsNotFoundError("No lyrics were found for this song.")

        normalized_artist = artist.lower()
        normalized_title = title.lower()

        for hit in hits:
            result = hit.get("result", {})
            primary_artist = result.get("primary_artist", {}).get("name", "").lower()
            result_title = result.get("title", "").lower()
            if primary_artist in normalized_artist or result_title in normalized_title:
                return result

        return hits[0].get("result", {})

    def _search_song_url(self, artist, title):
        """Search Genius and return the best matching lyrics page URL."""
        return self._search_song(artist, title).get("url")

    def _clean_line(self, line):
        """Remove Genius annotations and extra whitespace from a lyric line."""
        line = re.sub(r"\[.*?\]", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        return line

    def _clean_section_header(self, line):
        """Keep lyric section headers readable instead of merging them away."""
        line = re.sub(r"\s+", " ", line).strip()
        return line

    def _is_metadata_line(self, line, title):
        """Identify Genius navigation and contributor lines that are not lyrics."""
        if not line:
            return True
        if line in LANGUAGE_LABELS:
            return True
        if line == "Read More" or line == "Embed":
            return True
        if re.match(r"^\d+\s+Contributors?$", line):
            return True
        if line.lower() == f"{title.lower()} lyrics":
            return True
        return False

    def _extract_info(self, raw_lines, title, song_url):
        """Extract a short Genius song blurb for the UI info box."""
        info_lines = []
        for raw_line in raw_lines:
            line = re.sub(r"\s+", " ", raw_line).strip()
            if INFO_STOP_RE.match(line):
                break
            if self._is_metadata_line(line, title):
                continue
            info_lines.append(line)

        about = " ".join(info_lines)
        about = re.sub(r"\s+", " ", about).strip()
        return {
            "about": about,
            "source": "Genius",
            "source_url": song_url,
        }

    def _extract_lyric_lines(self, raw_lines):
        """Drop Genius page chrome and keep only lyric lines after first section."""
        lines = []
        has_seen_section = False

        for raw_line in raw_lines:
            raw_line = re.sub(r"\s+", " ", raw_line).strip()
            if not raw_line:
                continue

            if INFO_STOP_RE.match(raw_line):
                has_seen_section = True
                lines.append(self._clean_section_header(raw_line))
                continue

            if not has_seen_section:
                continue

            cleaned = self._clean_line(raw_line)
            if cleaned and cleaned != "Embed":
                lines.append(cleaned)

        return lines

    @lru_cache(maxsize=128)
    def get_lyrics(self, artist, title):
        """Fetch a Genius page and return lyric lines with useful song info."""
        song = self._search_song(artist, title)
        song_url = song.get("url")
        if not song_url:
            raise LyricsNotFoundError("No lyrics were found for this song.")

        response = requests.get(song_url, timeout=10)
        if response.status_code >= 400:
            raise LyricsNotFoundError("Could not open the Genius lyrics page.")

        soup = BeautifulSoup(response.text, "html.parser")
        lyric_nodes = soup.select("div[data-lyrics-container='true']")
        raw_text = "\n".join(node.get_text("\n") for node in lyric_nodes)
        raw_lines = raw_text.splitlines()

        lines = self._extract_lyric_lines(raw_lines)

        if not lines:
            raise LyricsNotFoundError("No lyrics were found for this song.")

        return {
            "lyrics": lines,
            "info": self._extract_info(raw_lines, song.get("title", title), song_url),
        }

    def get_lyrics_lines(self, artist, title):
        """Fetch a Genius page and return only clean lyric lines."""
        return self.get_lyrics(artist, title)["lyrics"]
