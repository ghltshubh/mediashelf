// Player state (M3). One thing playing at a time; switching engines stops the
// previous cleanly (Part 2 §4.5). Live re-routing: an engine that fails hands
// off to the next option in the chain with a toast naming the switch.

import { create } from "zustand";
import type { PlayOption } from "../lib/api";
import { SpotifySdkEngine, YouTubeEngine } from "../lib/engines";

export interface PlayRequest {
  title: string;
  subtitle: string;
  artwork: string | null;
  options: PlayOption[];
}

interface PlayerState {
  request: PlayRequest | null;
  option: PlayOption | null;
  status: "idle" | "loading" | "playing" | "paused";
  position: number;
  duration: number;
  volume: number;
  toast: string | null;
  play: (req: PlayRequest, choice?: PlayOption) => void;
  stop: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  setVolume: (v: number) => void;
  showToast: (msg: string) => void;
}

const youtube = new YouTubeEngine();
const spotifySdk = new SpotifySdkEngine();
let toastTimer: number | undefined;

export const YOUTUBE_CONTAINER_ID = "yt-theater-slot";

function stopEngines() {
  youtube.destroy();
  spotifySdk.destroy();
}

export const usePlayer = create<PlayerState>((set, get) => {
  const callbacks = {
    onState: (s: "loading" | "playing" | "paused" | "ended") =>
      set(s === "ended" ? { status: "idle", request: null, option: null }
        : { status: s === "loading" ? "loading" : s }),
    onProgress: (position: number, duration: number) => set({ position, duration }),
    onFail: (reason: string) => {
      const { request, option } = get();
      if (!request || !option) return;
      // Re-route live: next option in the chain after the failed one.
      const idx = request.options.findIndex((o) => o === option || o.engine === option.engine);
      const next = request.options[idx + 1];
      if (reason === "embed-blocked" && option.engine === "youtube") {
        get().showToast("This video can't be embedded — opening on YouTube");
        window.open(`https://www.youtube.com/watch?v=${option.payload.video_id}`, "_blank", "noopener");
        get().stop();
        return;
      }
      if (next) {
        get().showToast(`${option.label} unavailable — trying ${next.label}`);
        get().play(request, next);
      } else {
        get().showToast(`${option.label} unavailable`);
        get().stop();
      }
    },
  };

  return {
    request: null,
    option: null,
    status: "idle",
    position: 0,
    duration: 0,
    volume: 0.8,
    toast: null,

    play: (req, choice) => {
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
      } else if (option.engine === "musickit") {
        callbacks.onFail("MusicKit playback not wired yet");
      }
    },

    stop: () => {
      stopEngines();
      set({ request: null, option: null, status: "idle", position: 0, duration: 0 });
    },

    toggle: () => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.toggle();
      else if (option?.engine === "spotify_sdk") spotifySdk.toggle();
    },

    seek: (seconds) => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.seek(seconds);
      else if (option?.engine === "spotify_sdk") spotifySdk.seek(seconds);
      set({ position: seconds });
    },

    setVolume: (v) => {
      const { option } = get();
      if (option?.engine === "youtube") youtube.setVolume(v);
      else if (option?.engine === "spotify_sdk") spotifySdk.setVolume(v);
      set({ volume: v });
    },

    showToast: (msg) => {
      window.clearTimeout(toastTimer);
      set({ toast: msg });
      toastTimer = window.setTimeout(() => set({ toast: null }), 4000);
    },
  };
});
