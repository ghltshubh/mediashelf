// Shared search plumbing for the palette and the results page: debounced query,
// per-scope fan-out (sections render progressively), provider status messages,
// and row activation.

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePlayer } from "../stores/player";
import { api, type MusicResult, type SearchResult, type VideoResult } from "./api";

export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function isVideo(item: SearchResult): item is VideoResult {
  return !("entity" in item);
}
export function isMusic(item: SearchResult): item is MusicResult {
  return "entity" in item;
}

export interface SearchGroup {
  key: string;
  label: string;
  items: SearchResult[];
}

const PROVIDER_MESSAGES: Record<string, Record<string, string>> = {
  tmdb: {
    unconfigured: "Add your TMDB key (Settings → Keys) to search movies & TV",
    unavailable: "TMDB search unavailable — showing your local catalog only",
  },
  spotify: {
    unconfigured: "Add Spotify API keys (Settings → Keys) to search music",
    unavailable: "Spotify search unavailable",
  },
};

export function useUniversalSearch(q: string) {
  // Independent queries per scope so one slow or failing provider never blocks
  // the other sections (plan §4.3 + failure modes).
  const enabled = q.trim().length >= 2;
  const library = useQuery({
    queryKey: ["search", "library", q],
    queryFn: () => api.search("library", q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const video = useQuery({
    queryKey: ["search", "video", q],
    queryFn: () => api.search("video", q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const music = useQuery({
    queryKey: ["search", "music", q],
    queryFn: () => api.search("music", q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

  // YOUR LIBRARY pinned first when it has hits (§4.3).
  const groups: SearchGroup[] = [
    ...(library.data?.groups ?? []),
    ...(video.data?.groups ?? []),
    ...(music.data?.groups ?? []),
  ];
  const notices = [...(video.data?.providers ?? []), ...(music.data?.providers ?? [])]
    .filter((p) => p.state !== "ok")
    .map((p) => PROVIDER_MESSAGES[p.key]?.[p.state])
    .filter((m): m is string => !!m);

  return {
    enabled,
    groups,
    notices,
    videoPending: enabled && video.isPending,
    musicPending: enabled && music.isPending,
  };
}

/** Executes a result's smart-default action. Returns once navigation/opening happened. */
export function useActivate() {
  const navigate = useNavigate();
  const player = usePlayer();
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function activate(item: SearchResult, onDone?: () => void) {
    const action = item.action;
    if (!action) return;
    setError(null);
    if (action.type === "play" && isMusic(item) && item.playback) {
      // M3: Enter's smart default is the playback routing chain.
      player.play({
        title: item.title,
        subtitle: item.artists.join(", "),
        artwork: item.thumb,
        options: item.playback.options,
      });
      onDone?.();
    } else if (action.type === "deeplink" && action.url) {
      window.open(action.url, "_blank", "noopener");
      onDone?.();
    } else if (action.type === "title" && action.title_id != null) {
      navigate(`/title/${action.title_id}`);
      onDone?.();
    } else if (action.type === "import" && action.media_type && action.tmdb_id != null) {
      setImporting(true);
      try {
        const title = await api.importTitle(action.media_type, action.tmdb_id);
        navigate(`/title/${title.id}`);
        onDone?.();
      } catch (e) {
        setError(`Couldn't load that title — ${(e as Error).message}`);
      } finally {
        setImporting(false);
      }
    }
  }

  return { activate, importing, error };
}
