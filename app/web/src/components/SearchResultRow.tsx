import type { SearchResult } from "../lib/api";
import { isVideo } from "../lib/searchData";

function ThumbFallback({ label }: { label: string }) {
  return (
    <div className="flex h-12 w-8 shrink-0 items-center justify-center rounded bg-bg2 font-mono text-[0.6rem] text-muted">
      {label}
    </div>
  );
}

/** One row: thumb, title, year in mono, service badges (lit vs dimmed), and a
    right-aligned mono hint showing what Enter does (Part 2 §4.3). */
export function SearchResultRow({
  item,
  id,
  active,
  onActivate,
  onHover,
}: {
  item: SearchResult;
  id: string;
  active: boolean;
  onActivate: () => void;
  onHover?: () => void;
}) {
  const video = isVideo(item);
  const thumb = video ? item.poster : item.thumb;
  const sub = video
    ? item.media_type === "tv" ? "show" : "movie"
    : item.entity === "artist" ? "artist" : `${item.entity} · ${item.artists.slice(0, 2).join(", ")}`;
  const pills = video
    ? item.badges.slice(0, 4).map((b) => ({ key: b.service_key, name: b.service_name, owned: b.owned }))
    : item.services.map((s) => ({ key: s.service_key, name: s.service_name, owned: s.owned }));

  return (
    <div
      id={id}
      role="option"
      aria-selected={active}
      tabIndex={-1}
      onClick={onActivate}
      onMouseMove={onHover}
      className={`flex cursor-pointer items-center gap-3 rounded-[6px] px-3 py-2 ${
        active ? "bg-bg2" : ""
      }`}
    >
      {thumb ? (
        <img src={thumb} alt="" className="h-12 w-8 shrink-0 rounded object-cover" />
      ) : (
        <ThumbFallback label={video ? "▦" : "♪"} />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.95rem] leading-tight">
          {item.title}
          {item.year != null && (
            <span className="ml-2 font-mono text-[0.75rem] text-muted">{item.year}</span>
          )}
        </p>
        <div className="mt-0.5 flex items-center gap-1.5 overflow-hidden">
          <span className="shrink-0 font-mono text-[0.7rem] text-muted">{sub}</span>
          {pills.map((p) => (
            <span
              key={p.key}
              className={`shrink-0 rounded-full border px-1.5 font-mono text-[0.65rem] ${
                p.owned ? "border-owned/50 text-owned" : "border-line text-muted"
              }`}
            >
              {p.name}
            </span>
          ))}
        </div>
      </div>
      <span className="shrink-0 font-mono text-[0.75rem] text-muted">{item.hint}</span>
    </div>
  );
}
