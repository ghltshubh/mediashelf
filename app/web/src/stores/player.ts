// Player state (M3). One thing playing at a time; switching engines stops the
// previous cleanly (Part 2 §4.5). Live re-routing: an engine that fails hands
// off to the next option in the chain with a toast naming the switch.

import { create } from "zustand";
import type { PlayOption } from "../lib/api";
import { Html5AudioEngine, MusicKitEngine, SpotifySdkEngine, YouTubeEngine } from "../lib/engines";

export interface PlayRequest {
  title: string;
  subtitle: string;
  artwork: string | null;
  options: PlayOption[];
  // Music via YouTube: hide the video theater and play audio only (the iframe
  // stays alive off-screen). Trailers/actual videos leave this unset.
  audioOnly?: boolean;
}

interface PlayerState {
  request: PlayRequest | null;
  option: PlayOption | null;
  status: "idle" | "loading" | "playing" | "paused";
  position: number;
  duration: number;
  volume: number;
  toast: string | null;
  queue: PlayRequest[];
  queueIndex: number;
  play: (req: PlayRequest, choice?: PlayOption) => void;
  playQueue: (queue: PlayRequest[], index: number, choice?: PlayOption) => void;
  next: () => void;
  prev: () => void;
  stop: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  setVolume: (v: number) => void;
  showToast: (msg: string) => void;
}

const youtube = new YouTubeEngine();
const spotifySdk = new SpotifySdkEngine();
const audio = new Html5AudioEngine();
const musicKit = new MusicKitEngine();
let toastTimer: number | undefined;

export const YOUTUBE_CONTAINER_ID = "yt-theater-slot";

function stopEngines() {
  youtube.destroy();
  spotifySdk.destroy();
  audio.destroy();
  musicKit.destroy();
}

export const usePlayer = create<PlayerState>((set, get) => {
  const callbacks = {
    onState: (s: "loading" | "playing" | "paused" | "ended") => {
      if (s === "ended") {
        // Continuous playback: advance to the next queued track, else go idle.
        get().next();
        return;
      }
      set({ status: s === "loading" ? "loading" : s });
    },
    onProgress: (position: number, duration: number) => set({ position, duration }),
    onFail: (reason: string) => {
      const { request, option } = get();
      if (!request || !option) return;
      // Re-route live: next option in the chain after the failed one.
      const idx = request.options.findIndex((o) => o === option || o.engine === option.engine);
      const next = request.options[idx + 1];
      if (reason === "embed-blocked" && option.engine === "youtube") {
        // Some YouTube videos (often official music) disable embedding, so the
        // in-app player can't play them. In a queue, skip and keep going rather
        // than stopping everything or spamming tabs; for a single track, hand
        // off to YouTube.
        const { queue, queueIndex } = get();
        if (queueIndex >= 0 && queueIndex < queue.length - 1) {
          get().showToast(`Can't play "${request.title}" here — skipping`);
          get().next();
        } else {
          get().showToast("This video can't be embedded — opening on YouTube");
          window.open(`https://www.youtube.com/watch?v=${option.payload.video_id}`, "_blank", "noopener");
          get().stop();
        }
        return;
      }
      if (next) {
        get().showToast(`${option.label} unavailable — trying ${next.label}`);
        load(request, next);  // re-route within the same track — keep the queue
      } else {
        get().showToast(`${option.label} unavailable`);
        get().stop();
      }
    },
  };

  // Shared engine loader. `play` (single track) clears the queue first; the
  // queue methods and the re-route call this directly so the queue survives.
  function load(req: PlayRequest, choice?: PlayOption): void {
    const option = choice ?? req.options.find((o) => o.engine !== "deeplink") ?? req.options[0];
    if (!option) return;
    if (option.engine === "deeplink") {
      if (option.payload.url) window.open(option.payload.url, "_blank", "noopener");
      return;
    }
    stopEngines();
    set({ request: req, option, status: "loading", position: 0, duration: 0 });
    if (option.engine === "youtube" && option.payload.video_id) {
      // The theater slot must exist before the iframe mounts.
      window.setTimeout(
        () => youtube.load(YOUTUBE_CONTAINER_ID, option.payload.video_id!, callbacks), 0);
    } else if (option.engine === "spotify_sdk" && option.payload.spotify_uri) {
      void spotifySdk.load(option.payload.spotify_uri, callbacks);
    } else if (option.engine === "spotify_embed") {
      set({ status: "playing" });  // embed manages itself; we just host it
    } else if (option.engine === "audio" && option.payload.url) {
      void audio.load(option.payload.url, callbacks);
    } else if (option.engine === "musickit") {
      void musicKit.load(option.payload, callbacks);
    }
  }

  return {
    request: null,
    option: null,
    status: "idle",
    position: 0,
    duration: 0,
    volume: 0.8,
    toast: null,
    queue: [],
    queueIndex: -1,

    playQueue: (queue, index, choice) => {
      // Clicking a track in a list plays it and continues through the rest.
      set({ queue, queueIndex: index });
      const req = queue[index];
      if (req) load(req, choice);
    },

    next: () => {
      const { queue, queueIndex } = get();
      const ni = queueIndex + 1;
      if (ni >= 0 && ni < queue.length) {
        set({ queueIndex: ni });
        load(queue[ni]);
      } else {
        get().stop();
      }
    },

    prev: () => {
      const { queue, queueIndex } = get();
      const pi = queueIndex - 1;
      if (pi >= 0 && pi < queue.length) {
        set({ queueIndex: pi });
        load(queue[pi]);
      }
    },

    // Standalone single-track play (Title page, etc.): drop any queue so a track
    // that ends doesn't auto-advance into a stale list.
    play: (req, choice) => {
      set({ queue: [], queueIndex: -1 });
      load(req, choice);
    },

    stop: () => {
      stopEngines();
      set({ request: null, option: null, status: "idle", position: 0, duration: 0,
            queue: [], queueIndex: -1 });
    },

    toggle: () => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.toggle();
      else if (option?.engine === "spotify_sdk") spotifySdk.toggle();
      else if (option?.engine === "audio") audio.toggle();
      else if (option?.engine === "musickit") musicKit.toggle();
    },

    seek: (seconds) => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.seek(seconds);
      else if (option?.engine === "spotify_sdk") spotifySdk.seek(seconds);
      else if (option?.engine === "audio") audio.seek(seconds);
      else if (option?.engine === "musickit") musicKit.seek(seconds);
      set({ position: seconds });
    },

    setVolume: (v) => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.setVolume(v);
      else if (option?.engine === "spotify_sdk") spotifySdk.setVolume(v);
      else if (option?.engine === "audio") audio.setVolume(v);
      else if (option?.engine === "musickit") musicKit.setVolume(v);
      set({ volume: v });
    },

    showToast: (msg) => {
      window.clearTimeout(toastTimer);
      set({ toast: msg });
      toastTimer = window.setTimeout(() => set({ toast: null }), 4000);
    },
  };
});
