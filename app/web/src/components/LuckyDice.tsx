import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Playback, ShelfItem } from "../lib/api";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";
import { GenreSelect } from "./GenreSelect";
import { serviceMarksNode } from "./serviceMarks";

type LuckyItem = ShelfItem & { runtime_minutes: number | null; play: Playback };

const LENGTHS = [0, 30, 60, 90, 120]; // 0 = any

/** Feeling lucky (🎲): pick a genre + max length, roll, and get a random title
    that's streaming on your services right now — revealed with Play (deep link
    into the owning app), Details, and Roll again. */
export function LuckyDice({ genres }: { genres: string[] }) {
  const t = useT();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [genre, setGenre] = useState("");
  const [maxMin, setMaxMin] = useState(0);
  const [type, setType] = useState("");
  const [rolling, setRolling] = useState(false);
  const [rolled, setRolled] = useState(false);
  const [item, setItem] = useState<LuckyItem | null>(null);

  function roll() {
    setRolling(true);
    setRolled(false);
    setItem(null);
    const started = Date.now();
    api
      .lucky(genre, maxMin || null, type)
      .then((r) => {
        // Let the die spin at least ~0.9s so the roll reads as a roll.
        const wait = Math.max(0, 900 - (Date.now() - started));
        window.setTimeout(() => {
          setItem(r.found && r.item ? r.item : null);
          setRolled(true);
          setRolling(false);
        }, wait);
      })
      .catch(() => {
        setRolled(true);
        setRolling(false);
      });
  }

  function close() {
    setOpen(false);
    setRolled(false);
    setItem(null);
  }

  const playDefault = item?.play.default;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label={t("lucky.title")}
        title={t("lucky.title")}
        className="hoverable -mb-px cursor-pointer px-3 py-2 text-[1.05rem] opacity-80 hover:opacity-100"
      >
        🎲
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-bg0/70 p-4 backdrop-blur-[2px]"
          onClick={close}
        >
          <div
            role="dialog"
            aria-label={t("lucky.title")}
            onClick={(e) => e.stopPropagation()}
            className="w-[min(430px,92vw)] rounded-[10px] border border-line bg-bg1 p-5 shadow-xl"
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-display text-[1.25rem] font-semibold">{t("lucky.title")}</h2>
              <button
                onClick={close}
                aria-label={t("common.dismiss")}
                className="rounded px-1.5 font-mono text-[0.85rem] text-muted hover:bg-bg2 hover:text-ink"
              >
                ✕
              </button>
            </div>

            <div className="mb-5 flex flex-wrap items-center gap-3">
              <GenreSelect value={genre} genres={genres} onChange={setGenre} />
              <label className="flex items-center gap-1.5">
                <span className="font-mono text-[0.7rem] text-muted">length</span>
                <select
                  value={maxMin}
                  onChange={(e) => setMaxMin(Number(e.target.value))}
                  aria-label="Maximum length"
                  className="rounded-[6px] border border-line bg-bg1 px-2 py-1 font-mono text-[0.75rem] text-ink outline-none focus:border-owned/60"
                >
                  {LENGTHS.map((m) => (
                    <option key={m} value={m}>{m === 0 ? t("lucky.anyLength") : `≤ ${m} min`}</option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-1.5">
                <span className="font-mono text-[0.7rem] text-muted">type</span>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  aria-label="Media type"
                  className="rounded-[6px] border border-line bg-bg1 px-2 py-1 font-mono text-[0.75rem] text-ink outline-none focus:border-owned/60"
                >
                  <option value="">{t("chip.all")}</option>
                  <option value="movie">{t("tab.movies")}</option>
                  <option value="tv">{t("tab.shows")}</option>
                </select>
              </label>
            </div>

            {/* The die. Spins while a roll is in flight. */}
            <div className="mb-5 flex justify-center">
              <button
                onClick={roll}
                disabled={rolling}
                aria-label={t("lucky.roll")}
                className="cursor-pointer rounded-full border border-line bg-bg2 px-6 py-3 text-[2rem] leading-none hover:border-owned/60 disabled:cursor-default"
              >
                <span className={`inline-block ${rolling ? "dice-rolling" : ""}`}>🎲</span>
              </button>
            </div>

            {rolled && item && (
              <div className="flex gap-4">
                <div className={`${item.owned ? "lit" : "dimmed"} w-24 shrink-0 self-start rounded-[8px]`}>
                  {item.poster ? (
                    <img src={item.poster} alt="" className="poster w-full rounded-[8px]" />
                  ) : (
                    <div className="flex aspect-[2/3] items-center justify-center rounded-[8px] bg-bg2 p-2 text-center font-display text-[0.7rem] text-muted">
                      {item.title}
                    </div>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-display text-[1.05rem] font-semibold leading-tight">{item.title}</p>
                  <p className="mt-1 font-mono text-[0.75rem] text-muted">
                    {[item.year, item.rating ? `★ ${item.rating.toFixed(1)}` : null,
                      item.runtime_minutes ? `${item.runtime_minutes} min` : null,
                      item.genres?.[0]]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <div className="mt-1.5 flex items-center gap-1 font-mono text-[0.75rem] text-muted">
                    {serviceMarksNode(item.badges, item.owned)}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {playDefault?.payload.url && (
                      <a
                        href={playDefault.payload.url}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.85rem] font-medium text-bg0"
                      >
                        ▶ {playDefault.label}
                      </a>
                    )}
                    <button
                      onClick={() => { close(); navigate(`/title/${item.id}`); }}
                      className="cursor-pointer rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] hover:bg-bg2"
                    >
                      {t("lucky.details")}
                    </button>
                    <button
                      onClick={roll}
                      className="cursor-pointer rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] text-muted hover:bg-bg2"
                    >
                      🎲 {t("lucky.again")}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {rolled && !item && (
              <p className="text-center font-mono text-[0.8rem] text-muted">{t("lucky.none")}</p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
