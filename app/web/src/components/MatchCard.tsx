import { useEffect, useRef, useState } from "react";
import type { MusicResult, ReviewItem, TrackPayload } from "../lib/api";
import { api } from "../lib/api";
import { isMusic, useDebounced } from "../lib/searchData";

function fmt(ms?: number | null): string {
  if (!ms) return "—";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function Side({ label, track }: { label: string; track: TrackPayload }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 font-mono text-[0.65rem] tracking-widest text-muted">{label}</p>
      <div className="flex gap-3">
        {track.thumb ? (
          <img src={track.thumb} alt="" className="h-14 w-14 rounded object-cover" />
        ) : (
          <div className="flex h-14 w-14 items-center justify-center rounded bg-bg2 text-muted">♪</div>
        )}
        <div className="min-w-0">
          <p className="truncate text-[0.95rem]">{track.title}</p>
          <p className="truncate font-mono text-[0.75rem] text-muted">
            {(track.artists ?? []).join(", ")}
            {track.album ? ` · ${track.album}` : ""}
          </p>
          <p className="font-mono text-[0.7rem] text-muted">
            {fmt(track.duration_ms)}{track.service ? ` · ${track.service}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Side-by-side match review (Part 2 §4.6): source vs proposed target,
    duration delta, Approve / Pick another (inline search) / Skip. */
export function MatchCard({
  item,
  active,
  pickerOpen,
  onApprove,
  onSkip,
  onReplace,
  onTogglePicker,
  onFocus,
}: {
  item: ReviewItem;
  active: boolean;
  pickerOpen: boolean;
  onApprove: () => void;
  onSkip: () => void;
  onReplace: (candidate: TrackPayload) => void;
  onTogglePicker: () => void;
  onFocus: () => void;
}) {
  const [q, setQ] = useState("");
  const debounced = useDebounced(q, 300);
  const [results, setResults] = useState<MusicResult[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (pickerOpen) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [pickerOpen]);

  useEffect(() => {
    let cancelled = false;
    if (!pickerOpen || debounced.trim().length < 2) {
      setResults([]);
      return;
    }
    api.search("music", debounced).then((r) => {
      if (cancelled) return;
      const items = r.groups.flatMap((g) => g.items).filter(isMusic)
        .filter((m) => m.entity === "track");
      setResults(items.slice(0, 5));
    });
    return () => {
      cancelled = true;
    };
  }, [pickerOpen, debounced]);

  const delta =
    item.source.duration_ms && item.candidate.duration_ms
      ? (item.candidate.duration_ms - item.source.duration_ms) / 1000
      : null;

  return (
    // Mouse click OR keyboard focus of any inner control marks this the active
    // row (for the A/S/P shortcuts) — no bogus button role on a container.
    <div
      onClick={onFocus}
      onFocusCapture={onFocus}
      className={`rounded-[10px] border bg-bg1 p-4 ${
        active ? "border-owned/60" : "border-line"
      }`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <Side label="SOURCE" track={item.source} />
        <div className="shrink-0 text-center font-mono text-[0.75rem] text-muted">
          <span aria-hidden className="block text-[1.1rem] text-owned">→</span>
          {delta != null && (
            <span title="duration delta">{delta > 0 ? "+" : ""}{delta.toFixed(1)}s</span>
          )}
        </div>
        <Side label="PROPOSED" track={item.candidate} />
        <div className="shrink-0 text-right">
          <span
            className={`rounded-full border px-2 py-0.5 font-mono text-[0.75rem] ${
              item.confidence >= 0.9
                ? "border-[color:var(--play)]/60 text-[color:var(--play)]"
                : "border-owned/50 text-owned"
            }`}
          >
            {(item.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button onClick={onApprove}
                className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.85rem] font-medium text-bg0">
          Approve <kbd className="ml-1 opacity-60">A</kbd>
        </button>
        <button onClick={onTogglePicker}
                className="rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] hover:bg-bg2">
          Pick another <kbd className="ml-1 text-muted">P</kbd>
        </button>
        <button onClick={onSkip}
                className="rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] text-muted hover:bg-bg2">
          Skip <kbd className="ml-1">S</kbd>
        </button>
      </div>

      {pickerOpen && (
        <div className="mt-3 rounded-[6px] border border-line bg-bg0 p-2">
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="search for the right track…"
            aria-label="Search replacement track"
            className="w-full rounded-[6px] border border-line bg-bg1 px-3 py-1.5 text-[0.875rem] outline-none placeholder:text-muted/50"
          />
          <div className="mt-1">
            {results.map((m, i) => (
              <button
                key={i}
                onClick={() =>
                  onReplace({
                    title: m.title, artists: m.artists, duration_ms: m.duration_ms ?? null,
                    thumb: m.thumb, spotify_id: (m as MusicResult & { spotify_id?: string }).spotify_id ?? null,
                    url: m.services[0]?.url ?? null, service: m.services[0]?.service_key,
                  })
                }
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-bg2"
              >
                {m.thumb && <img src={m.thumb} alt="" className="h-8 w-8 rounded object-cover" />}
                <span className="min-w-0 truncate text-[0.85rem]">{m.title}</span>
                <span className="truncate font-mono text-[0.7rem] text-muted">
                  {m.artists.join(", ")}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[0.7rem] text-muted">
                  {fmt(m.duration_ms)}
                </span>
              </button>
            ))}
            {q.trim().length >= 2 && results.length === 0 && (
              <p className="px-2 py-1.5 font-mono text-[0.75rem] text-muted">no tracks found</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
