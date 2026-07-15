const statusEl = document.querySelector("#status");
const titleEl = document.querySelector("#song-title");
const artistEl = document.querySelector("#artist-name");
const albumArtEl = document.querySelector("#album-art");
const emptyStateEl = document.querySelector("#empty-state");
const originalLyricsEl = document.querySelector("#original-lyrics");
const translatedLyricsEl = document.querySelector("#translated-lyrics");
const languageEl = document.querySelector("#language");
const songInfoEl = document.querySelector("#song-info");
const songAboutEl = document.querySelector("#song-about");
const songSourceEl = document.querySelector("#song-source");
const karaokeControlsEl = document.querySelector("#karaoke-controls");
const lyricsGridEl = document.querySelector("#lyrics-grid");
const karaokeToggleEl = document.querySelector("#karaoke-toggle");
const karaokeDurationEl = document.querySelector("#karaoke-duration");
const karaokeProgressEl = document.querySelector("#karaoke-progress");
const songElapsedEl = document.querySelector("#song-elapsed");
const songDurationEl = document.querySelector("#song-duration");
const karaokeResetEl = document.querySelector("#karaoke-reset");
const karaokeSourceEl = document.querySelector("#karaoke-source");
const lyricsSourceEl = document.querySelector("#lyrics-source");
const translationLabelEl = document.querySelector("#translation-label");
const preparingEl = document.querySelector("#preparing-overlay");
const preparingArtEl = document.querySelector("#preparing-art");
const fixSongEl = document.querySelector("#fix-song");
const playToggleEl = document.querySelector("#play-toggle");
const moreMenuEl = document.querySelector("#player-more-menu");
const permissionEl = document.querySelector("#permission-helper");
const setupEl = document.querySelector("#setup-helper");
const setupOpenEl = document.querySelector("#setup-open");
const setupPermissionEl = document.querySelector("#setup-permission");
const setupPlayEl = document.querySelector("#setup-play");
const creditSongEl = document.querySelector("#credit-song");
const creditArtistEl = document.querySelector("#credit-artist");
const creditPlaybackEl = document.querySelector("#credit-playback");
const creditPlaybackTextEl = document.querySelector("#credit-playback-text");
const creditLyricsEl = document.querySelector("#credit-lyrics");
const creditLyricsTextEl = document.querySelector("#credit-lyrics-text");
const creditTranslationEl = document.querySelector("#credit-translation");
const qualityEl = document.querySelector("#quality-labels");
const openSongEl = document.querySelector("#open-song");
const openSourceEl = document.querySelector("#open-source");
const recentSongsEl = document.querySelector("#recent-songs");

let lastTrackId = "";
let lastLanguage = "";
let isLoading = false;
let lyricLineCount = 0;
let karaokeTimer = null;
let karaokeStartedAt = 0;
let karaokePausedAt = 0;
let activeKaraokeIndex = -1;
let karaokeTimings = [];
let playbackSnapshot = null;
let lastRenderedTrack = null;

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

function setTranslationLabel(label) {
  translationLabelEl.textContent = label || "";
  translationLabelEl.hidden = !label;
}

function setLyricsSourceLabel(label) {
  const shouldShow = Boolean(label && label !== "LRCLIB synced");
  lyricsSourceEl.textContent = label || "";
  lyricsSourceEl.hidden = !shouldShow;
}

