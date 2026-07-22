import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";

/** Country-name region picking: home region as a named select, extra
    watch-regions as a searchable checkbox list. Falls back to nothing until
    a TMDB key exists (the region list comes from TMDB). */
export function RegionPicker({
  home,
  extras,
  onHomeChange,
  onExtrasChange,
  saving,
}: {
  home: string;
  extras: string[];
  onHomeChange: (code: string) => void;
  onExtrasChange: (codes: string[]) => void;
  saving: boolean;
}) {
  const regions = useQuery({ queryKey: ["regions"], queryFn: api.regions, staleTime: Infinity });
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState<string[] | null>(null);

  const list = regions.data ?? [];
  const selected = draft ?? extras;
  const dirty = draft !== null && draft.join(",") !== extras.join(",");
  const shown = list.filter(
    (r) =>
      r.code !== home &&
      (filter === "" ||
        r.name.toLowerCase().includes(filter.toLowerCase()) ||
        r.code.toLowerCase() === filter.toLowerCase()),
  );

  const toggle = (code: string) => {
    const cur = draft ?? extras;
    setDraft(cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]);
  };

  if (list.length === 0) {
    return (
      <p className="font-mono text-[0.75rem] text-muted">
        region list loads once your TMDB key is set
      </p>
    );
  }

  return (
    <div className="max-w-lg">
      <label className="block">
        <span className="font-mono text-[0.75rem] text-muted">HOME REGION</span>
        <select
          value={home}
          onChange={(e) => onHomeChange(e.target.value)}
          className="mt-1 w-full rounded-[6px] border border-line bg-bg1 px-3 py-2 font-mono text-[0.875rem]"
        >
          {list.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name} ({r.code})
            </option>
          ))}
        </select>
      </label>

      <div className="mt-4">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[0.75rem] text-muted">
            ALSO TRACK REGIONS · {selected.length} selected
          </span>
          {dirty && (
            <button
              onClick={() => {
                onExtrasChange(draft ?? []);
                setDraft(null);
              }}
              disabled={saving}
              className="rounded-[6px] bg-owned px-3 py-1 text-[0.8rem] font-medium text-bg0 disabled:opacity-40"
            >
              {saving ? "Saving…" : "Apply"}
            </button>
          )}
        </div>
        {selected.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {selected.map((code) => {
              const name = list.find((r) => r.code === code)?.name ?? code;
              return (
                <button
                  key={code}
                  onClick={() => toggle(code)}
                  title={`Remove ${name}`}
                  className="inline-flex items-center gap-1 rounded-full border border-owned/50 bg-owned/10 px-2 py-0.5 font-mono text-[0.7rem] text-owned hover:bg-owned/20"
                >
                  {name} <span aria-hidden>✕</span>
                </button>
              );
            })}
          </div>
        )}
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter countries…"
          aria-label="Filter countries"
          className="mt-2 w-full rounded-[6px] border border-line bg-bg1 px-3 py-1.5 font-mono text-[0.8rem] placeholder:text-muted/50"
        />
        <div className="mt-2 grid max-h-56 grid-cols-1 gap-x-4 overflow-y-auto rounded-[6px] border border-line bg-bg1 p-2 sm:grid-cols-2">
          {shown.map((r) => (
            <label
              key={r.code}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-[0.85rem] hover:bg-bg2"
            >
              <input
                type="checkbox"
                checked={selected.includes(r.code)}
                onChange={() => toggle(r.code)}
                className="accent-[var(--owned)]"
              />
              <span className="min-w-0 truncate">{r.name}</span>
              <span className="ml-auto font-mono text-[0.7rem] text-muted">{r.code}</span>
            </label>
          ))}
          {shown.length === 0 && (
            <p className="px-2 py-1 font-mono text-[0.75rem] text-muted">no match</p>
          )}
        </div>
      </div>
    </div>
  );
}
