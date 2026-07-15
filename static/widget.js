const artEl = document.querySelector("#widget-art");
const titleEl = document.querySelector("#widget-title");
const artistEl = document.querySelector("#widget-artist");
const languageEl = document.querySelector("#widget-language");
const emptyEl = document.querySelector("#widget-empty");
const lyricsEl = document.querySelector("#widget-lyrics");
const originalEl = document.querySelector("#widget-original");
const romanizedEl = document.querySelector("#widget-romanized");
const translatedEl = document.querySelector("#widget-translated");
const prevEl = document.querySelector("#widget-prev");
const nextEl = document.querySelector("#widget-next");
const statusEl = document.querySelector("#widget-status");
const translationEl = document.querySelector("#widget-translation");
const syncEl = document.querySelector("#widget-sync");
const sourceEl = document.querySelector("#widget-source");
const preparingEl = document.querySelector("#widget-preparing");
const preparingArtEl = document.querySelector("#widget-preparing-art");
const romanizationToggleEl = document.querySelector("#widget-romanization-toggle");
const progressFillEl = document.querySelector("#widget-progress-fill");
const elapsedTimeEl = document.querySelector("#widget-elapsed");
const durationTimeEl = document.querySelector("#widget-duration");
const reloadEl = document.querySelector("#widget-reload");
const playToggleEl = document.querySelector("#widget-play-toggle");
const moreMenuEl = document.querySelector("#widget-more-menu");
const permissionEl = document.querySelector("#widget-permission");
const setupEl = document.querySelector("#widget-setup");
const setupOpenEl = document.querySelector("#widget-setup-open");
const setupPermissionEl = document.querySelector("#widget-setup-permission");
const setupPlayEl = document.querySelector("#widget-setup-play");
const creditSongEl = document.querySelector("#widget-credit-song");
const creditArtistEl = document.querySelector("#widget-credit-artist");
const creditPlaybackEl = document.querySelector("#widget-credit-playback");
const creditPlaybackTextEl = document.querySelector("#widget-credit-playback-text");
const creditLyricsEl = document.querySelector("#widget-credit-lyrics");
const creditLyricsTextEl = document.querySelector("#widget-credit-lyrics-text");
const creditTranslationEl = document.querySelector("#widget-credit-translation");
const qualityEl = document.querySelector("#widget-quality");
const openSongEl = document.querySelector("#widget-open-song");
const openSourceEl = document.querySelector("#widget-open-source");
const recentSongsEl = document.querySelector("#widget-recent-songs");
const openSpotifyEls = document.querySelectorAll("[data-open-spotify]");

let lastTrackId = "";
let lyricPairs = [];
let syncedTimings = [];
let playbackSnapshot = null;
let lastRenderedTrack = null;
let estimatedStartedAt = 0;
let isLoading = false;
let activeLyricIndex = 0;
let showRomanization = localStorage.getItem("lyric-widget-romanization") !== "off";

romanizationToggleEl.checked = showRomanization;

function setStatus(message) {
  statusEl.textContent = message;
}

function isSpotifyPermissionError(message = "") {
  return (
    message.includes("Allow LumaLyrics") ||
    message.includes("Not authorized to send Apple events") ||
    message.includes("-1743")
  );
}

function setPermissionHelper(message = "") {
  permissionEl.hidden = !isSpotifyPermissionError(message);
}

function setChecklistItem(element, isComplete) {
  element.classList.toggle("is-complete", Boolean(isComplete));
}

function renderSetupChecklist(status = {}) {
  const isReady = Boolean(status.is_ready);
  setupEl.hidden = isReady;
  setChecklistItem(setupOpenEl, status.spotify_running);
  setChecklistItem(setupPermissionEl, status.automation_allowed);
  setChecklistItem(setupPlayEl, status.has_playback);
}

function renderReadySetupFromTrack(track) {
  if (!track || isAdTrack(track)) return;
  renderSetupChecklist({
    spotify_running: true,
    automation_allowed: true,
    has_playback: true,
    is_ready: true,
  });
}

function renderSetupFromError(message = "") {
  if (isSpotifyPermissionError(message)) {
    renderSetupChecklist({
      spotify_running: true,
      automation_allowed: false,
      has_playback: false,
      is_ready: false,
    });
  }
}