function setFixActionVisible(isVisible) {
  fixSongEl.hidden = !isVisible;
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
    empty.className = "recent-empty";
    empty.textContent = "Translated songs will appear here.";
    recentSongsEl.appendChild(empty);
    return;
  }

  for (const song of songs) {
    const button = document.createElement("button");
    button.className = "recent-song";
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
  emptyStateEl.hidden = !isEmpty;
  karaokeControlsEl.hidden = isEmpty;
  lyricsGridEl.hidden = isEmpty;
  if (isEmpty) {
    songInfoEl.hidden = true;
    setTranslationLabel("");
    setLyricsSourceLabel("");
    setFixActionVisible(false);
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
  const artUrl = albumArtEl.currentSrc || albumArtEl.src || "";
  if (artUrl) {
    preparingArtEl.src = artUrl;
    preparingArtEl.hidden = false;
  } else {
    preparingArtEl.src = "";
    preparingArtEl.hidden = true;
  }
  preparingEl.hidden = !isPreparing;
}

function parseSectionHeader(line) {
  const match = line?.match(/^\[(.+?)\]$/);
  if (!match) return null;

  const [label, performers] = match[1].split(/:\s(.+)/);
  return {
    label: label.trim(),
    performers: performers ? performers.trim() : "",
  };
}

function createSectionHeader(line) {
  const section = parseSectionHeader(line);
  const node = document.createElement("div");
  node.className = "lyric-section";

  const label = document.createElement("span");
  label.className = "section-label";
  label.textContent = section.label;
  node.appendChild(label);

  if (section.performers) {
    const performers = document.createElement("span");
    performers.className = "section-performers";
    performers.textContent = section.performers;
    node.appendChild(performers);
  }

  return node;
}

function renderLines(container, lines) {
  container.innerHTML = "";
  let lyricIndex = 0;
  for (const line of lines) {
    if (parseSectionHeader(line)) {
      container.appendChild(createSectionHeader(line));
      continue;
    }

    const node = document.createElement("div");
    node.className = "lyric-line";
    node.dataset.karaokeIndex = lyricIndex;
    if (lyricIndex === activeKaraokeIndex) {
      node.classList.add("is-active-lyric");
    }
    node.textContent = line || " ";
    container.appendChild(node);
    lyricIndex += 1;
  }
}

function renderOriginalLines(container, pairs) {
  container.innerHTML = "";
  let lyricIndex = 0;
  for (const pair of pairs) {
    const line = pair.original || "";
    if (parseSectionHeader(line)) {
      container.appendChild(createSectionHeader(line));
      continue;
    }

    const node = document.createElement("div");
    node.className = "lyric-line";
    node.dataset.karaokeIndex = lyricIndex;
    if (lyricIndex === activeKaraokeIndex) {
      node.classList.add("is-active-lyric");
    }

    const original = document.createElement("span");
    original.textContent = line || " ";
    node.appendChild(original);

    if (pair.romanized) {
      const romanized = document.createElement("span");
      romanized.className = "romanized-line";
      romanized.textContent = pair.romanized;
      node.appendChild(romanized);
    }

    container.appendChild(node);
    lyricIndex += 1;
  }
}

function countLyricLines(lines) {
  return lines.filter((line) => !parseSectionHeader(line)).length;
}

function getKaraokeDurationMs() {
  const seconds = Number(karaokeDurationEl.value) || 210;
  return Math.max(30, Math.min(600, seconds)) * 1000;
}

function hasSyncedTimings() {
  return karaokeTimings.length > 0;
}

function getTrackId(track) {
  return track.id || `${track.artist}-${track.title}`;
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

function clearLyrics() {
  originalLyricsEl.innerHTML = "";
  translatedLyricsEl.innerHTML = "";
  songInfoEl.hidden = true;
  lyricLineCount = 0;
  karaokeTimings = [];
  playbackSnapshot = null;
  lastRenderedTrack = null;
  activeKaraokeIndex = -1;
  setTranslationLabel("");
  setLyricsSourceLabel("");
  setFixActionVisible(false);
  setPlayToggleState(null);
  setCredits();
  setQualityLabels([]);
  clearKaraokeHighlight();
  updateKaraokeProgress(0);
  renderKaraokeMode();
}

function renderEmptyState(message = "Ready.") {
  renderTrack(null);
  clearLyrics();
  lastTrackId = "";
  lastLanguage = languageEl.value;
  setStatus(message);
  setEmptyState(true);
}

function renderAdState(track) {
  renderTrack(track);
  clearLyrics();
  setEmptyState(false);
  lastTrackId = getTrackId(track);
  lastLanguage = languageEl.value;
  setStatus("Spotify is playing an ad. Lyrics will resume after the next song.");
  setTranslationLabel("");
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

  renderKaraokeMode();
  updatePlaybackProgressFromSnapshot();
}

function hasLivePlaybackSync() {
  return Boolean(playbackSnapshot && hasSyncedTimings());
}

function hasSpotifyPlaybackSync() {
  return Boolean(playbackSnapshot);
}

function getLivePlaybackElapsedMs() {
  if (!hasSpotifyPlaybackSync()) return null;

  const driftMs = playbackSnapshot.isPlaying ? Date.now() - playbackSnapshot.receivedAt : 0;
  return Math.max(0, playbackSnapshot.progressMs + driftMs);
}

function getKaraokeTotalMs() {
  if (!hasSyncedTimings()) {
    return playbackSnapshot?.durationMs || getKaraokeDurationMs();
  }

  const lastTimedLine = karaokeTimings[karaokeTimings.length - 1];
  return Math.max(30000, (lastTimedLine.time + 4) * 1000);
}

function updatePlaybackProgressFromSnapshot() {
  const elapsedMs = getLivePlaybackElapsedMs();
  if (elapsedMs === null) {
    updateKaraokeProgress(0, 0, lyricLineCount > 0 ? getKaraokeTotalMs() : 0);
    return;
  }

  const durationMs = getKaraokeTotalMs();
  updateKaraokeProgress(Math.min(1, elapsedMs / durationMs), elapsedMs, durationMs);
}

function formatTime(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return "0:00";

  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function setSongTimeLabels(elapsedMs = 0, durationMs = 0) {
  songElapsedEl.textContent = formatTime(elapsedMs);
  songDurationEl.textContent = formatTime(durationMs);
}

function getTimedLineIndex(elapsedMs) {
  if (!hasSyncedTimings()) {
    const progressRatio = Math.min(1, elapsedMs / getKaraokeTotalMs());
    return Math.min(
      lyricLineCount - 1,
      Math.floor(progressRatio * lyricLineCount),
    );
  }

  const elapsedSeconds = elapsedMs / 1000;
  let lineIndex = 0;
  for (let index = 0; index < karaokeTimings.length; index += 1) {
    if (karaokeTimings[index].time > elapsedSeconds) {
      break;
    }
    lineIndex = index;
  }
  return Math.min(lyricLineCount - 1, lineIndex);
}

function clearKaraokeHighlight() {
  document.querySelectorAll(".is-active-lyric").forEach((node) => {
    node.classList.remove("is-active-lyric");
  });
}

function setActiveKaraokeLine(index) {
  if (index !== activeKaraokeIndex) {
    clearKaraokeHighlight();
    activeKaraokeIndex = index;

    const activeLines = document.querySelectorAll(`[data-karaoke-index="${index}"]`);
    activeLines.forEach((node) => node.classList.add("is-active-lyric"));

    const firstActiveLine = activeLines[0];
    if (firstActiveLine) {
      firstActiveLine.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

function updateKaraokeProgress(progressRatio, elapsedMs = null, durationMs = null) {
  const boundedRatio = Math.max(0, Math.min(1, progressRatio || 0));
  const resolvedDurationMs = Number.isFinite(durationMs)
    ? durationMs
    : lyricLineCount > 0 || hasSpotifyPlaybackSync()
    ? getKaraokeTotalMs()
    : 0;
  const resolvedElapsedMs = Number.isFinite(elapsedMs)
    ? elapsedMs
    : boundedRatio * resolvedDurationMs;

  karaokeProgressEl.value = Math.round(boundedRatio * 1000);
  setSongTimeLabels(
    Math.min(Math.max(0, resolvedElapsedMs), resolvedDurationMs || resolvedElapsedMs),
    resolvedDurationMs,
  );
}

function stopKaraokeTimer() {
  if (karaokeTimer) {
    clearInterval(karaokeTimer);
    karaokeTimer = null;
  }
}

function resetKaraoke() {
  stopKaraokeTimer();
  const liveElapsed = getLivePlaybackElapsedMs();
  karaokePausedAt = liveElapsed || 0;
  karaokeStartedAt = Date.now() - karaokePausedAt;
  activeKaraokeIndex = -1;
  updateKaraokeProgress(0);
  clearKaraokeHighlight();

  if (karaokeToggleEl.checked && lyricLineCount > 0) {
    startKaraoke();
  }
}

function tickKaraoke() {
  if (!karaokeToggleEl.checked || lyricLineCount === 0) return;

  const liveElapsed = getLivePlaybackElapsedMs();
  const elapsed = liveElapsed ?? Date.now() - karaokeStartedAt;
  const duration = getKaraokeTotalMs();
  const progressRatio = Math.min(1, elapsed / duration);
  const lineIndex = getTimedLineIndex(elapsed);

  updateKaraokeProgress(progressRatio, elapsed, duration);
  setActiveKaraokeLine(lineIndex);

  if (progressRatio >= 1 && !hasSpotifyPlaybackSync()) {
    stopKaraokeTimer();
  }
}

function startKaraoke() {
  if (lyricLineCount === 0) return;

  stopKaraokeTimer();
  karaokeStartedAt = Date.now() - karaokePausedAt;
  karaokeTimer = setInterval(tickKaraoke, 300);
  tickKaraoke();
}

function pauseKaraoke() {
  karaokePausedAt = getLivePlaybackElapsedMs() ?? Date.now() - karaokeStartedAt;
  stopKaraokeTimer();
}

function syncKaraokeFromSlider() {
  if (hasSpotifyPlaybackSync()) {
    setStatus("Spotify desktop is controlling synced lyric position.");
    tickKaraoke();
    return;
  }

  const ratio = Number(karaokeProgressEl.value) / 1000;
  karaokePausedAt = ratio * getKaraokeTotalMs();
  karaokeStartedAt = Date.now() - karaokePausedAt;
  activeKaraokeIndex = -1;
  tickKaraoke();
}

function renderKaraokeMode() {
  const isSynced = hasSyncedTimings();
  karaokeDurationEl.disabled = isSynced || hasSpotifyPlaybackSync();
  if (hasLivePlaybackSync()) {
    karaokeSourceEl.textContent = "Spotify + LRCLIB sync";
  } else if (hasSpotifyPlaybackSync()) {
    karaokeSourceEl.textContent = "Spotify estimated timing";
  } else {
    karaokeSourceEl.textContent = isSynced ? "LRCLIB synced timing" : "Estimated timing";
  }
}

function prepareKaraoke(lines, timings = []) {
  lyricLineCount = countLyricLines(lines);
  karaokeTimings = timings
    .filter((line) => Number.isFinite(line.time) && line.text)
    .sort((a, b) => a.time - b.time);
  activeKaraokeIndex = -1;
  clearKaraokeHighlight();
  updateKaraokeProgress(0);
  renderKaraokeMode();

  if (karaokeToggleEl.checked) {
    resetKaraoke();
  }
}

function renderTrack(track) {
  lastRenderedTrack = track || null;
  setPermissionHelper("");
  titleEl.textContent = isAdTrack(track) ? "Advertisement" : track?.title || "Start Spotify to begin";
  artistEl.textContent = isAdTrack(track) ? "Spotify" : track?.artist || "Waiting for a track...";
  albumArtEl.src = isAdTrack(track) ? "" : track?.album_art || "";
  setAlbumBackground(isAdTrack(track) ? "" : track?.album_art);
  setPlayToggleState(track);
  setPlaybackSnapshot(track);
  setCredits({ track });
  renderReadySetupFromTrack(track);
}

function renderSongInfo(info) {
  const about = info?.about || "";
  songInfoEl.hidden = !about;
  songAboutEl.textContent = about;
  songSourceEl.href = info?.source_url || "#";
  songSourceEl.textContent = info?.source ? `Open ${info.source}` : "Open source";
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

    if (isAdTrack(track)) {
      renderAdState(track);
      return;
    }

    if (lastTrackId && trackId !== lastTrackId) {
      await loadTranslatedLyrics();
      return;
    }

    if (karaokeToggleEl.checked) {
      tickKaraoke();
    }
  } catch (error) {
    setPermissionHelper(error.message);
    setStatus(error.message);
  } finally {
    setPlayToggleState(lastRenderedTrack);
  }
}

async function loadRecentSongs() {
  try {
    const data = await fetchJson("/recent-songs?limit=8");
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

async function playRecentSong(trackId) {
  if (!trackId) return;
  try {
    setStatus("Opening song in Spotify...");
    moreMenuEl.removeAttribute("open");
    await fetchJson("/recent-songs/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track_id: trackId }),
    });
    setTimeout(refreshPlaybackSync, 700);
  } catch (error) {
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    setStatus(error.message);
  }
}

async function loadTranslatedLyrics(force = false) {
  if (isLoading) return;
  isLoading = true;
  fixSongEl.disabled = true;
  document.body.classList.add("loading");
  setStatus(force ? "Reloading lyrics for this song..." : "Preparing lyrics...");
  setPreparing(true);

  try {
    const lang = encodeURIComponent(languageEl.value);
    const forceParam = force ? "&force=1" : "";
    const data = await fetchJson(`/translated-lyrics?lang=${lang}&auto_pause=1${forceParam}`);
    setEmptyState(false);
    lastTrackId = getTrackId(data.track);
    lastLanguage = languageEl.value;
    renderTrack(data.track);
    renderSongInfo(data.info);
    setCredits({
      track: data.track,
      info: data.info,
      lyricsSource: data.lyrics_source_label || data.lyric_source,
      translationProvider: data.translation_provider,
      translationStatus: data.translation_status,
    });
    setQualityLabels(qualityLabelsFor(data));
    loadRecentSongs();
    renderOriginalLines(originalLyricsEl, data.lyrics);
    renderLines(translatedLyricsEl, data.lyrics.map((line) => line.translated));
    setTranslationLabel(data.translation_label);
    prepareKaraoke(
      data.lyrics.map((line) => line.original),
      data.synced_lyrics || [],
    );
    const timingLabel = hasLivePlaybackSync()
      ? " Spotify and LRCLIB sync are ready."
      : hasSpotifyPlaybackSync()
      ? " Spotify playback sync is ready."
      : hasSyncedTimings()
      ? " LRCLIB synced timing is ready."
      : " Using estimated karaoke timing.";
    const pauseLabel = data.paused_for_translation ? " Playback was paused while preparing." : "";
    setLyricsSourceLabel(data.lyrics_source_label || data.lyric_source);
    setFixActionVisible((data.lyrics || []).length > 0);
    setStatus(`Translated to ${data.language}.${pauseLabel}${timingLabel}`);
  } catch (error) {
    if (error.status === 409) {
      clearLyrics();
      setEmptyState(false);
    } else if (error.status === 404) {
      renderEmptyState("Waiting for Spotify playback.");
      return;
    }
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    refreshSetupStatus();
    setStatus(error.message);
  } finally {
    isLoading = false;
    fixSongEl.disabled = false;
    setPreparing(false);
    document.body.classList.remove("loading");
  }
}

async function checkForSongChange(force = false, clearCaches = false) {
  if (isLoading) return;

  try {
    const track = await fetchJson("/current-song");
    const trackId = getTrackId(track);
    const languageChanged = languageEl.value !== lastLanguage;

    renderTrack(track);

    if (isAdTrack(track)) {
      renderAdState(track);
      return;
    }
    setEmptyState(false);

    if (force || trackId !== lastTrackId || languageChanged) {
      await loadTranslatedLyrics(clearCaches);
      return;
    }

    setStatus("Lyrics are up to date.");
  } catch (error) {
    if (error.status === 404) {
      renderEmptyState("Waiting for Spotify playback.");
      return;
    }
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    setStatus(error.message);
  }
}

async function refreshPlaybackSync() {
  if (isLoading) return;

  try {
    const track = await fetchJson("/playback-sync");
    const trackId = getTrackId(track);
    renderTrack(track);

    if (isAdTrack(track)) {
      renderAdState(track);
      return;
    }

    if (lastTrackId && trackId !== lastTrackId) {
      await loadTranslatedLyrics();
      return;
    }

    if (karaokeToggleEl.checked) {
      tickKaraoke();
    }
  } catch (error) {
    setPermissionHelper(error.message);
    renderSetupFromError(error.message);
    playbackSnapshot = null;
    renderKaraokeMode();
  }
}

languageEl.addEventListener("change", () => {
  checkForSongChange(true);
});

karaokeToggleEl.addEventListener("change", () => {
  if (karaokeToggleEl.checked) {
    startKaraoke();
  } else {
    pauseKaraoke();
  }
});

karaokeResetEl.addEventListener("click", resetKaraoke);
karaokeDurationEl.addEventListener("change", resetKaraoke);
karaokeProgressEl.addEventListener("input", syncKaraokeFromSlider);
fixSongEl.addEventListener("click", () => {
  fixSongEl.closest("details")?.removeAttribute("open");
  checkForSongChange(true, true);
});
playToggleEl.addEventListener("click", togglePlayback);
moreMenuEl.addEventListener("toggle", () => {
  if (moreMenuEl.open) loadRecentSongs();
});
recentSongsEl.addEventListener("click", (event) => {
  const button = event.target.closest(".recent-song");
  if (button) playRecentSong(button.dataset.trackId);
});

checkForSongChange(true);
loadRecentSongs();
refreshSetupStatus();
setInterval(refreshPlaybackSync, 1500);
setInterval(() => checkForSongChange(false), 12000);
setInterval(refreshSetupStatus, 5000);
