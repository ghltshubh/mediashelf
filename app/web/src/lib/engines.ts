// Playback engines (M3). Only officially sanctioned engines exist here:
// YouTube IFrame API, Spotify Web Playback SDK, Spotify embed. DRM services
// can never reach this file — their only option is a deep link.

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    YT?: any;
    onYouTubeIframeAPIReady?: () => void;
    Spotify?: any;
    onSpotifyWebPlaybackSDKReady?: () => void;
    MusicKit?: any;
  }
}

export interface EngineCallbacks {
  onState: (s: "loading" | "playing" | "paused" | "ended") => void;
  onProgress: (position: number, duration: number) => void;
  onFail: (reason: string) => void;
}

function loadScript(src: string, id: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) return resolve();
    const s = document.createElement("script");
    s.src = src;
    s.id = id;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`failed to load ${src}`));
    document.head.appendChild(s);
  });
}

// ---------- YouTube IFrame API ----------

let ytReady: Promise<any> | null = null;

function ensureYouTube(): Promise<any> {
  if (!ytReady) {
    ytReady = new Promise((resolve, reject) => {
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      loadScript("https://www.youtube.com/iframe_api", "yt-iframe-api").catch(reject);
      // Already loaded earlier?
      if (window.YT?.Player) resolve(window.YT);
    });
  }
  return ytReady;
}

export class YouTubeEngine {
  private player: any = null;
  private timer: number | undefined;

  async load(containerId: string, videoId: string, cb: EngineCallbacks): Promise<void> {
    const YT = await ensureYouTube();
    cb.onState("loading");
    this.destroy();
    this.player = new YT.Player(containerId, {
      videoId,
      playerVars: { autoplay: 1, rel: 0, playsinline: 1 },
      events: {
        onReady: () => this.player?.playVideo?.(),
        onStateChange: (e: any) => {
          if (e.data === YT.PlayerState.PLAYING) cb.onState("playing");
          else if (e.data === YT.PlayerState.PAUSED) cb.onState("paused");
          else if (e.data === YT.PlayerState.ENDED) cb.onState("ended");
        },
        onError: (e: any) => {
          // 101/150 = embedding disabled → deep-link out (plan failure modes).
          const embedBlocked = e.data === 101 || e.data === 150;
          cb.onFail(embedBlocked ? "embed-blocked" : `youtube error ${e.data}`);
        },
      },
    });
    window.clearInterval(this.timer);
    this.timer = window.setInterval(() => {
      if (this.player?.getCurrentTime) {
        cb.onProgress(this.player.getCurrentTime() ?? 0, this.player.getDuration() ?? 0);
      }
    }, 1000);
  }

  toggle() {
    if (!this.player?.getPlayerState) return;
    const s = this.player.getPlayerState();
    if (s === window.YT?.PlayerState.PLAYING) this.player.pauseVideo();
    else this.player.playVideo();
  }

  seek(seconds: number) {
    this.player?.seekTo?.(seconds, true);
  }

  setVolume(v: number) {
    this.player?.setVolume?.(Math.round(v * 100));
  }

  setRate(r: number) {
    this.player?.setPlaybackRate?.(r);
  }

  destroy() {
    window.clearInterval(this.timer);
    this.player?.destroy?.();
    this.player = null;
  }
}

// ---------- HTML5 audio (podcasts, M8) ----------

// Remembered playback positions (podcast resume). Keyed by media URL, capped so
// the map can't grow unbounded; an entry clears when the episode finishes.
const POS_STORE = "mediashelf-audio-pos";

function loadPositions(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(POS_STORE) ?? "{}");
  } catch {
    return {};
  }
}

function savePosition(url: string, pos: number | null) {
  const all = loadPositions();
  if (pos == null) delete all[url];
  else all[url] = Math.floor(pos);
  const keys = Object.keys(all);
  if (keys.length > 50) delete all[keys[0]];
  try {
    localStorage.setItem(POS_STORE, JSON.stringify(all));
  } catch {
    /* storage full/blocked — resume is best-effort */
  }
}

// Streams an episode enclosure URL through a single <audio> element. No SDK,
// no visible DOM slot, no DRM — plain progressive audio. `ended` drives the
// player store's queue → next(), so an episode list auto-advances for free.
// Long episodes resume where you left off; speed is adjustable and sticky.
export class Html5AudioEngine {
  private audio: HTMLAudioElement | null = null;
  private rate = 1;
  private lastSaved = 0;

