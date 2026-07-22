import type { SearchResult } from "../lib/api";
import { isVideo } from "../lib/searchData";
import { ServiceMark, distinctServices } from "./ServiceMark";

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
  // Video sub-line: "movie/show", rating, and a lead genre — matching the shelf
  // cards. Music keeps its entity · artists line.
  const genre = video ? item.genres?.[0] : undefined;
  const sub = video
    ? item.media_type === "tv" ? "show" : "movie"
    : item.entity === "artist" ? "artist" : `${item.entity} · ${item.artists.slice(0, 2).join(", ")}`;
  // Video shows deduped service LOGOS (like the cards); music keeps name pills
  // (music services carry no logos in the catalog).
  const videoMarks = video ? distinctServices(item.badges, 4) : [];

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
          {video && item.rating ? (
            <span className="shrink-0 font-mono text-[0.7rem] text-muted">★ {item.rating.toFixed(1)}</span>
          ) : null}
          {genre ? (
            <span className="shrink-0 truncate font-mono text-[0.7rem] text-muted">· {genre}</span>
          ) : null}
          {video
            ? videoMarks.map((b) => (
                <ServiceMark key={b.service_key} name={b.service_name} logo={b.logo} owned={b.owned} />
              ))
            : item.services.map((s) => (
                <span
                  key={s.service_key}
                  className={`shrink-0 rounded-full border px-1.5 font-mono text-[0.65rem] ${
                    s.owned ? "border-owned/50 text-owned" : "border-line text-muted"
                  }`}
                >
                  {s.service_name}
                </span>
              ))}
        </div>
      </div>
      <span className="shrink-0 font-mono text-[0.75rem] text-muted">{item.hint}</span>
    </div>
  );
}
