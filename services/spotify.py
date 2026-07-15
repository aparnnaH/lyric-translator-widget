import subprocess


SPOTIFY_PERMISSION_MESSAGE = (
    "Allow LumaLyrics to control Spotify in System Settings > Privacy & Security > Automation."
)


SPOTIFY_SCRIPT = """
tell application "Spotify"
  set playState to player state as string
  if playState is "stopped" then
    return "STOPPED"
  end if

  try
    set trackId to id of current track
  on error
    set trackId to ""
  end try
  try
    set trackName to name of current track
  on error
    set trackName to "Advertisement"
  end try
  try
    set artistName to artist of current track
  on error
    set artistName to "Spotify"
  end try
  try
    set albumArt to artwork url of current track
  on error
    set albumArt to ""
  end try
  set songPosition to player position
  try
    set songDuration to duration of current track
  on error
    set songDuration to ""
  end try

  return trackId & linefeed & trackName & linefeed & artistName & linefeed & albumArt & linefeed & songPosition & linefeed & songDuration & linefeed & playState
end tell
"""


class LocalSpotifyError(Exception):
    pass


class LocalSpotifyClient:
    def _friendly_error(self, message):
        if "-1743" in message or "Not authorized to send Apple events" in message:
            return SPOTIFY_PERMISSION_MESSAGE
        return message

    def _is_ad(self, track_id, title, artist):
        """Spotify ads do not behave like normal spotify:track playback."""
        normalized_title = (title or "").strip().lower()
        normalized_artist = (artist or "").strip().lower()
        if not track_id.startswith("spotify:track:"):
            return True
        if normalized_title in {"advertisement", "spotify advertisement"}:
            return True
        if normalized_artist == "spotify" and "ad" in normalized_title:
            return True
        return False

    def _is_spotify_running(self):
        try:
            result = subprocess.run(
                ["pgrep", "-x", "Spotify"],
                capture_output=True,
                check=False,
                text=True,
                timeout=1,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        return result.returncode == 0

    def _run_script(self):
        if not self._is_spotify_running():
            return "NOT_RUNNING"

        try:
            result = subprocess.run(
                ["osascript", "-e", SPOTIFY_SCRIPT],
                capture_output=True,
                check=False,
                text=True,
                timeout=3,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise LocalSpotifyError("Could not ask the Spotify desktop app for playback.") from exc

        if result.returncode != 0:
            message = result.stderr.strip() or "Spotify desktop playback is unavailable."
            raise LocalSpotifyError(self._friendly_error(message))

        return result.stdout.strip()

    def get_setup_status(self):
        """Return setup readiness for the onboarding checklist."""
        if not self._is_spotify_running():
            return {
                "spotify_running": False,
                "automation_allowed": False,
                "has_playback": False,
                "is_ready": False,
                "message": "Open Spotify to begin.",
            }

        try:
            output = self._run_script()
        except LocalSpotifyError as exc:
            return {
                "spotify_running": True,
                "automation_allowed": False,
                "has_playback": False,
                "is_ready": False,
                "message": str(exc),
            }

        has_playback = output not in {"NOT_RUNNING", "STOPPED", ""}
        return {
            "spotify_running": True,
            "automation_allowed": True,
            "has_playback": has_playback,
            "is_ready": has_playback,
            "message": "" if has_playback else "Play a song in Spotify.",
        }

    def _run_control_script(self, command):
        if not self._is_spotify_running():
            return

        try:
            result = subprocess.run(
                ["osascript", "-e", f'tell application "Spotify" to {command}'],
                capture_output=True,
                check=False,
                text=True,
                timeout=3,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise LocalSpotifyError(f"Could not {command} Spotify playback.") from exc

        if result.returncode != 0:
            message = result.stderr.strip() or f"Spotify could not {command} playback."
            raise LocalSpotifyError(self._friendly_error(message))

    def _escape_applescript_string(self, value):
        return value.replace("\\", "\\\\").replace('"', '\\"')

    def pause(self):
        """Pause local Spotify playback."""
        self._run_control_script("pause")

    def play(self):
        """Resume local Spotify playback."""
        self._run_control_script("play")

    def toggle_playback(self):
        """Toggle local Spotify playback."""
        self._run_control_script("playpause")

    def play_track(self, track_uri):
        """Ask Spotify Desktop to play a specific Spotify track URI."""
        if not track_uri.startswith("spotify:track:"):
            raise LocalSpotifyError("Only Spotify tracks from recent songs can be replayed.")
        escaped_uri = self._escape_applescript_string(track_uri)
        self._run_control_script(f'play track "{escaped_uri}"')

    def _duration_seconds(self, raw_duration):
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            return None

        if duration > 10000:
            return duration / 1000
        return duration

    def get_current_track(self):
        """Read current playback directly from the local macOS Spotify app."""
        output = self._run_script()
        if output in {"NOT_RUNNING", "STOPPED", ""}:
            return None

        parts = output.splitlines()
        if len(parts) < 7:
            raise LocalSpotifyError("Spotify desktop returned an incomplete playback response.")

        track_id, title, artist, album_art, position, duration, play_state = parts[:7]
        try:
            progress_seconds = float(position)
        except ValueError as exc:
            raise LocalSpotifyError("Spotify desktop returned an invalid playback position.") from exc

        is_ad = self._is_ad(track_id, title, artist)
        if is_ad:
            return {
                "title": "Advertisement",
                "artist": "Spotify",
                "album_art": "",
                "source_url": "",
                "id": track_id or "spotify-ad",
                "progress_seconds": progress_seconds,
                "duration_seconds": self._duration_seconds(duration),
                "is_playing": play_state == "playing",
                "playback_source": "spotify-local",
                "is_ad": True,
            }

        return {
            "title": title,
            "artist": artist,
            "album_art": album_art,
            "source_url": track_id.replace("spotify:track:", "https://open.spotify.com/track/"),
            "id": track_id,
            "progress_seconds": progress_seconds,
            "duration_seconds": self._duration_seconds(duration),
            "is_playing": play_state == "playing",
            "playback_source": "spotify-local",
        }
