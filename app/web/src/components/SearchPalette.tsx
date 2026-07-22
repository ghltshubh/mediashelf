import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { SearchResult } from "../lib/api";
import { useActivate, useDebounced, useUniversalSearch } from "../lib/searchData";
import { usePalette } from "../stores/palette";
import { SearchResultRow } from "./SearchResultRow";

function SkeletonRows() {
  return (
    <div className="space-y-1 px-3 py-2" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3 py-1.5">
          <div className="h-12 w-8 animate-pulse rounded bg-bg2" />
          <div className="h-4 flex-1 animate-pulse rounded bg-bg2" />
        </div>
      ))}
    </div>
  );
}

/** Cmd-K / "/" palette (Part 2 §4.3): 640px overlay, grouped results, keyboard
    nav (arrows, Tab cycles groups, Enter activates, Esc closes), progressive
    per-provider rendering. Full-screen below 700px. */
export function SearchPalette() {
  const { open, closePalette } = usePalette();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const debouncedQ = useDebounced(q, 300);
  const { groups, notices, videoPending, musicPending } = useUniversalSearch(debouncedQ);
  const { activate, importing, error } = useActivate();
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const flat = useMemo(() => {
    const rows: { item: SearchResult; group: string }[] = [];
    for (const g of groups) for (const item of g.items) rows.push({ item, group: g.key });
    return rows;
  }, [groups]);

  useEffect(() => setActiveIdx(0), [debouncedQ, groups.length]);

  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement as HTMLElement;
      setQ("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      restoreFocusRef.current?.focus?.();
    }
  }, [open]);

  useEffect(() => {
    const el = document.getElementById(`palette-row-${activeIdx}`);
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  if (!open) return null;

  const close = () => closePalette();

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Tab" && flat.length > 0) {
      // Tab cycles groups: jump to the first row of the next/previous group.
      e.preventDefault();
      const groupKeys = [...new Set(flat.map((r) => r.group))];
      const current = flat[activeIdx]?.group;
      const dir = e.shiftKey ? -1 : 1;
      const next =
        groupKeys[(groupKeys.indexOf(current) + dir + groupKeys.length) % groupKeys.length];
      setActiveIdx(flat.findIndex((r) => r.group === next));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flat[activeIdx] && !importing) {
        void activate(flat[activeIdx].item, close);
      } else if (q.trim().length >= 2) {
        navigate(`/search?q=${encodeURIComponent(q.trim())}`);
        close();
      }
    }
  };

  let rowIdx = -1;
  const pending = videoPending || musicPending;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60"
      onClick={close}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Universal search"
        onClick={(e) => e.stopPropagation()}
        className="mx-auto flex h-full w-full flex-col bg-bg1 min-[700px]:mt-[10vh] min-[700px]:h-auto
                   min-[700px]:max-h-[70vh] min-[700px]:w-[640px] min-[700px]:rounded-[10px]
                   min-[700px]:border min-[700px]:border-line"
      >
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search movies, shows, music…"
          aria-label="Search movies, shows, music"
          role="combobox"
          aria-expanded={flat.length > 0}
          aria-controls="palette-results"
          aria-activedescendant={flat.length ? `palette-row-${activeIdx}` : undefined}
          className="w-full border-b border-line bg-transparent px-4 py-3.5 text-[1rem] outline-none placeholder:text-muted/60"
        />

        <div id="palette-results" role="listbox" className="min-h-0 flex-1 overflow-y-auto py-2">
          {q.trim().length < 2 && (
            <p className="px-4 py-6 text-center font-mono text-[0.8rem] text-muted">
              type to search · ↑↓ navigate · Tab groups · Enter opens · Esc closes
            </p>
          )}

          {groups.map((g) => (
            <section key={g.key} className="mb-2">
              <h3 className="px-4 py-1.5 font-mono text-[0.7rem] tracking-widest text-muted">
                {g.label}
              </h3>
              {g.items.map((item) => {
                rowIdx += 1;
                const idx = rowIdx;
                return (
                  <SearchResultRow
                    key={`${g.key}-${idx}`}
                    id={`palette-row-${idx}`}
                    item={item}
                    active={idx === activeIdx}
                    onActivate={() => void activate(item, close)}
                    onHover={() => setActiveIdx(idx)}
                  />
                );
              })}
            </section>
          ))}

          {pending && q.trim().length >= 2 && <SkeletonRows />}

          {!pending && q.trim().length >= 2 && flat.length === 0 && (
            <p className="px-4 py-6 text-center text-[0.9rem] text-muted">
              Nothing found for “{q.trim()}”.
            </p>
          )}

          {(notices.length > 0 || error || importing) && (
            <div className="space-y-1 px-4 py-2">
              {importing && (
                <p className="font-mono text-[0.75rem] text-muted">loading title…</p>
              )}
              {error && (
                <p className="font-mono text-[0.75rem] text-[color:var(--danger)]">{error}</p>
              )}
              {notices.map((n) => (
                <p key={n} className="rounded-full border border-line px-3 py-1 font-mono text-[0.7rem] text-muted">
                  {n}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
