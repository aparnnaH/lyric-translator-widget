import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

from services.genius import GeniusClient, LyricsNotFoundError
from services.lastfm import LastFmClient, LastFmError
from services.lrclib import LrcLibClient, LrcLibError
from services.romanizer import romanize_korean
from services.spotify import LocalSpotifyClient, LocalSpotifyError
from services.translator import TranslatorClient, TranslationError

load_dotenv(os.getenv("LYRIC_TRANSLATOR_ENV", ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

track_source = LastFmClient()
local_spotify = LocalSpotifyClient()
lrclib = LrcLibClient()
genius = GeniusClient()
translator = TranslatorClient()


def env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


TRANSLATION_PAUSE_WINDOW_SECONDS = env_float(
    "SPOTIFY_TRANSLATION_PAUSE_WINDOW_SECONDS",
    "12",
)


def json_error(message, status_code=400):
    """Return a consistent JSON error response for API routes."""
    return jsonify({"error": message}), status_code


def get_current_track():
    """Prefer local Spotify playback and fall back to Last.fm scrobbling."""
    spotify_error = None
    try:
        spotify_track = local_spotify.get_current_track()
        if spotify_track:
            return spotify_track
    except LocalSpotifyError as exc:
        spotify_error = exc

    try:
        return track_source.get_current_track()
    except LastFmError as exc:
        if spotify_error:
            raise LastFmError(f"{spotify_error} Last.fm fallback also failed: {exc}") from exc
        raise


def get_local_spotify_track():
    """Fetch playback position from the local Spotify desktop app only."""
    return local_spotify.get_current_track()


def get_lyrics_for_track(track):
    """Prefer timestamped LRCLIB lyrics and fall back to Genius text lyrics."""
    if track.get("is_ad"):
        raise LyricsNotFoundError("Spotify is playing an ad. Lyrics will resume after the next song.")

    try:
        return lrclib.get_lyrics(track["artist"], track["title"])
    except LrcLibError:
        lyric_result = genius.get_lyrics(track["artist"], track["title"])
        return {
            **lyric_result,
            "synced_lyrics": [],
            "timing_source": "estimated",
            "lyric_source": "Genius",
        }


def clear_song_caches(track, target_lang=None):
    """Clear provider and translation caches before retrying a problematic song."""
    lrclib.get_lyrics.cache_clear()
    genius.get_lyrics.cache_clear()
    translator.clear_cached_track(track, target_lang)


def lyrics_source_label(lyric_result):
    """Return a compact source label for UI badges."""
    source = lyric_result.get("lyric_source", "Genius")
    if source == "LRCLIB":
        return "LRCLIB synced" if lyric_result.get("synced_lyrics") else "LRCLIB plain"
    return source


def is_translation_pause_candidate(track):
    """Return True when playback is local Spotify and near the song start."""
    if track.get("playback_source") != "spotify-local":
        return False
    if track.get("is_ad") or not track.get("is_playing"):
        return False

    try:
        progress_seconds = float(track.get("progress_seconds", 999999))
    except (TypeError, ValueError):
        return False

    if progress_seconds > TRANSLATION_PAUSE_WINDOW_SECONDS:
        return False

    return True


def should_pause_for_translation(track, lines, target_lang):
    """Pause only for uncached local Spotify songs at the beginning of playback."""
    if not is_translation_pause_candidate(track):
        return False
    return not translator.has_cached_translation(lines, target_lang, track=track)


@app.route("/")
def home():
    """Render the single-page lyric translator UI."""
    return render_template("index.html")


@app.route("/widget")
def widget():
    """Render the compact lyric widget UI."""
    return render_template("widget.html")


@app.route("/focus")
def focus():
    """Render the full-screen lyric focus mode."""
    return render_template("focus.html")


@app.route("/login")
def login():
    """Keep the old route available; Last.fm does not require app login."""
    return redirect(url_for("home"))


@app.route("/callback")
def callback():
    """Keep the old route available after switching away from Spotify OAuth."""
    return redirect(url_for("home"))


@app.route("/current-song")
def current_song():
    """Return the currently playing track as JSON."""
    try:
        track = get_current_track()
    except LastFmError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not read your current track.", 502)

    if not track:
        return json_error("No currently playing track was found.", 404)

    return jsonify(track)


@app.route("/playback-sync")
def playback_sync():
    """Return local Spotify playback position for lyric synchronization."""
    try:
        track = get_local_spotify_track()
    except LocalSpotifyError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not read local Spotify playback.", 502)

    if not track:
        return json_error("Spotify desktop is not currently playing a track.", 404)

    return jsonify(track)


@app.route("/setup-status")
def setup_status():
    """Return local Spotify setup readiness for first-run onboarding."""
    return jsonify(local_spotify.get_setup_status())


@app.route("/playback-toggle", methods=["POST"])
def playback_toggle():
    """Toggle local Spotify desktop playback and return the updated track state."""
    try:
        local_spotify.toggle_playback()
        track = get_local_spotify_track()
    except LocalSpotifyError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not control local Spotify playback.", 502)

    if not track:
        return json_error("Spotify desktop is not currently playing a track.", 404)

    return jsonify(track)


@app.route("/recent-songs")
def recent_songs():
    """Return locally remembered translated Spotify songs."""
    try:
        limit = max(1, min(20, int(request.args.get("limit", "8"))))
    except ValueError:
        limit = 8
    return jsonify({"songs": translator.get_recent_songs(limit)})


@app.route("/recent-songs/play", methods=["POST"])
def play_recent_song():
    """Replay a remembered Spotify track in the local Spotify desktop app."""
    payload = request.get_json(silent=True) or {}
    track_id = payload.get("track_id", "")
    try:
        local_spotify.play_track(track_id)
        track = get_local_spotify_track()
    except LocalSpotifyError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not replay this song in Spotify.", 502)

    return jsonify(track or {"id": track_id, "is_playing": True})


@app.route("/lyrics")
def lyrics():
    """Return clean lyric lines for the currently playing track."""
    try:
        track = get_current_track()
        if not track:
            return json_error("No currently playing track was found on Last.fm.", 404)
        if track.get("is_ad"):
            return json_error(
                "Spotify is playing an ad. Lyrics will resume after the next song.",
                409,
            )

        lyric_result = get_lyrics_for_track(track)
    except LyricsNotFoundError as exc:
        return json_error(str(exc), 404)
    except LastFmError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not fetch lyrics for this track.", 502)

    return jsonify(
        {
            "track": track,
            **lyric_result,
            "lyrics_source_label": lyrics_source_label(lyric_result),
        }
    )


@app.route("/translated-lyrics")
def translated_lyrics():
    """Return original lyric lines paired with translated lines."""
    target_lang = request.args.get("lang", "ES").upper()
    auto_pause = request.args.get("auto_pause") == "1"
    force_reload = request.args.get("force") == "1"
    paused_for_translation = False

    try:
        track = get_current_track()
        if not track:
            return json_error("No currently playing track was found on Last.fm.", 404)
        if track.get("is_ad"):
            return json_error(
                "Spotify is playing an ad. Lyrics will resume after the next song.",
                409,
            )

        if force_reload:
            clear_song_caches(track, target_lang)

        if auto_pause and is_translation_pause_candidate(track):
            try:
                local_spotify.pause()
                paused_for_translation = True
            except LocalSpotifyError:
                paused_for_translation = False

        try:
            lyric_result = get_lyrics_for_track(track)
            lines = lyric_result["lyrics"]
            if (
                auto_pause
                and not paused_for_translation
                and should_pause_for_translation(track, lines, target_lang)
            ):
                try:
                    local_spotify.pause()
                    paused_for_translation = True
                except LocalSpotifyError:
                    paused_for_translation = False

            translation_result = translator.translate_lyrics(lines, target_lang, track=track)
            translator.remember_recent_song(
                track,
                translation_result,
                lyrics_source_label(lyric_result),
            )
        finally:
            if paused_for_translation:
                try:
                    local_spotify.play()
                except LocalSpotifyError:
                    pass

        translated_lines = translation_result["lines"]
    except LyricsNotFoundError as exc:
        return json_error(str(exc), 404)
    except TranslationError as exc:
        return json_error(str(exc), 502)
    except LastFmError as exc:
        return json_error(str(exc), 400)
    except Exception:
        return json_error("Could not translate lyrics for this track.", 502)

    paired = [
        {
            "original": original,
            "romanized": romanize_korean(original),
            "translated": translated,
        }
        for original, translated in zip(lines, translated_lines)
    ]
    return jsonify(
        {
            "track": track,
            "language": target_lang,
            "lyrics": paired,
            "info": lyric_result["info"],
            "synced_lyrics": lyric_result.get("synced_lyrics", []),
            "timing_source": lyric_result.get("timing_source", "estimated"),
            "lyric_source": lyric_result.get("lyric_source", "Genius"),
            "lyrics_source_label": lyrics_source_label(lyric_result),
            "detected_source_language": translation_result["detected_source_language"],
            "target_language": translation_result["target_language"],
            "translation_status": translation_result["translation_status"],
            "language_detection_confidence": translation_result[
                "language_detection_confidence"
            ],
            "translation_label": translation_result["translation_label"],
            "translation_provider": translation_result.get("provider"),
            "translation_cache_hit": translation_result.get("cache_hit", False),
            "reused_repeated_lines": translation_result.get("reused_repeated_lines", False),
            "line_languages": translation_result["line_languages"],
            "paused_for_translation": paused_for_translation,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
