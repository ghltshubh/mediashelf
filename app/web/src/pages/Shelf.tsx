import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BecauseRail } from "../components/BecauseRail";
import { EmptyState } from "../components/EmptyState";
import { FilterChips } from "../components/FilterChips";
import { LuckyDice } from "../components/LuckyDice";
import { GenreSelect } from "../components/GenreSelect";
import { MediaCard } from "../components/MediaCard";
import { MusicRail } from "../components/MusicRail";
import { RailSection } from "../components/RailSection";
import { RegionSwitcher } from "../components/RegionSwitcher";
import { SortSelect } from "../components/SortSelect";
import { StatusBanner } from "../components/StatusBanner";
import { api } from "../lib/api";
import { useT } from "../lib/i18n";
import { fmtNumber, useLocale } from "../lib/locale";
import { ageOf, daysSince } from "../lib/time";
import { MusicTab } from "./MusicTab";
import { Podcasts } from "./Podcasts";

const TABS = [
  ["all", "All"],
  ["movies", "Movies"],
  ["shows", "Shows"],
  ["music", "Music"],
  ["podcasts", "Podcasts"],
] as const;

const TAB_TYPE: Record<string, string> = { movies: "movie", shows: "tv" };

function SkeletonRail() {
  return (
    <div className="mb-10">
      <div className="mb-3 h-6 w-32 animate-pulse rounded bg-bg2" />
      <div className="flex gap-4 overflow-hidden">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="w-[148px] shrink-0 sm:w-[168px]">
            <div className="aspect-[2/3] animate-pulse rounded-[10px] bg-bg1" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function Shelf() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const locale = useLocale();
  const t = useT();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab")! : "all";
  const [view, setView] = useState<"categories" | "services">("categories");
  const [region, setRegion] = useState("");
  const [filter, setFilter] = useState<string | null>(null);
  const [sort, setSort] = useState("popularity");
  const [genre, setGenre] = useState("");
  const mediaType = TAB_TYPE[tab] ?? "";

  // "On my services" is the default chip once anything is subscribed (§4.2);
  // filtering happens server-side so counts and "see all" always agree.
  const shelfKnown = useQuery({
    queryKey: ["shelf-meta"],
    queryFn: () => api.shelf("categories", "", "all"),
    enabled: !!settings.data?.tmdb_api_key_set,
    staleTime: 60_000,
  });
  const hasSubs = (shelfKnown.data?.stats.subscribed ?? 0) > 0;

  // Home is the curated landing: the full shelf (lit vs dimmed), no filter
  // controls — so nothing shifts around. Movies/Shows are the browsing tabs
  // and carry the whole toolbar, pinned at the top (no music rail above it).
  const isHome = tab === "all";
  const active = isHome ? "all" : (filter ?? (hasSubs ? "mine" : "all"));
  const effView = isHome ? "categories" : view;
  const effRegion = isHome ? "" : region;
  const effSort = isHome ? "popularity" : sort;
  const effGenre = isHome ? "" : genre;

  const shelf = useQuery({
    queryKey: ["shelf", effView, effRegion, active, mediaType, effSort, effGenre],
    queryFn: () => api.shelf(effView, effRegion, active, mediaType, effSort, effGenre),
    enabled: !!settings.data?.tmdb_api_key_set && shelfKnown.isSuccess
      && tab !== "music" && tab !== "podcasts",
    refetchInterval: (q) => (q.state.data?.sync.status === "running" ? 4000 : false),
  });

  const showMusicRail = isHome;

  const data = shelf.data;

  if (settings.data && !settings.data.tmdb_api_key_set) {
    return (
      <EmptyState
        message={t("empty.tmdb")}
        action={
          <Link
            to="/onboarding"
            className="inline-block rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
          >
            {t("empty.tmdbCta")}
          </Link>
        }
      />
    );
  }

  // Media-type tabs: scoping within the one shelf, not navigation (design plan).
  // Sticky: content scrolls under it; solid bg so cards never bleed through.
  const tabBar = (
    <div
      role="tablist"
      aria-label="Media type"
      className="sticky top-0 z-30 -mx-5 mb-5 flex gap-1 border-b border-line bg-bg0 px-5 pt-1
                 min-[700px]:-mx-8 min-[700px]:px-8"
    >
      {TABS.map(([key]) => (
        <button
          key={key}
          role="tab"
          aria-selected={tab === key}
          onClick={() => setParams(key === "all" ? {} : { tab: key }, { replace: true })}
          className={`-mb-px border-b-2 px-4 py-2 font-display text-[1.05rem] font-semibold tracking-tight ${
            tab === key
              ? "border-[var(--owned)] text-owned"
              : "border-transparent text-muted hover:text-ink"
          }`}
        >
          {t(`tab.${key}`)}
        </button>
      ))}
      {/* Feeling lucky — a random pick from your services, from anywhere on the shelf. */}
      <span className="ml-auto flex items-center">
        <LuckyDice genres={shelfKnown.data?.all_genres ?? []} />
      </span>
    </div>
  );

  if (tab === "music") {
    return (
      <div>
        {tabBar}
        <MusicTab />
      </div>
    );
  }

  if (tab === "podcasts") {
    return (
      <div>
        {tabBar}
        <Podcasts />
      </div>
    );
  }

  if (!data) {
    return (
      <div>
        {tabBar}
        <div className="mb-6 h-4 w-72 animate-pulse rounded bg-bg1" />
        <SkeletonRail />
        <SkeletonRail />
      </div>
    );
  }

  return (
    <div>
      {tabBar}
      {data.sync.status === "running" && (
        <StatusBanner kind="info">
          Catalog sync running{data.sync.detail ? ` — ${data.sync.detail}` : ""}…
        </StatusBanner>
      )}
      {/* Degrade, never blank: the last-synced catalog keeps serving, with its age named. */}
      {data.sync.status === "error" && data.sync.error_kind === "auth" && (
        <StatusBanner kind="danger">
          TMDB rejected your API key — showing the catalog from{" "}
          {ageOf(data.synced_at) ?? "the last sync"}.{" "}
          <Link to="/settings#keys" className="underline underline-offset-2">
            Fix it in Settings → Keys
          </Link>
        </StatusBanner>
      )}
      {data.sync.status === "error" && data.sync.error_kind !== "auth" && (
        <StatusBanner kind="info">
          TMDB is unreachable — showing the catalog from {ageOf(data.synced_at) ?? "the last sync"}.
          Retrying automatically.
        </StatusBanner>
      )}
      {data.sync.status === "idle" && (daysSince(data.synced_at) ?? 0) > 2 && (
        <StatusBanner kind="info">Catalog last updated {ageOf(data.synced_at)}.</StatusBanner>
      )}

      {/* Home: the curated shelf, controls-free — the music rail leads, then
          personalized recommendations seeded by the watchlist. */}
      {showMusicRail && <MusicRail />}
      {isHome && <BecauseRail />}

      {/* Stats + toolbar belong to the browsing tabs; Home stays pure rails. */}
      {!isHome && (
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[0.8rem] text-muted">
          {t("stats.line", {
            titles: fmtNumber(data.stats.titles, locale),
            services: data.stats.services,
            subscribed: data.stats.subscribed,
          })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <GenreSelect value={genre} genres={data.all_genres} onChange={setGenre} />
          <SortSelect value={sort} onChange={setSort} />
          <RegionSwitcher regions={data.regions} active={data.country} onSelect={setRegion} />
          <div role="group" aria-label="Shelf view" className="flex rounded-[6px] border border-line">
            {(["categories", "services"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={view === v}
                className={`px-3 py-1 font-mono text-[0.75rem] first:rounded-l-[5px] last:rounded-r-[5px] ${
                  view === v ? "bg-owned/15 text-owned" : "text-muted hover:bg-bg2"
                }`}
              >
                {v === "categories" ? t("view.categories") : t("view.services")}
              </button>
            ))}
          </div>
        </div>
      </div>
      )}

      {!isHome && (
        <div className="mb-8">
          <FilterChips
            // Ownership only — per-service browsing lives in the by-service view,
            // music in the Music tab (chip row stays fixed-size as subs grow).
            chips={[
              { key: "all", label: t("chip.all") },
              { key: "mine", label: t("chip.mine") },
              { key: "elsewhere", label: t("chip.elsewhere") },
            ]}
            active={active}
            onSelect={setFilter}
          />
        </div>
      )}

      {data.rails.length === 0 && data.stats.titles === 0 && data.sync.status !== "running" && (
        <EmptyState
          message={t("empty.catalog")}
          action={
            <button
              onClick={() => api.sync().then(() => shelf.refetch())}
              className="rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
            >
              {t("empty.syncNow")}
            </button>
          }
        />
      )}
      {data.rails.length === 0 && data.stats.titles > 0 && (
        <EmptyState
          message={active === "mine" ? t("empty.mine") : t("empty.noMatch")}
          action={
            active === "mine" ? (
              <Link
                to="/settings"
                className="inline-block rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
              >
                {t("empty.mineCta")}
              </Link>
            ) : (
              <button
                onClick={() => {
                  setFilter("all");
                  setGenre("");
                }}
                className="rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
              >
                {t("empty.showAll")}
              </button>
            )
          }
        />
      )}

      {data.rails.map((rail) => (
        <RailSection
          key={rail.key}
          label={rail.label}
          railKey={rail.key}
          total={rail.total}
          shown={rail.items.length}
          region={data.country}
          filter={active}
          mediaType={mediaType}
          genre={effGenre}
        >
          {rail.items.map((item) => (
            <MediaCard key={`${rail.key}-${item.id}`} item={item} />
          ))}
        </RailSection>
      ))}
    </div>
  );
}