function setTranslationLabel(message) {
  translationEl.textContent = message || "-";
}

function setSourceLabel(message) {
  const shouldShow = Boolean(message && message !== "LRCLIB synced");
  sourceEl.textContent = message || "";
  sourceEl.hidden = !shouldShow;
}

function setFixActionVisible(isVisible) {
  reloadEl.hidden = !isVisible;
}

function providerLabel(provider, status) {
  if (status === "translation_not_required") return "Not required";
  if (provider === "deepl") return "DeepL";
  if (provider === "mymemory") return "MyMemory";
  return provider || "-";
}

function setCreditLink(linkEl, fallbackEl, url, text) {
  if (url) {
    linkEl.href = url;
    linkEl.textContent = text;
    linkEl.hidden = false;
    fallbackEl.hidden = true;
    return;
  }

  linkEl.href = "#";
  linkEl.hidden = true;
  fallbackEl.textContent = text;
  fallbackEl.hidden = false;
}

function setActionLink(linkEl, url, text) {
  linkEl.href = url || "#";
  linkEl.textContent = text;
  linkEl.hidden = !url;
}

function playbackCreditLabel(track) {
  if (track?.playback_source === "spotify-local") return "Open Spotify";
  if (track?.source_url) return "Open track source";
  return "Spotify";
}

function setQualityLabels(labels = []) {
  qualityEl.innerHTML = "";
  for (const label of labels.filter(Boolean)) {
    const chip = document.createElement("span");
    chip.textContent = label;
    qualityEl.appendChild(chip);
  }
}

function renderRecentSongs(songs = []) {
  recentSongsEl.innerHTML = "";
  if (songs.length === 0) {
    const empty = document.createElement("span");
    empty.className = "widget-recent-empty";
    empty.textContent = "Translated songs will appear here.";
    recentSongsEl.appendChild(empty);
    return;
  }

  for (const song of songs) {
    const button = document.createElement("button");
    button.className = "widget-recent-song";
    button.type = "button";
    button.dataset.trackId = song.id;
    button.innerHTML = `
      <span>
        <strong></strong>
        <em></em>
      </span>
      <b>Play</b>
    `;
    button.querySelector("strong").textContent = song.title || "Unknown song";
    button.querySelector("em").textContent = song.artist || "Unknown artist";
    recentSongsEl.appendChild(button);
  }
}

function setCredits({ track = null, info = null, lyricsSource = "", translationProvider = "", translationStatus = "" } = {}) {
  const title = isAdTrack(track) ? "Advertisement" : track?.title || "-";
  const artist = isAdTrack(track) ? "Spotify" : track?.artist || "-";
  const lyricsLabel = lyricsSource || info?.source || "-";

  creditSongEl.textContent = title;
  creditArtistEl.textContent = artist;
  setCreditLink(creditPlaybackEl, creditPlaybackTextEl, track?.source_url, playbackCreditLabel(track));
  setCreditLink(creditLyricsEl, creditLyricsTextEl, info?.source_url, lyricsLabel);
  setActionLink(openSongEl, track?.source_url, playbackCreditLabel(track));
  setActionLink(openSourceEl, info?.source_url, `Open ${lyricsLabel}`);
  creditTranslationEl.textContent = providerLabel(translationProvider, translationStatus);
}

function qualityLabelsFor(data) {
  return [
    data?.synced_lyrics?.length > 0 ? "Synced lyrics" : "Estimated timing",
    data?.translation_cache_hit ? "Cached translation" : "",
    data?.reused_repeated_lines ? "Repeated chorus reused" : "",
  ];
}

function setEmptyState(isEmpty) {
  emptyEl.hidden = !isEmpty;
  lyricsEl.hidden = isEmpty;
  if (isEmpty) {
    setTranslationLabel("");
    setSourceLabel("");
    setFixActionVisible(false);
    syncEl.textContent = "-";
    progressFillEl.style.width = "0%";
    setProgressTimeLabels(0, 0);
  }
}

function setPlayToggleState(track) {
  const canControl = track?.playback_source === "spotify-local" && !isAdTrack(track);
  playToggleEl.disabled = !canControl;
  playToggleEl.textContent = track?.is_playing ? "⏸" : "▶";
  playToggleEl.setAttribute(
    "aria-label",
    track?.is_playing ? "Pause Spotify playback" : "Play Spotify playback",
  );
}

