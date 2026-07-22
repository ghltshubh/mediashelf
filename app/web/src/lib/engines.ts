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

  destroy() {
    window.clearInterval(this.timer);
    this.player?.destroy?.();
    this.player = null;
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
