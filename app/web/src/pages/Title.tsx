import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AvailabilityRow } from "../components/AvailabilityRow";
import { DiscoveryCard } from "../components/DiscoveryCard";
import { EmptyState } from "../components/EmptyState";
import { PlayButton } from "../components/PlayButton";
import { countryName, RegionSwitcher } from "../components/RegionSwitcher";
import { SeasonAvailabilityBlock } from "../components/SeasonAvailabilityBlock";
import { SeasonTracker } from "../components/SeasonTracker";
import { api } from "../lib/api";
import { usePlayer } from "../stores/player";

export function TitlePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const player = usePlayer();
  const qc = useQueryClient();
  const [region, setRegion] = useState("");
  const query = useQuery({
    queryKey: ["title", id, region],
    queryFn: () => api.title(Number(id), region),
    enabled: !!id,
  });
  const similar = useQuery({
    queryKey: ["similar", id, region],
    queryFn: () => api.similar(Number(id), region),
    enabled: !!id,
  });
  const watchlist = useMutation({
    mutationFn: (action: "add" | "remove") =>
      action === "add" ? api.addToWatchlist(Number(id)) : api.removeFromWatchlist(Number(id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["title", id] });
      qc.invalidateQueries({ queryKey: ["shelf"] });  // the rail changes too
    },
  });

  if (query.isError) {
    return (
      <EmptyState
        message="Title not found. It may have rotated out of the catalog on the last sync."
        action={
          <div className="flex items-center gap-3">
            <Link to="/" className="inline-block rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0">
              Back to shelf
            </Link>
            <Link to="/search" className="inline-block rounded-[6px] border border-line px-4 py-2 hover:bg-bg2">
              Search
            </Link>
          </div>
        }
      />
    );
  }
  if (!query.data) {
    return (
      <div className="flex gap-8">
        <div className="aspect-[2/3] w-56 animate-pulse rounded-[10px] bg-bg1" />
        <div className="flex-1 space-y-4 pt-2">
          <div className="h-8 w-1/2 animate-pulse rounded bg-bg1" />
          <div className="h-4 w-1/3 animate-pulse rounded bg-bg1" />
        </div>
      </div>
    );
  }

  const t = query.data;
  const meta = [
    t.year,
    t.runtime_minutes ? `${t.runtime_minutes} min` : null,
    t.genres.join(" · ") || null,
  ]
    .filter(Boolean)
    .join(" · ");
  // Rating cluster: real IMDb/RT/Metacritic when OMDb is on, else TMDB's score.
  const ratingPills: { label: string; value: string }[] = [];
  if (t.ratings.imdb) ratingPills.push({ label: "IMDb", value: t.ratings.imdb.toFixed(1) });
  if (t.ratings.rt) ratingPills.push({ label: "RT", value: t.ratings.rt });
  if (t.ratings.metacritic) ratingPills.push({ label: "Metacritic", value: t.ratings.metacritic });
  if (t.rating) ratingPills.push({ label: "TMDB", value: t.rating.toFixed(1) });

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="hoverable mb-6 rounded-[6px] px-2 py-1 font-mono text-[0.8rem] text-muted hover:bg-bg2 hover:text-ink"
      >
        ← Back
      </button>

      <div className="flex flex-col gap-8 md:flex-row">
        <div className={`w-48 shrink-0 self-start md:w-60 ${t.owned ? "lit" : "dimmed"} rounded-[10px]`}>
          {t.poster ? (
            <img src={t.poster} alt={t.title} className="poster w-full rounded-[10px]" />
          ) : (
            <div className="flex aspect-[2/3] items-center justify-center rounded-[10px] bg-bg1 p-4 text-center font-display text-muted">
              {t.title}
            </div>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[2.4rem] font-bold leading-tight">{t.title}</h1>
          {meta && <p className="mt-1 font-mono text-[0.8rem] text-muted">{meta}</p>}
          {ratingPills.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {ratingPills.map((p) => (
                <span key={p.label}
                      className="rounded-full border border-line px-2 py-0.5 font-mono text-[0.75rem]">
                  <span className="text-muted">{p.label}</span>{" "}
                  <span className="text-ink">{p.value}</span>
                </span>
              ))}
            </div>
          )}
          {t.overview && <p className="clamp-3 mt-4 max-w-2xl text-[0.95rem] text-ink/90">{t.overview}</p>}

          {t.keywords?.length > 0 && (
            <div className="mt-3 flex max-w-2xl flex-wrap gap-1.5">
              {t.keywords.map((k) => (
                <span key={k}
                      className="rounded-full border border-line px-2 py-0.5 font-mono text-[0.7rem] text-muted">
                  {k}
                </span>
              ))}
            </div>
          )}

          {/* Exactly one primary Play button, routed per the M3 chain — movies/TV
              only ever get deep-link options (DRM stays browse-and-link). */}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            {t.play.default && (
              <PlayButton
                playback={t.play}
                title={t.title}
                subtitle={t.genres.slice(0, 2).join(" · ")}
                artwork={t.poster}
              />
            )}
            {/* Save it yourself — until now the list could only arrive from the
                companion tool's import, so there was no way to say "later". */}
            <button
              disabled={watchlist.isPending}
              onClick={() =>
                watchlist.mutate(t.in_watchlist ? "remove" : "add")
              }
              className={`rounded-[6px] border px-4 py-2 text-[0.9rem] disabled:opacity-50 ${
                t.in_watchlist
                  ? "border-owned/50 bg-owned/10 text-owned hover:bg-owned/20"
                  : "border-line hover:bg-bg2"
              }`}
            >
              {t.in_watchlist ? "✓ On your list" : "+ Want to watch"}
            </button>
            {t.trailer_youtube_id && (
              <button
                onClick={() =>
                  player.play({
                    title: `${t.title} — Trailer`,
                    subtitle: "Trailer · YouTube",
                    artwork: t.poster,
                    options: [{
                      engine: "youtube", service_key: "youtube", label: "YouTube",
                      kind: "trailer", payload: { video_id: t.trailer_youtube_id! },
                    }],
                  })
                }
                className="rounded-[6px] border border-line px-4 py-2 text-[0.9rem] hover:bg-bg2"
              >
                <span className="mr-1 text-[color:var(--play)]">▶</span> Trailer
              </button>
            )}
          </div>

          {t.cast?.length > 0 && (
            <section className="mt-8 max-w-2xl">
              <h2 className="mb-3 font-mono text-[0.75rem] tracking-widest text-muted">CAST</h2>
              <div className="flex gap-3 overflow-x-auto pb-2">
                {t.cast.map((c, i) => {
                  const inner = (
                    <>
                      {c.profile ? (
                        <img src={c.profile} alt="" loading="lazy"
                             className="mx-auto h-[76px] w-[76px] rounded-full object-cover" />
                      ) : (
                        <div className="mx-auto flex h-[76px] w-[76px] items-center justify-center rounded-full bg-bg2 text-muted">
                          {c.name.slice(0, 1)}
                        </div>
                      )}
                      <p className="mt-1 truncate text-[0.72rem] leading-tight" title={c.name}>{c.name}</p>
                      {c.character && (
                        <p className="truncate font-mono text-[0.62rem] text-muted" title={c.character}>
                          {c.character}
                        </p>
                      )}
                    </>
                  );
                  // Clickable → person page when TMDB gave us the person id.
                  return c.id != null ? (
                    <Link key={`${c.name}-${i}`} to={`/person/${c.id}`}
                          className="hoverable w-[76px] shrink-0 rounded-[8px] p-1 text-center hover:bg-bg2">
                      {inner}
                    </Link>
                  ) : (
                    <div key={`${c.name}-${i}`} className="w-[76px] shrink-0 p-1 text-center">
                      {inner}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Shows only: manual episode progress (no playback signal exists). */}
          {t.media_type === "tv" && <SeasonTracker itemId={t.id} />}

          {/* Availability block — the product's money shot (Part 2 §4.4). */}
          <div className="mt-8 max-w-2xl space-y-6">
            {t.regions.length > 1 && (
              <div className="flex items-center gap-2 font-mono text-[0.75rem] text-muted">
                <span>availability in</span>
                <RegionSwitcher regions={t.regions} active={t.country} onSelect={setRegion} />
              </div>
            )}
            {t.badges.length === 0 && (
              // A real state, not an empty block (plan: failure modes) — and with
              // multi-region data it becomes information, not a shrug.
              <div className="rounded-[10px] border border-line bg-bg1 px-4 py-3">
                <p className="text-[0.95rem]">Not streaming in {countryName(t.country)} right now.</p>
                <p className="mt-1 text-[0.875rem] text-muted">
                  {t.world.length > 0
                    ? "It is streaming in other regions — see below. Availability refreshes nightly."
                    : "No provider reports this title anywhere yet. It may arrive on a service later — availability refreshes nightly."}
                </p>
                {/* Nothing streams it at all — the strongest case for handing it
                    to your own pipeline, so the button must reach here too. */}
                {t.request_url && (
                  <a
                    href={t.request_url}
                    target="_blank"
                    rel="noreferrer"
                    title="Open this title in your own Overseerr/Jellyseerr"
                    className="mt-3 inline-block rounded-[6px] bg-owned px-4 py-2.5 text-[0.9rem] font-medium text-bg0"
                  >
                    ↗ Request on Seer
                  </a>
                )}
              </div>
            )}
            {t.badges.length > 0 && (
            <div>
              <h2 className="mb-2 font-mono text-[0.75rem] tracking-widest text-owned">
                ON YOUR SERVICES
              </h2>
              {t.on_your_services.length > 0 ? (
                <div className="space-y-2">
                  {t.on_your_services.map((b) => (
                    <AvailabilityRow key={`${b.service_key}-${b.offer_type}`} badge={b} />
                  ))}
                  {/* You can watch it now but not for long. Quieter than the
                      empty-state button — this is a hedge, not the main action. */}
                  {t.leaving_soon && t.request_url && (
                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[6px] border border-line bg-bg1 px-3 py-2.5">
                      <span className="text-[0.875rem] text-muted">
                        Leaving {t.leaving_soon.service_name}
                        {t.leaving_soon.note ? ` — ${t.leaving_soon.note}` : " soon"}.
                      </span>
                      <a
                        href={t.request_url}
                        target="_blank"
                        rel="noreferrer"
                        title="Open this title in your own Overseerr/Jellyseerr"
                        className="hoverable shrink-0 rounded-[6px] border border-owned/50 px-3 py-1.5 font-mono text-[0.8rem] text-owned hover:bg-owned/15"
                      >
                        ↗ Request on Seer
                      </a>
                    </div>
                  )}
                </div>
              ) : (
                // Nothing you pay for carries it. If you self-host a request
                // pipeline, that IS the action here — so it sits beside the
                // message as a primary button rather than buried below.
                <div className="flex flex-wrap items-center gap-3">
                  <p className="min-w-0 flex-1 rounded-[6px] border border-line bg-bg1 px-3 py-2.5 text-[0.875rem] text-muted">
                    Not on any service you've ticked. Update your services in Settings, or see below.
                  </p>
                  {t.request_url && (
                    <a
                      href={t.request_url}
                      target="_blank"
                      rel="noreferrer"
                      title="Open this title in your own Overseerr/Jellyseerr"
                      className="shrink-0 rounded-[6px] bg-owned px-4 py-2.5 text-[0.9rem] font-medium text-bg0"
                    >
                      ↗ Request on Seer
                    </a>
                  )}
                </div>
              )}
            </div>
            )}

            {/* Only renders when the seasons actually differ from each other. */}
            {t.media_type === "tv" && <SeasonAvailabilityBlock itemId={t.id} region={region} />}

            {t.badges.length > 0 && (
            <div>
              <h2 className="mb-2 font-mono text-[0.75rem] tracking-widest text-muted">ELSEWHERE</h2>
              {t.elsewhere.length > 0 ? (
                <div className="space-y-2">
                  {t.elsewhere.map((b) => (
                    <AvailabilityRow key={`${b.service_key}-${b.offer_type}`} badge={b} />
                  ))}
                </div>
              ) : (
                <p className="rounded-[6px] border border-line bg-bg1 px-3 py-2.5 text-[0.875rem] text-muted">
                  No other streaming source reported for your country.
                </p>
              )}
            </div>
            )}

            {/* Display-only world availability — the map, not the plane ticket. */}
            {t.world.length > 0 && (
              <details className="group rounded-[10px] border border-line bg-bg1">
                <summary className="cursor-pointer list-none px-4 py-3 font-mono text-[0.75rem] tracking-widest text-muted hover:text-ink">
                  <span className="mr-2 inline-block transition-transform group-open:rotate-90">▸</span>
                  IN OTHER REGIONS · {t.world.length} countr{t.world.length === 1 ? "y" : "ies"}
                </summary>
                <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 px-4 pb-4 sm:grid-cols-2">
                  {t.world.map((w) => (
                    <div key={w.country} className="flex gap-2 font-mono text-[0.75rem]">
                      <span className="w-28 shrink-0 truncate text-owned" title={countryName(w.country)}>
                        {countryName(w.country)}
                      </span>
                      <span className="min-w-0 truncate text-muted" title={w.services.join(", ")}>
                        {w.services.join(", ")}{w.more > 0 ? ` +${w.more}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </div>
        </div>
      </div>

      {(() => {
        // Two soft sections: titles confirmed on your services vs the rest.
        // Recommendations aren't all imported, so the rest have *unknown*
        // availability — labelled "more like this", never "not on my services".
        const items = similar.data?.items ?? [];
        if (items.length === 0) return null;
        const mine = items.filter((i) => i.owned);
        const rest = items.filter((i) => !i.owned);
        const rail = (list: typeof items) => (
          <div className="flex gap-4 overflow-x-auto pb-2">
            {list.map((it) => (
              <div key={`${it.media_type}-${it.tmdb_id ?? it.id}`} className="w-[130px] shrink-0 sm:w-[150px]">
                <DiscoveryCard item={it} />
              </div>
            ))}
          </div>
        );
        return (
          <>
            {mine.length > 0 && (
              <section className="mt-12">
                <h2 className="mb-3 font-mono text-[0.75rem] tracking-widest text-owned">
                  SIMILAR · ON YOUR SERVICES
                </h2>
                {rail(mine)}
              </section>
            )}
            {rest.length > 0 && (
              <section className="mt-12">
                <h2 className="mb-3 font-mono text-[0.75rem] tracking-widest text-muted">
                  MORE LIKE THIS
                </h2>
                {rail(rest)}
              </section>
            )}
          </>
        );
      })()}
    </div>
  );
}