function setPreparing(isPreparing) {
  const artUrl = artEl.currentSrc || artEl.src || "";
  if (artUrl) {
    preparingArtEl.src = artUrl;
    preparingArtEl.hidden = false;
  } else {
    preparingArtEl.src = "";
    preparingArtEl.hidden = true;
  }
  preparingEl.hidden = !isPreparing;
}

function setShowRomanization(value) {
  showRomanization = value;
  localStorage.setItem("lyric-widget-romanization", value ? "on" : "off");
  renderLyricAt(activeLyricIndex);
}

function getTrackId(track) {
  return track?.id || `${track?.artist || ""}-${track?.title || ""}`;
}

function isAdTrack(track) {
  return Boolean(track?.is_ad);
}

function setAlbumBackground(url) {
  if (url) {
    document.body.style.setProperty("--album-background", `url(${JSON.stringify(url)})`);
    document.body.classList.add("has-album-background");
    return;
  }

  document.body.style.removeProperty("--album-background");
  document.body.classList.remove("has-album-background");
}

function isSectionHeader(line) {
  return /^\[.+\]$/.test(line || "");
}

function getDisplayPairs(pairs) {
  return pairs.filter((pair) => !isSectionHeader(pair.original));
}

function renderTrack(track) {
  lastRenderedTrack = track || null;
  setPermissionHelper("");
  titleEl.textContent = isAdTrack(track) ? "Advertisement" : track?.title || "Open Spotify";
  artistEl.textContent = isAdTrack(track) ? "Spotify" : track?.artist || "Waiting for playback";
  artEl.src = isAdTrack(track) ? "" : track?.album_art || "";
  setAlbumBackground(isAdTrack(track) ? "" : track?.album_art);
  setPlayToggleState(track);
  setCredits({ track });
  renderReadySetupFromTrack(track);
}

function clearLyrics() {
  lyricPairs = [];
  syncedTimings = [];
  playbackSnapshot = null;
  lastRenderedTrack = null;
  activeLyricIndex = 0;
  originalEl.textContent = "-";
  romanizedEl.textContent = "";
  romanizedEl.hidden = true;
  translatedEl.textContent = "-";
  prevEl.textContent = "";
  nextEl.textContent = "";
  setTranslationLabel("");
  setSourceLabel("");
  setFixActionVisible(false);
  setPlayToggleState(null);
  setCredits();
  setQualityLabels([]);
  updateProgressBar();
}

function renderEmptyState(message = "Ready") {
  renderTrack(null);
  clearLyrics();
  lastTrackId = "";
  setStatus(message);
  setEmptyState(true);
}

function renderAdState(track) {
  renderTrack(track);
  clearLyrics();
  setEmptyState(false);
  lastTrackId = getTrackId(track);
  setStatus("Ad playing");
  syncEl.textContent = "Paused";
}

function setPlaybackSnapshot(track) {
  if (
    track?.playback_source === "spotify-local" &&
    Number.isFinite(Number(track.progress_seconds))
  ) {
    playbackSnapshot = {
      trackId: getTrackId(track),
      progressMs: Number(track.progress_seconds) * 1000,
      durationMs: Number.isFinite(Number(track.duration_seconds))
        ? Number(track.duration_seconds) * 1000
        : null,
      receivedAt: Date.now(),
      isPlaying: Boolean(track.is_playing),
    };
  } else {
    playbackSnapshot = null;
  }
}

function getLiveElapsedMs() {
  if (!playbackSnapshot) return null;

  const driftMs = playbackSnapshot.isPlaying ? Date.now() - playbackSnapshot.receivedAt : 0;
  return Math.max(0, playbackSnapshot.progressMs + driftMs);
}

