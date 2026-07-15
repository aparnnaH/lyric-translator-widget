# LumaLyrics

A minimal Flask/Electron lyric widget that reads playback from the local Spotify desktop app, fetches synced lyrics from LRCLIB with Genius as a fallback, and translates Korean/English lyric lines with DeepL Free plus MyMemory fallback.

## Setup

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your API credentials.

3. Create a Last.fm API account at `https://www.last.fm/api/account/create`, then put your API key and username in `.env`.

4. Open the Spotify desktop app on your Mac and start playing a song. If macOS asks whether Terminal or Python can control Spotify, allow it.

5. Last.fm is still supported as a fallback if local Spotify is not running. To use that fallback, make sure your music app is scrobbling to Last.fm.

6. Run the app:

```bash
flask --app app run --debug --port 5001
```

Open `http://127.0.0.1:5001` and play a song in Spotify Desktop.

For the compact player, open `http://127.0.0.1:5001/widget`.

## LumaLyrics Desktop Widget

The Electron wrapper keeps the same Flask backend and opens the compact widget in a small always-on-top Mac window.

Install the desktop dependencies once:

```bash
npm install
```

Run the desktop widget:

```bash
npm run desktop
```

Build a Mac app bundle:

```bash
npm run desktop:package
```

The desktop app starts the Flask server automatically if `http://127.0.0.1:5001` is not already running.

## Environment Variables

- `FLASK_SECRET_KEY`
- `LASTFM_API_KEY`
- `LASTFM_USERNAME`
- `GENIUS_ACCESS_TOKEN`
- `LRCLIB_API_URL` defaults to `https://lrclib.net/api`
- `TRANSLATION_PROVIDER` defaults to `mymemory`; set to `deepl` to use DeepL first
- `TRANSLATION_SOURCE_LANG` defaults to `auto`
- `DEEPL_API_KEY` enables DeepL translation
- `DEEPL_API_URL` defaults to `https://api-free.deepl.com/v2/translate`
- `TRANSLATION_CACHE_PATH` defaults to `.cache/translations.sqlite3`
- `LANGUAGE_CONFIDENCE_THRESHOLD` defaults to `0.72`
- `LANGUAGE_SHORT_LINE_CHARS` defaults to `12`
- `SPOTIFY_TRANSLATION_PAUSE_WINDOW_SECONDS` defaults to `12`; new songs can pause briefly during this opening window while lyrics and translation are prepared
- `MYMEMORY_API_URL` defaults to `https://api.mymemory.translated.net/get`
- `MYMEMORY_EMAIL` is optional but recommended by MyMemory for higher-volume usage

## Routes

- `/` homepage
- `/widget` compact lyric player
- `/focus` full-screen lyric focus mode
- `/login` redirects home; kept for compatibility after removing Spotify OAuth
- `/callback` redirects home; kept for compatibility after removing Spotify OAuth
- `/current-song` current local Spotify track JSON, falling back to Last.fm
- `/playback-sync` local Spotify playback position JSON for syncing LRCLIB timestamps
- `/lyrics` current track lyrics JSON, including LRCLIB synced timing when available
- `/translated-lyrics?lang=ES` paired original and translated lyric lines

## Lyrics Sources

The app tries LRCLIB first because it can return timestamped `syncedLyrics` for karaoke-style highlighting without scraping. If LRCLIB does not have the track, the app falls back to Genius and uses the estimated line-by-line karaoke timer.

## Translation

Set `TRANSLATION_PROVIDER=deepl` and `DEEPL_API_KEY=...` to use DeepL Free first. Before calling any translation provider, the app detects lyric language locally with `lingua-language-detector`, skips section labels, blank/punctuation-only lines, and simple vocal sounds, and avoids translation when the lyrics already match the selected display language. If DeepL is not configured or fails, the app falls back to MyMemory.

Translation results are cached locally in SQLite at `.cache/translations.sqlite3`. The cache stores the detected source language, target language, translation status, language-detection confidence, translated lines, and label metadata.

## Karaoke Sync

For free local sync, the app asks the Spotify desktop app for `player position` using macOS `osascript`. That position is matched against LRCLIB timestamps, so lyrics can stay aligned even if the page loads late, Spotify is paused, or you scrub within the Spotify app.

When the web page or widget loads a new uncached song near the beginning, it can briefly pause Spotify Desktop while LRCLIB lyrics and translations are prepared, then resume playback automatically. This only runs for local Spotify Desktop playback, not ads or Last.fm fallback tracks.

This local sync only works for Spotify playing on the same Mac. If Spotify desktop is not running, the app falls back to Last.fm for track detection, but Last.fm cannot provide exact playback position.
