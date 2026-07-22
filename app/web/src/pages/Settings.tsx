import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ConnectionCard } from "../components/ConnectionCard";
import { KeyValueMono } from "../components/KeyValueMono";
import { RegionPicker } from "../components/RegionPicker";
import { ServiceTile } from "../components/ServiceTile";
import { StatusBanner } from "../components/StatusBanner";
import { api, type Service } from "../lib/api";
import { ageOf } from "../lib/time";

const SECTIONS = [
  ["services", "Services"],
  ["accounts", "Accounts"],
  ["keys", "Keys"],
  ["playback", "Playback"],
  ["plugins", "Plugins"],
  ["about", "About"],
] as const;

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 border-b border-line py-8 last:border-b-0">
      <h2 className="mb-4 font-display text-[1.25rem] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

const inputCls =
  "mt-1 w-full rounded-[6px] border border-line bg-bg1 px-3 py-2 font-mono text-[0.875rem] placeholder:text-muted/50";
const primaryBtn = "rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0 disabled:opacity-40";
const quietBtn =
  "rounded-[6px] border border-line px-4 py-2 text-[0.9rem] hover:bg-bg2 disabled:opacity-40";

function OmdbKeyForm({ onSaved }: { onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.updateSettings({ omdb_api_key: key.trim() }),
    onSuccess: () => {
      setKey("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      onSaved();
    },
    onError: (e: Error) => setError(e.message),
  });
  return (
    <div className="mt-3">
      <div className="flex max-w-lg items-end gap-3">
        <label className="flex-1">
          <span className="font-mono text-[0.75rem] text-muted">OMDB API KEY</span>
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)}
                 className={inputCls} />
        </label>
        <button disabled={!key.trim() || save.isPending} onClick={() => save.mutate()}
                className={primaryBtn}>
          {save.isPending ? "Checking…" : "Save"}
        </button>
      </div>
      {error && <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}
    </div>
  );
}


function GoogleKeysForm({ onSaved }: { onSaved: () => void }) {
  const queryClient = useQueryClient();
  const [id, setId] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.updateSettings({ google_client_id: id, google_client_secret: secret }),
    onSuccess: () => {
      setId("");
      setSecret("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      onSaved();
    },
    onError: (e: Error) => setError(e.message),
  });
  return (
    <div className="mt-3">
      <div className="flex max-w-lg flex-wrap items-end gap-3">
        <label className="min-w-40 flex-1">
          <span className="font-mono text-[0.75rem] text-muted">CLIENT ID</span>
          <input value={id} onChange={(e) => setId(e.target.value)} className={inputCls} />
        </label>
        <label className="min-w-40 flex-1">
          <span className="font-mono text-[0.75rem] text-muted">CLIENT SECRET</span>
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)}
                 className={inputCls} />
        </label>
        <button disabled={!id.trim() || !secret.trim() || save.isPending}
                onClick={() => save.mutate()} className={primaryBtn}>
          Save
        </button>
      </div>
      {error && <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}
    </div>
  );
}


function AddServiceForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [kind, setKind] = useState("video");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.createService({ name, homepage_url: url, kind }),
    onSuccess: () => {
      setName("");
      setUrl("");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["services"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="mt-6 rounded-[10px] border border-line bg-bg1 p-4">
      <h3 className="font-display text-[1rem] font-semibold">Add a service</h3>
      <p className="mt-1 text-[0.85rem] text-muted">
        For services we don't know. It joins your checklist and opens via its site — availability
        per title can't be shown (no data source knows its catalog).
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="min-w-40 flex-1">
          <span className="font-mono text-[0.75rem] text-muted">NAME</span>
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls}
                 placeholder="Kanopy" />
        </label>
        <label className="min-w-56 flex-[2]">
          <span className="font-mono text-[0.75rem] text-muted">HOMEPAGE URL</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} className={inputCls}
                 placeholder="https://www.kanopy.com" />
        </label>
        <label>
          <span className="font-mono text-[0.75rem] text-muted">KIND</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}
                  className={`${inputCls} w-auto`}>
            <option value="video">video</option>
            <option value="music">music</option>
            <option value="podcast">podcast</option>
          </select>
        </label>
        <button
          disabled={!name.trim() || !url.trim() || create.isPending}
          onClick={() => create.mutate()}
          className={primaryBtn}
        >
          Add
        </button>
      </div>
      {error && <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}
    </div>
  );
}