function formatTime(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return "0:00";

  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function setProgressTimeLabels(elapsedMs = 0, durationMs = 0) {
  elapsedTimeEl.textContent = formatTime(elapsedMs);
  durationTimeEl.textContent = formatTime(durationMs);
}

function updateProgressBar() {
  const elapsedMs = getLiveElapsedMs();
  const durationMs = playbackSnapshot?.durationMs || 0;
  const boundedElapsedMs = elapsedMs !== null
    ? Math.min(elapsedMs, durationMs || elapsedMs)
    : 0;
  const percent = elapsedMs !== null && durationMs ? Math.min(100, (elapsedMs / durationMs) * 100) : 0;
  progressFillEl.style.width = `${percent}%`;
  setProgressTimeLabels(boundedElapsedMs, durationMs);
}

function getEstimatedDurationMs() {
  return playbackSnapshot?.durationMs || 210000;
}

function getTimedIndex(elapsedMs) {
  if (syncedTimings.length === 0) {
    const pairs = getDisplayPairs(lyricPairs);
    if (pairs.length === 0) return 0;
    const progress = Math.min(1, elapsedMs / getEstimatedDurationMs());
    return Math.min(pairs.length - 1, Math.floor(progress * pairs.length));
  }

  const elapsedSeconds = elapsedMs / 1000;
  let activeIndex = 0;
  for (let index = 0; index < syncedTimings.length; index += 1) {
    if (syncedTimings[index].time > elapsedSeconds) {
      break;
    }
    activeIndex = index;
  }
  return activeIndex;
}

function getEstimatedIndex(pairs) {
  if (pairs.length === 0) return 0;
  const elapsedMs = Date.now() - estimatedStartedAt;
  const durationMs = getEstimatedDurationMs();
  const progress = Math.min(1, elapsedMs / durationMs);
  return Math.min(pairs.length - 1, Math.floor(progress * pairs.length));
}

function renderLyricAt(index) {
  const pairs = getDisplayPairs(lyricPairs);
  if (pairs.length === 0) {
    originalEl.textContent = "-";
    romanizedEl.textContent = "";
    romanizedEl.hidden = true;
    translatedEl.textContent = "-";
    prevEl.textContent = "";
    nextEl.textContent = "";
    return;
  }

  const boundedIndex = Math.max(0, Math.min(pairs.length - 1, index));
  activeLyricIndex = boundedIndex;
  const current = pairs[boundedIndex];
  const previous = pairs[boundedIndex - 1];
  const next = pairs[boundedIndex + 1];

  originalEl.textContent = current.original || "-";
  romanizedEl.textContent = current.romanized || "";
  romanizedEl.hidden = !showRomanization || !current.romanized;
  translatedEl.textContent = current.translated || "-";
  prevEl.textContent = previous?.original || "";
  nextEl.textContent = next?.original || "";
}

function updateCurrentLyric() {
  const displayPairs = getDisplayPairs(lyricPairs);
  const liveElapsed = getLiveElapsedMs();

  if (liveElapsed !== null) {
    renderLyricAt(getTimedIndex(liveElapsed));
    if (!playbackSnapshot?.isPlaying) {
      syncEl.textContent = "Paused";
    } else {
      syncEl.textContent = syncedTimings.length > 0 ? "Spotify synced" : "Spotify estimated";
    }
    updateProgressBar();
    return;
  }

  const estimatedElapsedMs = Date.now() - estimatedStartedAt;
  renderLyricAt(getEstimatedIndex(displayPairs));
  syncEl.textContent = syncedTimings.length > 0 ? "LRCLIB timing" : "Estimated";
  updateProgressBar();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "Request failed.");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function togglePlayback() {
  if (playToggleEl.disabled) return;

  playToggleEl.disabled = true;
  try {
    const track = await fetchJson("/playback-toggle", { method: "POST" });
    const trackId = getTrackId(track);
    renderTrack(track);
    setPlaybackSnapshot(track);

    if (isAdTrack(track)) {
      renderAdState(track);
      return;
    }

    if (lastTrackId && trackId !== lastTrackId) {
      await loadLyrics();
      return;
    }

    updateCurrentLyric();
  } catch (error) {
    setPermissionHelper(error.message);
    setStatus(error.message);
  } finally {
    setPlayToggleState(lastRenderedTrack);
  }
}

async function loadRecentSongs() {
  try {
    const data = await fetchJson("/recent-songs?limit=6");
    renderRecentSongs(data.songs || []);
  } catch {
    renderRecentSongs([]);
  }
}

async function refreshSetupStatus() {
  try {
    const status = await fetchJson("/setup-status");
    renderSetupChecklist(status);
  } catch {
    setupEl.hidden = true;
  }
}

async function openSpotify() {
  try {
    const result = await fetchJson("/open-spotify", { method: "POST" });
    setStatus(result.opened ? "Opening Spotify" : "Spotify is already open");
    setTimeout(refreshSetupStatus, 900);
    setTimeout(refreshPlayback, 1400);
  } catch (error) {
    setStatus(error.message);
  }
}

async function playRecentSong(trackId) {
  if (!trackId) return;
  try {
    setStatus("Opening song");
    moreMenuEl.removeAttribute("open");
    await fetchJson("/recent-songs/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_id: trackId }),
    });
    setTimeout(refreshPlayback, 700);
  } catch (error) {
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    setStatus(error.message);
  }
}

