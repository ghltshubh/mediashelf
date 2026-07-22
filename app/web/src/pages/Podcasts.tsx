import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { StatusBanner } from "../components/StatusBanner";
import { api } from "../lib/api";
import type { Podcast, PodcastEpisode, PlayOption, Playback } from "../lib/api";
import { fmtDate, useLocale } from "../lib/locale";
import { usePlayer } from "../stores/player";

function fmtDuration(s: number | null): string {
  if (!s || s <= 0) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m} min`;
}

// Episodes play through the shared player queue so the list auto-advances.
function episodeRequest(podcast: Podcast, ep: PodcastEpisode) {
  const option: PlayOption = {
    engine: "audio",
    service_key: "podcast",
    label: podcast.title,
    kind: "episode",
    payload: { url: ep.audio_url },
  };
  const playback: Playback = { options: [option], default: option };
  return {
    title: ep.title,
    subtitle: podcast.title,
    artwork: ep.image_url ?? podcast.image_url,
    options: playback.options,
  };
}

function EpisodeList({ podcast }: { podcast: Podcast }) {
  const player = usePlayer();
  const locale = useLocale();
  const detail = useQuery({
    queryKey: ["podcast", podcast.id],
    queryFn: () => api.podcast(podcast.id),
  });
  const eps = detail.data?.episodes ?? [];

  if (detail.isLoading) return <div className="h-24 animate-pulse rounded-[8px] bg-bg2" />;
  if (eps.length === 0) {
    return <p className="px-1 py-4 font-mono text-[0.8rem] text-muted">No episodes with audio found.</p>;
  }

  const queue = eps.map((e) => episodeRequest(detail.data!, e));

  return (
    <div className="mt-2 divide-y divide-line rounded-[8px] border border-line bg-bg0">
      {eps.map((ep, i) => {
        const playing = player.request?.title === ep.title && player.status !== "idle";
        return (
          <button
            key={ep.id}
            onClick={() => player.playQueue(queue, i)}
            className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-bg2"
          >
            <span className={`shrink-0 text-[1rem] ${playing ? "text-[color:var(--play)]" : "text-muted"}`}>
              {playing && player.status === "playing" ? "⏸" : "▶"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.9rem]">{ep.title}</p>
              <p className="truncate font-mono text-[0.7rem] text-muted">
                {[fmtDate(ep.published_at, locale), fmtDuration(ep.duration_seconds)].filter(Boolean).join(" · ")}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

/** Podcasts (M8): subscribe by RSS feed / OPML, play episodes in-app. */
export function Podcasts() {
  const queryClient = useQueryClient();
  const podcasts = useQuery({ queryKey: ["podcasts"], queryFn: api.podcasts });
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["podcasts"] });

  const subscribe = useMutation({
    mutationFn: (feed: string) => api.subscribePodcast(feed),
    onSuccess: () => { setUrl(""); setError(null); invalidate(); },
    onError: (e: Error) => setError(e.message),
  });
  const unsubscribe = useMutation({
    mutationFn: (id: number) => api.unsubscribePodcast(id),
    onSuccess: invalidate,
  });
  const refresh = useMutation({
    mutationFn: () => api.refreshPodcasts(),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["podcast"] });
    },
  });
  const importOpml = useMutation({
    mutationFn: (file: File) => api.importPodcastOpml(file),
    onSuccess: () => { setError(null); invalidate(); },
    onError: (e: Error) => setError(e.message),
  });

  const shows = podcasts.data ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 flex items-center justify-between">
        <h1 className="font-display text-[1.6rem] font-bold">Podcasts</h1>
        <div className="flex gap-2">
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || shows.length === 0}
            className="rounded-[6px] border border-line px-3 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2 disabled:opacity-40"
          >
            {refresh.isPending ? "refreshing…" : "refresh all"}
          </button>
          <a
            href="/api/podcasts/opml/export"
            className="rounded-[6px] border border-line px-3 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2"
          >
            export OPML
          </a>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={importOpml.isPending}
            className="rounded-[6px] border border-line px-3 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2 disabled:opacity-40"
          >
            {importOpml.isPending ? "importing…" : "import OPML"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".opml,.xml,text/xml,application/xml"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importOpml.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      </div>
      <p className="mb-5 font-mono text-[0.8rem] text-muted">
        {shows.length} subscription{shows.length === 1 ? "" : "s"} · no account or API key needed
      </p>

      <form
        onSubmit={(e) => { e.preventDefault(); if (url.trim()) subscribe.mutate(url.trim()); }}
        className="mb-6 flex gap-2"
      >
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a podcast RSS feed URL…"
          aria-label="Podcast RSS feed URL"
          className="flex-1 rounded-[6px] border border-line bg-bg1 px-3 py-2 text-[0.9rem] outline-none placeholder:text-muted/50 focus:border-owned/60"
        />
        <button
          type="submit"
          disabled={subscribe.isPending || !url.trim()}
          className="rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0 disabled:opacity-40"
        >
          {subscribe.isPending ? "adding…" : "Subscribe"}
        </button>
      </form>

      {error && <StatusBanner kind="danger">{error}</StatusBanner>}

      {shows.length === 0 ? (
        <EmptyState message="No podcasts yet. Paste an RSS feed URL above, or import an OPML file from another app." />
      ) : (
        <div className="space-y-3">
          {shows.map((pod) => (
            <div key={pod.id} className="rounded-[10px] border border-line bg-bg1">
              <div className="flex items-center gap-3 p-3">
                {pod.image_url ? (
                  <img src={pod.image_url} alt="" className="h-14 w-14 shrink-0 rounded object-cover" />
                ) : (
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded bg-bg2 text-muted">🎙</div>
                )}
                <button
                  onClick={() => setExpanded(expanded === pod.id ? null : pod.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate font-medium">{pod.title}</p>
                  <p className="truncate font-mono text-[0.72rem] text-muted">
                    {[pod.author, `${pod.episode_count} episode${pod.episode_count === 1 ? "" : "s"}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </button>
                <button
                  onClick={() => setExpanded(expanded === pod.id ? null : pod.id)}
                  aria-label={expanded === pod.id ? "Collapse" : "Expand"}
                  className="shrink-0 px-2 text-muted hover:text-ink"
                >
                  <span className={`inline-block transition-transform ${expanded === pod.id ? "rotate-90" : ""}`}>▸</span>
                </button>
                <button
                  onClick={() => unsubscribe.mutate(pod.id)}
                  aria-label="Unsubscribe"
                  className="shrink-0 rounded px-2 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2 hover:text-danger"
                >
                  ✕
                </button>
              </div>
              {expanded === pod.id && <div className="px-3 pb-3"><EpisodeList podcast={pod} /></div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