export function Settings() {
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const services = useQuery({ queryKey: ["services"], queryFn: api.services });
  const connections = useQuery({ queryKey: ["connections"], queryFn: api.connections });
  const [connectError, setConnectError] = useState<string | null>(params.get("connect_error"));
  const justConnected = params.get("connected");
  const [appleToken, setAppleToken] = useState("");
  const [appleError, setAppleError] = useState<string | null>(null);
  const [serviceQuery, setServiceQuery] = useState("");

  const saveApple = useMutation({
    mutationFn: () => api.setAppleToken(appleToken),
    onSuccess: () => {
      setAppleToken("");
      setAppleError(null);
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
    onError: (e: Error) => setAppleError(e.message),
  });

  const setPreferred = useMutation({
    mutationFn: (v: string) =>
      api.updateSettings({ preferred_music_service: v as "auto" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });

  const [newKey, setNewKey] = useState("");
  const [keyError, setKeyError] = useState<string | null>(null);
  const [spotifyId, setSpotifyId] = useState("");
  const [spotifySecret, setSpotifySecret] = useState("");
  const [spotifyError, setSpotifyError] = useState<string | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["settings"] });
    queryClient.invalidateQueries({ queryKey: ["shelf"] });
  };

  const toggle = useMutation({
    mutationFn: ({ id, subscribed }: { id: number; subscribed: boolean }) =>
      api.setSubscription(id, subscribed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["services"] });
      queryClient.invalidateQueries({ queryKey: ["shelf"] });
    },
  });

  const removeService = useMutation({
    mutationFn: (id: number) => api.deleteService(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["services"] }),
  });

  const saveKey = useMutation({
    mutationFn: () => api.updateSettings({ tmdb_api_key: newKey.trim() }),
    onSuccess: () => {
      setNewKey("");
      setKeyError(null);
      invalidate();
    },
    onError: (e: Error) => setKeyError(e.message),
  });

  const saveCountry = useMutation({
    mutationFn: (c: string) => api.updateSettings({ country: c }),
    onSuccess: invalidate,
    onError: (e: Error) => setKeyError(e.message),
  });

  const saveRegions = useMutation({
    mutationFn: (list: string[]) => api.updateSettings({ extra_countries: list }),
    onSuccess: invalidate,
    onError: (e: Error) => setKeyError(e.message),
  });

  const saveDepth = useMutation({
    mutationFn: (pages: number) => api.updateSettings({ catalog_pages: pages }),
    onSuccess: invalidate,
    onError: (e: Error) => setKeyError(e.message),
  });

  const syncNow = useMutation({ mutationFn: api.sync, onSuccess: invalidate });

  const saveSpotify = useMutation({
    mutationFn: () =>
      api.updateSettings({
        spotify_client_id: spotifyId.trim(),
        spotify_client_secret: spotifySecret.trim(),
      }),
    onSuccess: () => {
      setSpotifyId("");
      setSpotifySecret("");
      setSpotifyError(null);
      invalidate();
    },
    onError: (e: Error) => setSpotifyError(e.message),
  });

  const dismissRestore = useMutation({
    mutationFn: () => api.updateSettings({ dismiss_restore_notice: true }),
    onSuccess: invalidate,
  });

  const importDb = useMutation({
    mutationFn: (f: File) => api.importBackup(f),
    onSuccess: () => {
      setImportMsg("Database imported. Reloading…");
      setTimeout(() => window.location.reload(), 800);
    },
    onError: (e: Error) => setImportMsg(e.message),
  });

  const s = settings.data;
  const list = services.data ?? [];
  const q = serviceQuery.trim().toLowerCase();
  const searching = q.length > 0;
  const m = (sv: Service) => !searching || sv.name.toLowerCase().includes(q);

  const checklist = list.filter((sv) => sv.kind !== "meta" && !sv.is_channel && !sv.custom);
  // While browsing, subscribed services live only in the pinned YOUR SERVICES;
  // while searching, they show in-group too (search is a lookup, not a summary).
  const notPinned = (sv: Service) => searching || !sv.subscribed;
  const subscribed = checklist.filter((sv) => sv.subscribed && m(sv));
  const connect = checklist.filter((sv) => sv.integration_kind === "connector" && m(sv) && notPinned(sv));
  const watchlist = checklist.filter((sv) => sv.integration_kind === "watchlist" && m(sv) && notPinned(sv));
  const restVideo = checklist.filter((sv) => !sv.featured && sv.kind === "video" && m(sv) && notPinned(sv));
  const restMusic = checklist.filter((sv) => !sv.featured && sv.kind === "music" && m(sv) && notPinned(sv));
  const restPodcast = checklist.filter((sv) => !sv.featured && sv.kind === "podcast" && m(sv) && notPinned(sv));
  const channels = list.filter((sv) => sv.is_channel && m(sv) && notPinned(sv));
  const customServices = list.filter((sv) => sv.custom);

  const tileAction = (sv: Service) => {
    if (sv.integration_kind === "watchlist") {
      const done = sv.watchlist_count > 0;
      return {
        label: done ? `${sv.watchlist_count} imported · update` : "set up watchlist import",
        href: `http://127.0.0.1:8765/#${sv.key}`, external: true, done,
      };
    }
    if (sv.integration_kind === "connector") {
      return { label: sv.connected ? "connected · manage" : "connect", href: "#accounts",
               done: sv.connected };
    }
    return undefined;
  };
  const tile = (sv: Service, withAction = false) => (
    <ServiceTile key={sv.id} service={sv}
      onToggle={(sub) => toggle.mutate({ id: sv.id, subscribed: sub })}
      action={withAction ? tileAction(sv) : undefined} />
  );
  const grid = (items: Service[], withAction = false) => (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{items.map((sv) => tile(sv, withAction))}</div>
  );
  const group = (label: string, items: Service[], note: string) =>
    items.length > 0 && (
      <details key={`${label}-${searching ? "q" : "n"}`} {...(searching ? { open: true } : {})}
        className="group mt-4 rounded-[10px] border border-line bg-bg1">
        <summary className="cursor-pointer list-none px-4 py-3 font-mono text-[0.75rem] tracking-widest text-muted hover:text-ink">
          <span className="mr-2 inline-block transition-transform group-open:rotate-90">▸</span>
          {label} · {items.length}
          <span className="ml-2 normal-case tracking-normal opacity-70">{note}</span>
        </summary>
        <div className="px-4 pb-4">{grid(items)}</div>
      </details>
    );

  return (
    <div className="flex gap-10">
      <nav aria-label="Settings sections" className="sticky top-6 hidden h-fit w-40 shrink-0 md:block">
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="hoverable block rounded-[6px] px-3 py-1.5 text-[0.875rem] text-muted hover:bg-bg2 hover:text-ink"
          >
            {label}
          </a>
        ))}
      </nav>

      <div className="min-w-0 max-w-3xl flex-1">
        <h1 className="font-display text-[1.6rem] font-bold">Settings</h1>

        {s?.restore_notice && (
          <div className="mt-4">
            <StatusBanner kind="quota">
              {s.restore_notice}{" "}
              <button onClick={() => dismissRestore.mutate()} className="underline underline-offset-2">
                Dismiss
              </button>
            </StatusBanner>
          </div>
        )}

        <Section id="services" title="Services">
          <p className="mb-3 text-[0.9rem] text-muted">
            Tick what you subscribe to — this drives the lit/dimmed split everywhere. No logins needed.
          </p>
          <input
            value={serviceQuery}
            onChange={(e) => setServiceQuery(e.target.value)}
            placeholder="🔍  filter services…"
            aria-label="Filter services"
            className="mb-4 w-full max-w-sm rounded-[6px] border border-line bg-bg1 px-3 py-2 text-[0.9rem] outline-none placeholder:text-muted/60 focus:border-owned/60"
          />

          {!searching && subscribed.length > 0 && (
            <div className="mb-5">
              <p className="mb-2 font-mono text-[0.7rem] tracking-widest text-muted">
                YOUR SERVICES · {subscribed.length}
              </p>
              {grid(subscribed, true)}
            </div>
          )}

          {(connect.length > 0 || watchlist.length > 0) && (
            <div>
              <p className="mb-2 font-mono text-[0.7rem] tracking-widest text-muted">
                DEEPER INTEGRATION
              </p>
              {connect.length > 0 && (
                <>
                  <p className="mb-1.5 font-mono text-[0.65rem] text-muted/70">
                    connect · library sync &amp; in-app playback
                  </p>
                  {grid(connect, true)}
                </>
              )}
              {watchlist.length > 0 && (
                <>
                  <p className="mb-1.5 mt-3 font-mono text-[0.65rem] text-muted/70">
                    watchlist import · pull your "My List" into the shelf
                  </p>
                  {grid(watchlist, true)}
                </>
              )}
            </div>
          )}

          {group("ALL VIDEO SERVICES", restVideo, "browse & deep-link — tick any you subscribe to")}
          {group("ALL MUSIC SERVICES", restMusic, "browse & deep-link")}
          {group("PODCASTS", restPodcast, "")}
          {group("CHANNELS & ADD-ONS", channels,
            "separate purchases sold through Amazon / Apple TV / Roku")}

          {searching && subscribed.length + connect.length + watchlist.length + restVideo.length +
            restMusic.length + restPodcast.length + channels.length === 0 && (
            <p className="mt-4 font-mono text-[0.8rem] text-muted">no services match “{serviceQuery}”</p>
          )}

          {!searching && customServices.length > 0 && (
            <div className="mt-4 space-y-1">
              {customServices.map((sv) => (
                <div key={sv.id} className="flex items-center gap-3 font-mono text-[0.8rem] text-muted">
                  <span>{sv.name}</span>
                  {sv.homepage_url && (
                    <a href={sv.homepage_url} target="_blank" rel="noreferrer"
                       className="text-owned hover:underline">
                      ↗ open
                    </a>
                  )}
                  <button
                    onClick={() => removeService.mutate(sv.id)}
                    className="text-[color:var(--danger)] hover:underline"
                  >
                    remove
                  </button>
                </div>
              ))}
            </div>
          )}
          {!searching && <AddServiceForm />}
        </Section>

        <Section id="accounts" title="Accounts">
          {justConnected && (
            <StatusBanner kind="info">
              {justConnected === "spotify" ? "Spotify" : "YouTube"} connected — library sync started.
            </StatusBanner>
          )}
          {connectError && (
            <StatusBanner kind="danger">
              {connectError}{" "}
              <button onClick={() => setConnectError(null)} className="underline underline-offset-2">
                Dismiss
              </button>
            </StatusBanner>
          )}
          <div className="space-y-3">
            {(connections.data ?? []).map((c) => (
              <ConnectionCard key={c.provider} conn={c} origin="settings" onError={setConnectError} />
            ))}
          </div>

          <div className="mt-6 rounded-[10px] border border-line bg-bg1 p-4">
            <h3 className="font-display text-[1rem] font-semibold">Google API (for YouTube)</h3>
            <p className="mt-1 max-w-lg text-[0.85rem] text-muted">
              YouTube needs your own free Google Cloud OAuth client: console.cloud.google.com →
              new project → enable "YouTube Data API v3" → OAuth consent screen (External, add
              yourself as test user) → Credentials → OAuth client ID (Web application) with
              redirect URI <code className="font-mono text-[0.8rem]">http://127.0.0.1:8000/oauth2callback</code>.
            </p>
            <p className="mt-2 font-mono text-[0.8rem] text-muted">
              status: {s?.google_configured ? "configured" : "not configured"}
            </p>
            <GoogleKeysForm onSaved={() => queryClient.invalidateQueries({ queryKey: ["connections"] })} />
          </div>

          <div className="mt-4 rounded-[10px] border border-line bg-bg1 p-4">
            <h3 className="font-display text-[1rem] font-semibold">Apple Music developer token</h3>
            <p className="mt-1 max-w-lg text-[0.85rem] text-muted">
              Optional — needs a paid Apple Developer account. Paste a MusicKit developer token
              (JWT); tokens last ≤6 months and MediaShelf warns 14 days before expiry.
            </p>
            <div className="mt-3 flex max-w-lg items-end gap-3">
              <label className="flex-1">
                <span className="font-mono text-[0.75rem] text-muted">DEVELOPER TOKEN</span>
                <input type="password" value={appleToken}
                       onChange={(e) => setAppleToken(e.target.value)} className={inputCls} />
              </label>
              <button
                disabled={!appleToken.trim() || saveApple.isPending}
                onClick={() => saveApple.mutate()}
                className={primaryBtn}
              >
                Save
              </button>
            </div>
            {appleError && (
              <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{appleError}</p>
            )}
          </div>
        </Section>

        <Section id="keys" title="Keys">
          {s?.sync.status === "error" && s.sync.error_kind === "auth" && (
            <StatusBanner kind="danger">TMDB rejected your key — {s.sync.detail}</StatusBanner>
          )}
          {s?.sync.status === "error" && s.sync.error_kind !== "auth" && (
            <StatusBanner kind="info">
              Last sync failed — {s.sync.detail}. Retrying automatically.
            </StatusBanner>
          )}
          <KeyValueMono
            pairs={[
              ["TMDB key", s?.tmdb_api_key_set ? (s.tmdb_api_key_masked ?? "set") : "not set"],
              ["Country", s?.country ?? "—"],
              ["Catalog updated", s?.synced_at ? (ageOf(s.synced_at) ?? s.synced_at) : "never"],
              ["Sync status", s?.sync.status ?? "—"],
            ]}
          />
          <div className="mt-4 flex max-w-lg flex-wrap items-end gap-3">
            <label className="min-w-56 flex-1">
              <span className="font-mono text-[0.75rem] text-muted">REPLACE TMDB KEY</span>
              <input type="password" value={newKey} onChange={(e) => setNewKey(e.target.value)}
                     className={inputCls} />
            </label>
            <button
              disabled={!newKey.trim() || saveKey.isPending}
              onClick={() => saveKey.mutate()}
              className={primaryBtn}
            >
              Save
            </button>
          </div>
          <div className="mt-6">
            <RegionPicker
              home={s?.country ?? "US"}
              extras={s?.extra_countries ?? []}
              onHomeChange={(code) => saveCountry.mutate(code)}
              onExtrasChange={(codes) => saveRegions.mutate(codes)}
              saving={saveRegions.isPending}
            />
          </div>
          <div className="mt-4 flex max-w-lg flex-wrap items-end gap-3">
            <label>
              <span className="font-mono text-[0.75rem] text-muted">CATALOG DEPTH</span>
              <select
                value={s?.catalog_pages ?? 5}
                onChange={(e) => saveDepth.mutate(Number(e.target.value))}
                className={`${inputCls} w-auto`}
              >
                <option value={3}>60 / category</option>
                <option value={5}>100 / category</option>
                <option value={10}>200 / category</option>
                <option value={15}>300 / category</option>
                <option value={25}>500 / category</option>
              </select>
            </label>
            <button
              disabled={!s?.tmdb_api_key_set || s?.sync.status === "running"}
              onClick={() => syncNow.mutate()}
              className={quietBtn}
            >
              {s?.sync.status === "running" ? "Syncing…" : "Sync now"}
            </button>
          </div>
          <p className="mt-2 max-w-lg font-mono text-[0.7rem] text-muted">
            extra regions cost zero additional TMDB calls — availability for every region arrives
            in the same response. changing either setting re-syncs automatically.
          </p>
          {keyError && (
            <p className="mt-3 font-mono text-[0.8rem] text-[color:var(--danger)]">{keyError}</p>
          )}

          <div className="mt-8 border-t border-line pt-6">
            <h3 className="font-display text-[1rem] font-semibold">OMDb API (IMDb / RT / Metacritic ratings)</h3>
            <p className="mt-1 max-w-lg text-[0.85rem] text-muted">
              Optional — enriches title pages with real IMDb, Rotten Tomatoes and Metacritic scores.
              Free key (1,000/day) at{" "}
              <a href="https://www.omdbapi.com/apikey.aspx" target="_blank" rel="noreferrer"
                 className="text-owned underline underline-offset-2">omdbapi.com/apikey.aspx</a>.
              Without it, cards and title pages still show TMDB's own score.
            </p>
            <p className="mt-2 font-mono text-[0.8rem] text-muted">
              status: {s?.omdb_configured ? "configured" : "not configured — TMDB scores only"}
            </p>
            <OmdbKeyForm onSaved={invalidate} />
          </div>

          <div className="mt-8 border-t border-line pt-6">
            <h3 className="font-display text-[1rem] font-semibold">Spotify API (music search)</h3>
            <p className="mt-1 max-w-lg text-[0.85rem] text-muted">
              Lets universal search cover music. Create your own free app at{" "}
              <a
                href="https://developer.spotify.com/dashboard"
                target="_blank"
                rel="noreferrer"
                className="text-owned underline underline-offset-2"
              >
                developer.spotify.com/dashboard
              </a>{" "}
              (~2 min) and paste its Client ID and Client Secret. Account connection for playback
              comes later (M3) — this is catalog search only.
            </p>
            <p className="mt-2 font-mono text-[0.8rem] text-muted">
              status: {s?.spotify_configured ? `configured (client ${s.spotify_client_id})` : "not configured"}
            </p>
            <div className="mt-3 flex max-w-lg flex-wrap items-end gap-3">
              <label className="min-w-40 flex-1">
                <span className="font-mono text-[0.75rem] text-muted">CLIENT ID</span>
                <input value={spotifyId} onChange={(e) => setSpotifyId(e.target.value)}
                       className={inputCls} />
              </label>
              <label className="min-w-40 flex-1">
                <span className="font-mono text-[0.75rem] text-muted">CLIENT SECRET</span>
                <input type="password" value={spotifySecret}
                       onChange={(e) => setSpotifySecret(e.target.value)} className={inputCls} />
              </label>
              <button
                disabled={!spotifyId.trim() || !spotifySecret.trim() || saveSpotify.isPending}
                onClick={() => saveSpotify.mutate()}
                className={primaryBtn}
              >
                {saveSpotify.isPending ? "Checking…" : "Save"}
              </button>
            </div>
            {spotifyError && (
              <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{spotifyError}</p>
            )}
          </div>
        </Section>

        <Section id="playback" title="Playback">
          <p className="mb-3 text-[0.9rem] text-muted">
            Where the play button routes by default. "Auto" follows the chain — Spotify
            (Premium) → Apple Music → YouTube → previews → deep link. A pinned service
            outranks the chain whenever it can actually play the track.
          </p>
          <label className="flex max-w-xs items-center gap-3">
            <span className="font-mono text-[0.75rem] text-muted">PREFERRED MUSIC SERVICE</span>
            <select
              value={s?.preferred_music_service ?? "auto"}
              onChange={(e) => setPreferred.mutate(e.target.value)}
              className={`${inputCls} mt-0 w-auto`}
            >
              <option value="auto">auto (chain)</option>
              <option value="spotify">Spotify</option>
              <option value="apple_music">Apple Music</option>
              <option value="youtube">YouTube</option>
            </select>
          </label>
        </Section>

        <Section id="plugins" title="Plugins">
          <KeyValueMono pairs={[["yt-dlp", "not detected — optional metadata plugin, arrives in M6"]]} />
          <div className="mt-4 rounded-[10px] border border-line bg-bg1 p-4">
            <h3 className="font-display text-[1rem] font-semibold">Watchlist importer</h3>
            <p className="mt-1 max-w-lg text-[0.85rem] text-muted">
              Pull your "My List" from streaming apps into the Watchlist rail. The importer runs
              as a separate local companion tool — MediaShelf just links to it, keeping logged-in
              scraping outside the product. Log into a service once; it refreshes automatically.
            </p>
            <a
              href="http://127.0.0.1:8765"
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-block rounded-[6px] border border-line px-4 py-2 text-[0.9rem] hover:bg-bg2"
            >
              ↗ Open watchlist control panel
            </a>
          </div>
        </Section>

        <Section id="about" title="About">
          <KeyValueMono
            pairs={[
              ["MediaShelf", "0.1.0 (M1 — skeleton & catalog)"],
              ["Data", "TMDB — this product uses the TMDB API but is not endorsed or certified by TMDB"],
              ["Storage", "SQLite in your data dir · keys encrypted at rest · nightly backups (keep 7)"],
            ]}
          />
          <div className="mt-4 flex items-center gap-3">
            <a href="/api/backup/export" download className={quietBtn}>
              Export database
            </a>
            <button onClick={() => fileInput.current?.click()} className={quietBtn}>
              Import database
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".db"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importDb.mutate(f);
                e.target.value = "";
              }}
            />
          </div>
          {importMsg && <p className="mt-2 font-mono text-[0.8rem] text-muted">{importMsg}</p>}
        </Section>
      </div>
    </div>
  );
}