async function loadLyrics(force = false) {
  if (isLoading) return;

  isLoading = true;
  reloadEl.disabled = true;
  setStatus(force ? "Fixing" : "Loading");
  setPreparing(true);
  try {
    const lang = encodeURIComponent(languageEl.value);
    const forceParam = force ? "&force=1" : "";
    const data = await fetchJson(`/translated-lyrics?lang=${lang}&auto_pause=1${forceParam}`);
    if (isAdTrack(data.track)) {
      renderAdState(data.track);
      return;
    }
    setEmptyState(false);

    lastTrackId = getTrackId(data.track);
    lyricPairs = data.lyrics || [];
    syncedTimings = (data.synced_lyrics || [])
      .filter((line) => Number.isFinite(line.time) && line.text)
      .sort((a, b) => a.time - b.time);
    estimatedStartedAt = Date.now();

    renderTrack(data.track);
    setPlaybackSnapshot(data.track);
    updateCurrentLyric();
    setTranslationLabel(data.translation_label);
    setSourceLabel(data.lyrics_source_label || data.lyric_source);
    setCredits({
      track: data.track,
      info: data.info,
      lyricsSource: data.lyrics_source_label || data.lyric_source,
      translationProvider: data.translation_provider,
      translationStatus: data.translation_status,
    });
    setQualityLabels(qualityLabelsFor(data));
    loadRecentSongs();
    setFixActionVisible(lyricPairs.length > 0);
    setStatus(data.paused_for_translation ? "Prepared" : data.language);
  } catch (error) {
    if (error.status === 409) {
      clearLyrics();
      setEmptyState(false);
    } else if (error.status === 404) {
      renderEmptyState("Waiting");
      return;
    }
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    refreshSetupStatus();
    setStatus(error.message);
  } finally {
    isLoading = false;
    reloadEl.disabled = false;
    setPreparing(false);
  }
}

async function refreshPlayback() {
  if (isLoading) return;

  try {
    const track = await fetchJson("/playback-sync");
    const trackId = getTrackId(track);
    renderTrack(track);
    setPlaybackSnapshot(track);

    if (isAdTrack(track)) {
      renderAdState(track);
      return;
    }

    if (!lastTrackId || trackId !== lastTrackId) {
      await loadLyrics();
      return;
    }

    updateCurrentLyric();
  } catch (error) {
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    playbackSnapshot = null;
    updateCurrentLyric();

    if (!lastTrackId) {
      await loadLyrics();
    }
  }
}

languageEl.addEventListener("change", () => {
  loadLyrics();
});

romanizationToggleEl.addEventListener("change", () => {
  setShowRomanization(romanizationToggleEl.checked);
});

reloadEl.addEventListener("click", () => {
  reloadEl.closest("details")?.removeAttribute("open");
  loadLyrics(true);
});

playToggleEl.addEventListener("click", togglePlayback);
openSpotifyEls.forEach((element) => {
  element.addEventListener("click", (event) => {
    event.preventDefault();
    openSpotify();
  });
});
moreMenuEl.addEventListener("toggle", () => {
  if (moreMenuEl.open) loadRecentSongs();
});
recentSongsEl.addEventListener("click", (event) => {
  const button = event.target.closest(".widget-recent-song");
  if (button) playRecentSong(button.dataset.trackId);
});

loadLyrics();
loadRecentSongs();
refreshSetupStatus();
setInterval(refreshPlayback, 1000);
setInterval(updateCurrentLyric, 250);
setInterval(refreshSetupStatus, 5000);