  async load(url: string, cb: EngineCallbacks): Promise<void> {
    cb.onState("loading");
    this.destroy();
    const audio = new Audio(url);
    this.audio = audio;
    this.lastSaved = 0;
    audio.playbackRate = this.rate;
    // Resume where the user left off (only meaningfully into the episode).
    const resume = loadPositions()[url];
    if (resume && resume > 10) {
      audio.addEventListener("loadedmetadata", () => {
        if (Number.isFinite(audio.duration) && resume < audio.duration - 10) {
          audio.currentTime = resume;
        }
      }, { once: true });
    }
    audio.addEventListener("playing", () => cb.onState("playing"));
    audio.addEventListener("pause", () => {
      if (!audio.ended) cb.onState("paused");
    });
    audio.addEventListener("ended", () => {
      savePosition(url, null); // finished — start fresh next time
      cb.onState("ended");
    });
    audio.addEventListener("timeupdate", () => {
      cb.onProgress(audio.currentTime, Number.isFinite(audio.duration) ? audio.duration : 0);
      if (Math.abs(audio.currentTime - this.lastSaved) > 5) {
        this.lastSaved = audio.currentTime;
        savePosition(url, audio.currentTime);
      }
    });
    audio.addEventListener("error", () => cb.onFail("audio failed to load"));
    try {
      await audio.play();
    } catch {
      cb.onFail("audio playback was blocked");
    }
  }

  toggle() {
    if (!this.audio) return;
    if (this.audio.paused) void this.audio.play();
    else this.audio.pause();
  }

  seek(seconds: number) {
    if (this.audio) this.audio.currentTime = seconds;
  }

  setVolume(v: number) {
    if (this.audio) this.audio.volume = v;  // already 0..1, no scaling
  }

  setRate(r: number) {
    this.rate = r;
    if (this.audio) this.audio.playbackRate = r;
  }

  destroy() {
    if (this.audio) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
      this.audio = null;
    }
  }
}

// ---------- Spotify Web Playback SDK ----------

export class SpotifySdkEngine {
  private player: any = null;
  private deviceId: string | null = null;
  private timer: number | undefined;
  private _wasPlaying = false;  // for track-end detection

  private async token(): Promise<string> {
    const res = await fetch("/api/playback/spotify/token");
    if (!res.ok) throw new Error((await res.json()).detail ?? "no token");
    return (await res.json()).access_token;
  }

  private async ensurePlayer(cb: EngineCallbacks): Promise<string> {
    if (this.player && this.deviceId) return this.deviceId;
    await new Promise<void>((resolve, reject) => {
      window.onSpotifyWebPlaybackSDKReady = () => resolve();
      loadScript("https://sdk.scdn.co/spotify-player.js", "spotify-sdk").catch(reject);
      if (window.Spotify?.Player) resolve();
    });
    return new Promise((resolve, reject) => {
      this.player = new window.Spotify.Player({
        name: "MediaShelf",
        getOAuthToken: (fn: (t: string) => void) =>
          this.token().then(fn).catch(() => reject(new Error("token"))),
        volume: 0.8,
      });
      const fail = (m: string) => () => reject(new Error(m));
      this.player.addListener("initialization_error", fail("init"));
      this.player.addListener("authentication_error", fail("auth"));
      this.player.addListener("account_error", fail("premium-required"));
      this.player.addListener("ready", ({ device_id }: any) => {
        this.deviceId = device_id;
        resolve(device_id);
      });
      this.player.addListener("player_state_changed", (state: any) => {
        if (!state) return;
        // Track end: the SDK reports paused at position 0 with the finished track
        // now in previous_tracks. Guard on having been playing so the initial
        // paused state (before playback) isn't mistaken for an end.
        const ended = state.paused && state.position === 0 && this._wasPlaying
          && (state.track_window?.previous_tracks?.length ?? 0) > 0;
        if (ended) {
          this._wasPlaying = false;
          cb.onState("ended");
          return;
        }
        this._wasPlaying = !state.paused;
        cb.onState(state.paused ? "paused" : "playing");
        cb.onProgress(state.position / 1000, state.duration / 1000);
      });
      this.player.connect();
      window.setTimeout(() => reject(new Error("sdk timeout")), 12000);
    });
  }

