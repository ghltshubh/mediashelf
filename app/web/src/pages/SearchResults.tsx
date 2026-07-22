import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FilterChips } from "../components/FilterChips";
import { SearchResultRow } from "../components/SearchResultRow";
import { useActivate, useDebounced, useUniversalSearch } from "../lib/searchData";

const CHIP_FOR_GROUP: Record<string, string> = {
  movies_tv: "video",
  music: "music",
  artists: "artists",
};

/** Full results page (Part 2 §4.3): same grouping as the palette, filter chips. */
export function SearchResults() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const debouncedQ = useDebounced(q, 300);
  const { groups, notices, videoPending, musicPending } = useUniversalSearch(debouncedQ);
  const { activate, importing, error } = useActivate();
  const [chip, setChip] = useState("all");

  const visible = groups.filter((g) => chip === "all" || CHIP_FOR_GROUP[g.key] === chip);
  const pending = videoPending || musicPending;

  return (
    <div className="mx-auto max-w-3xl">
      <input
        value={q}
        onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })}
        placeholder="Search movies, shows, music…"
        aria-label="Search movies, shows, music"
        autoFocus
        className="w-full rounded-[10px] border border-line bg-bg1 px-4 py-3 text-[1rem] outline-none placeholder:text-muted/60 focus:border-owned/60"
      />

      <div className="mt-4">
        <FilterChips
          chips={[
            { key: "all", label: "All" },
            { key: "video", label: "Movies & Shows" },
            { key: "music", label: "Music" },
            { key: "artists", label: "Artists" },
          ]}
          active={chip}
          onSelect={setChip}
        />
      </div>

      <div className="mt-6 space-y-8">
        {importing && <p className="font-mono text-[0.8rem] text-muted">loading title…</p>}
        {error && <p className="font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}
        {notices.map((n) => (
          <p key={n} className="rounded-[6px] border border-line bg-bg1 px-3 py-2 font-mono text-[0.75rem] text-muted">
            {n}
          </p>
        ))}

        {visible.map((g) => (
          <section key={g.key}>
            <h2 className="mb-2 font-mono text-[0.75rem] tracking-widest text-muted">{g.label}</h2>
            <div className="rounded-[10px] border border-line bg-bg1 py-1">
              {g.items.map((item, i) => (
                <SearchResultRow
                  key={`${g.key}-${i}`}
                  id={`results-${g.key}-${i}`}
                  item={item}
                  active={false}
                  onActivate={() => void activate(item)}
                />
              ))}
            </div>
          </section>
        ))}

        {q.trim().length >= 2 && !pending && visible.length === 0 && (
          <p className="py-10 text-center text-muted">Nothing found for “{q.trim()}”.</p>
        )}
        {q.trim().length < 2 && (
          <p className="py-10 text-center font-mono text-[0.8rem] text-muted">
            Tip: press <kbd className="rounded border border-line px-1">/</kbd> or{" "}
            <kbd className="rounded border border-line px-1">⌘K</kbd> anywhere for the quick palette.
          </p>
        )}
      </div>
    </div>
  );
}
