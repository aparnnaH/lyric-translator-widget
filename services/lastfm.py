import os

import requests


LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


class LastFmError(Exception):
    pass


class LastFmClient:
    def __init__(self):
        self.api_key = os.getenv("LASTFM_API_KEY", "").strip()
        self.username = os.getenv("LASTFM_USERNAME", "").strip()

    def _require_config(self):
        """Ensure Last.fm can identify which user's current song to read."""
        if not self.api_key or not self.username:
            raise LastFmError("Last.fm API key and username are not configured.")
        if self.username == "your-lastfm-username":
            raise LastFmError("Replace LASTFM_USERNAME in .env with your real Last.fm username.")
        if self.api_key == "your-lastfm-api-key":
            raise LastFmError("Replace LASTFM_API_KEY in .env with your real Last.fm API key.")

    def get_current_track(self):
        """Return the user's currently playing track from Last.fm recent tracks."""
        self._require_config()
        response = requests.get(
            LASTFM_API_URL,
            params={
                "method": "user.getRecentTracks",
                "user": self.username,
                "api_key": self.api_key,
                "format": "json",
                "limit": 1,
            },
            timeout=10,
        )
        if response.status_code >= 400:
            raise LastFmError(f"Last.fm returned HTTP {response.status_code}.")

        data = response.json()
        if "error" in data:
            message = data.get("message", "Last.fm could not return recent tracks.")
            raise LastFmError(f"Last.fm error: {message}")

        tracks = data.get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        if not tracks:
            return None

        track = tracks[0]
        attrs = track.get("@attr", {})
        if attrs.get("nowplaying") != "true":
            return None

        images = track.get("image", [])
        album_art = ""
        for image in reversed(images):
            if image.get("#text"):
                album_art = image["#text"]
                break

        artist = track.get("artist", {})
        return {
            "title": track.get("name", ""),
            "artist": artist.get("#text", "") if isinstance(artist, dict) else artist,
            "album_art": album_art,
            "source_url": track.get("url", ""),
            "id": f"{artist}-{track.get('name', '')}",
        }