  async load(uri: string, cb: EngineCallbacks): Promise<void> {
    cb.onState("loading");
    try {
      const deviceId = await this.ensurePlayer(cb);
      const token = await this.token();
      const body = uri.startsWith("spotify:track:")
        ? { uris: [uri] }
        : { context_uri: uri };
      const res = await fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`,
        {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      if (!res.ok && res.status !== 204) throw new Error(`play ${res.status}`);
      window.clearInterval(this.timer);
      this.timer = window.setInterval(async () => {
        const s = await this.player?.getCurrentState?.();
        if (s) cb.onProgress(s.position / 1000, s.duration / 1000);
      }, 1000);
    } catch (e) {
      cb.onFail((e as Error).message);
    }
  }

  toggle() {
    this.player?.togglePlay?.();
  }

  seek(seconds: number) {
    this.player?.seek?.(seconds * 1000);
  }

  setVolume(v: number) {
    this.player?.setVolume?.(v);
  }

  destroy() {
    window.clearInterval(this.timer);
    this.player?.pause?.();
    // Keep the SDK device alive for the session — reconnecting is slow.
  }
}

// ---------- Apple Music (MusicKit JS v3) ----------
//
// NOTE: implemented against the MusicKit JS v3 API but UNTESTED — it needs a
// paid Apple Developer token (Settings → Keys) plus an Apple Music subscription
// to authorize in the browser. Plays by Apple catalog id when known, else
// resolves the track by title/artist via Apple's catalog search at play time.

let musicKitReady: Promise<void> | null = null;

function ensureMusicKitScript(): Promise<void> {
  if (!musicKitReady) {
    musicKitReady = new Promise((resolve, reject) => {
      if (window.MusicKit) return resolve();
      document.addEventListener("musickitloaded", () => resolve(), { once: true });
      loadScript("https://js-cdn.music.apple.com/musickit/v3/musickit.js", "musickit-js")
        .catch(reject);
      if (window.MusicKit) resolve();
    });
  }
  return musicKitReady;
}

export interface MusicKitPayload {
  apple_id?: string;
  title?: string;
  artists?: string[];
}

export class MusicKitEngine {
  private music: any = null;
  private configuring: Promise<any> | null = null;

  private async devToken(): Promise<string> {
    const res = await fetch("/api/playback/apple/token");
    if (!res.ok) throw new Error((await res.json()).detail ?? "no Apple Music token");
    return (await res.json()).developer_token;
  }

  private async instance(cb: EngineCallbacks): Promise<any> {
    if (this.music) return this.music;
    if (!this.configuring) {
      this.configuring = (async () => {
        const token = await this.devToken();
        await ensureMusicKitScript();
        const MK = window.MusicKit;
        const music = await MK.configure({
          developerToken: token,
          app: { name: "MediaShelf", build: "1.0" },
        });
        music.addEventListener("playbackStateDidChange", (e: any) => {
          const S = MK.PlaybackStates;
          const s = e.state ?? e.oldState;
          if (s === S.playing) cb.onState("playing");
          else if (s === S.paused) cb.onState("paused");
          else if (s === S.loading || s === S.waiting || s === S.stalled) cb.onState("loading");
          else if (s === S.completed || s === S.ended) cb.onState("ended");
        });
        music.addEventListener("playbackTimeDidChange", (e: any) => {
          cb.onProgress(e.currentPlaybackTime ?? 0,
                        e.currentPlaybackDuration ?? music.currentPlaybackDuration ?? 0);
        });
        this.music = music;
        return music;
      })();
    }
    return this.configuring;
  }

  private async resolveId(music: any, payload: MusicKitPayload): Promise<string | null> {
    if (payload.apple_id) return payload.apple_id;
    const term = `${payload.title ?? ""} ${(payload.artists ?? []).join(" ")}`.trim();
    if (!term) return null;
    const storefront = music.storefrontId || "us";
    const r = await music.api.music(`/v1/catalog/${storefront}/search`,
                                    { term, types: "songs", limit: 1 });
    return r?.data?.results?.songs?.data?.[0]?.id ?? null;
  }

  async load(payload: MusicKitPayload, cb: EngineCallbacks): Promise<void> {
    cb.onState("loading");
    try {
      const music = await this.instance(cb);
      await music.authorize(); // prompts Apple Music login; requires a subscription
      const id = await this.resolveId(music, payload);
      if (!id) {
        cb.onFail("Track not found on Apple Music");
        return;
      }
      await music.setQueue({ song: id });
      await music.play();
    } catch (e) {
      cb.onFail((e as Error).message || "Apple Music playback failed");
    }
  }

  toggle() {
    if (!this.music) return;
    if (this.music.isPlaying) void this.music.pause();
    else void this.music.play();
  }

  seek(seconds: number) {
    this.music?.seekToTime?.(seconds);
  }

  setVolume(v: number) {
    if (this.music) this.music.volume = v; // 0..1
  }

  destroy() {
    this.music?.stop?.();
  }
}
