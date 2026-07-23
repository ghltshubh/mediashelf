// Typed API client for the MediaShelf backend.

export interface SyncState {
  status: "idle" | "running" | "error";
  detail: string | null;
  last_completed: string | null;
  error_kind: "auth" | "network" | null;
}

export interface Settings {
  tmdb_api_key_set: boolean;
  tmdb_api_key_masked: string | null;
  country: string;
  extra_countries: string[];
  onboarded: boolean;
  sync: SyncState;
  synced_at: string | null;
  restore_notice: string | null;
  spotify_configured: boolean;
  spotify_client_id: string | null;
  google_configured: boolean;
  preferred_music_service: "auto" | "spotify" | "apple_music" | "youtube";
  catalog_pages: number;
  omdb_configured: boolean;
  ytdlp_detected: boolean;
  ytdlp_enabled: boolean;
  // Display locale (BCP-47) for date/number formatting; "" = follow browser.
  // Independent of `country` (content region).
  locale: string;
}

export interface RailPage {
  key: string;
  label: string;
  items: ShelfItem[];
  country: string;
  regions: string[];
}

export interface Connection {
  provider: "spotify" | "youtube" | "apple_music";
  name: string;
  configured: boolean;
  connected: boolean;
  state: "ok" | "expired" | "none";
  profile: string | null;
  premium: boolean;
  adds: string;
  requires: string;
  sync?: { status: string; detail: string | null };
  synced_at?: string | null;
  token_expires?: string | null;
  token_expiring_soon?: boolean;
}

export interface PlayOption {
  engine: "spotify_sdk" | "musickit" | "youtube" | "spotify_embed" | "audio" | "resolve" | "deeplink";
  service_key: string;
  label: string;
  kind: string;
  payload: {
    spotify_uri?: string;
    track_id?: string;
    video_id?: string;
    apple_id?: string;
    url?: string;
    // MusicKit / cross-service resolve by title/artist when no id is known.
    title?: string;
    artists?: string[];
    duration_ms?: number | null;
  };
}

export interface Playback {
  options: PlayOption[];
  default: PlayOption | null;
}

export interface LibraryGroup {
  key: string;
  provider: string;
  label: string;
  count: number;
  items: MusicResult[];
}

export interface TrackPayload {
  title: string;
  artists?: string[];
  album?: string | null;
  duration_ms?: number | null;
  isrc?: string | null;
  thumb?: string | null;
  url?: string | null;
  uri?: string | null;
  spotify_id?: string | null;
  service?: string;
}

export interface ReviewItem {
  id: number;
  job_id: number | null;
  source: TrackPayload;
  candidate: TrackPayload;
  confidence: number;
  status: "pending" | "approved" | "skipped" | "replaced";
}

export interface MigrationJob {
  id: number;
  source: string;
  target: string;
  status: "pending" | "matching" | "review" | "writing" | "paused_quota"
    | "paused_auth" | "done" | "stopped" | "failed" | "reverted";
  scope: { likes?: boolean; follows?: boolean };
  counts: { added: number; already: number; failed: number; skipped: number; queued: number };
  total: number;
  resume_at: string | null;
  journal_size: number;
  log: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface MigrationPair {
  source: string;
  target: string;
  source_slot: string;
  target_slot: string;
  label: string;
  ready: boolean;
}

export interface SecondAccount {
  provider: string;
  name: string;
  connected: boolean;
  profile: string | null;
  configured: boolean;
}

export interface MigrationsData {
  jobs: MigrationJob[];
  pairs: MigrationPair[];
  budget: { cap: number; used_today: number };
}

export interface LibraryData {
  groups: LibraryGroup[];
  sync: Record<string, { status: string; detail: string | null }>;
  connections: Record<string, boolean>;
}

export interface Service {
  id: number;
  key: string;
  name: string;
  kind: "video" | "music" | "meta" | "podcast";
  tier: number;
  subscribed: boolean;
  capabilities: { playback: string; [k: string]: unknown };
  signup_url: string | null;
  sso_note: string | null;
  homepage_url: string | null;
  logo_url: string | null;
  auto_added: boolean;
  custom: boolean;
  is_channel: boolean;
  featured: boolean;
  integration: string;
  integration_kind: "connector" | "watchlist" | "basic";
  connected: boolean;
  expired: boolean;
  watchlist_count: number;
}

export interface Badge {
  service_key: string;
  service_name: string;
  logo: string | null;
  offer_type: "flatrate" | "free" | "ads" | "rent" | "buy";
  owned: boolean;
  deep_link: string | null;
  price: string | null;
  signup_url: string | null;
  sso_note: string | null;
  plan_price: string | null;
  checked_at: string | null;
}

export interface ShelfItem {
  id: number;
  media_type: "movie" | "tv";
  title: string;
  year: number | null;
  poster: string | null;
  backdrop: string | null;
  rating: number | null;
  genres: string[];
  owned: boolean;
  unlock_service: string | null;
  badges: Badge[];
  list_source?: string;  // watchlist rail: which of your lists it's from
  list_source_logo?: string | null;
  // Studio-inferred likely home for an upcoming, not-yet-streaming title. A
  // prediction, not confirmed availability — shown dimmed as "expected on X".
  expected_service?: { service_key: string; service_name: string; logo: string | null } | null;
}

export interface Shelf {
  stats: { titles: number; services: number; subscribed: number };
  rails: { key: string; label: string; items: ShelfItem[]; total: number; owned?: boolean }[];
  subscribed_services: { key: string; name: string }[];
  all_genres: string[];
  filter: string;
  sync: SyncState;
  country: string;
  synced_at: string | null;
  regions: string[];
}

export interface SearchAction {
  type: "deeplink" | "title" | "import" | "play";
  url?: string;
  title_id?: number;
  media_type?: string;
  tmdb_id?: number;
}

export interface VideoResult {
  local: boolean;
  media_type: "movie" | "tv";
  tmdb_id: number | null;
  id: number | null;
  title: string;
  year: number | null;
  poster: string | null;
  rating?: number | null;
  genres?: string[];
  owned: boolean;
  badges: Badge[];
  unlock_service: string | null;
  action: SearchAction;
  hint: string;
  role?: string | null; // discovery cards: character or crew job
}

export interface PersonPage {
  id: number;
  name: string;
  profile: string | null;
  known_for: string | null;
  biography: string | null;
  credits: VideoResult[];
}

export interface MusicServiceLink {
  service_key: string;
  service_name: string;
  url: string | null;
  owned: boolean;
}

export interface MusicResult {
  entity: "track" | "album" | "artist" | "video" | "channel";
  title: string;
  artists: string[];
  year: number | null;
  thumb: string | null;
  duration_ms?: number | null;
  services: MusicServiceLink[];
  action: SearchAction | null;
  hint: string;
  playback?: Playback;
}

export type SearchResult = VideoResult | MusicResult;

export interface SearchResponse {
  scope: "video" | "music" | "library";
  groups: { key: string; label: string; items: SearchResult[] }[];
  providers: { key: string; state: "ok" | "unavailable" | "unconfigured" }[];
}

export interface PodcastEpisode {
  id: number;
  guid: string;
  title: string;
  description: string | null;
  audio_url: string;
  duration_seconds: number | null;
  published_at: string | null;
  image_url: string | null;
}

export interface Podcast {
  id: number;
  feed_url: string;
  title: string;
  author: string | null;
  description: string | null;
  image_url: string | null;
  website: string | null;
  episode_count: number;
  last_fetched_at: string | null;
  latest_episode: PodcastEpisode | null;
  episodes?: PodcastEpisode[];
}

export interface Title extends ShelfItem {
  overview: string | null;
  runtime_minutes: number | null;
  country: string;
  on_your_services: Badge[];
  elsewhere: Badge[];
  play: Playback;
  trailer_youtube_id: string | null;
  regions: string[];
  world: { country: string; services: string[]; more: number }[];
  ratings: { imdb?: number; imdb_votes?: string; rt?: string; metacritic?: string };
  keywords: string[];
  cast: { id: number | null; name: string; character: string | null; profile: string | null }[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep status */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  settings: () => request<Settings>("/api/settings"),
  updateSettings: (
    body: Partial<{
      tmdb_api_key: string;
      country: string;
      extra_countries: string[];
      catalog_pages: number;
      onboarded: boolean;
      dismiss_restore_notice: boolean;
      omdb_api_key: string;
      spotify_client_id: string;
      spotify_client_secret: string;
      google_client_id: string;
      google_client_secret: string;
      preferred_music_service: "auto" | "spotify" | "apple_music" | "youtube";
      ytdlp_enabled: boolean;
      locale: string;
    }>,
  ) =>
    request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  validateTmdb: (key: string) =>
    request<{ ok: boolean; error?: string }>("/api/settings/tmdb/validate", {
      method: "POST",
      body: JSON.stringify({ tmdb_api_key: key }),
    }),
  services: (region = "") => request<Service[]>(`/api/services?region=${region}`),
  setSubscription: (id: number, subscribed: boolean) =>
    request<{ id: number; subscribed: boolean }>(`/api/services/${id}/subscription`, {
      method: "PUT",
      body: JSON.stringify({ subscribed }),
    }),
  createService: (body: { name: string; homepage_url: string; kind?: string }) =>
    request<Service>("/api/services", { method: "POST", body: JSON.stringify(body) }),
  deleteService: async (id: number) => {
    const res = await fetch(`/api/services/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status}`);
  },
  importBackup: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/backup/import", { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `${res.status}`);
    }
  },
  shelf: (
    view: "categories" | "services" = "categories",
    region = "",
    filter = "all",
    type = "",
    sort = "popularity",
    genre = "",
  ) =>
    request<Shelf>(
      `/api/shelf?view=${view}&region=${region}&filter=${encodeURIComponent(filter)}&type=${type}&sort=${sort}&genre=${encodeURIComponent(genre)}`,
    ),
  title: (id: number, region = "") => request<Title>(`/api/titles/${id}?region=${region}`),
  similar: (id: number, region = "") =>
    request<{ items: VideoResult[] }>(`/api/titles/${id}/similar?region=${region}`),
  because: () => request<{ seed: string | null; items: VideoResult[] }>("/api/home/because"),
  lucky: (genre = "", maxMinutes: number | null = null, type = "") =>
    request<{ found: boolean; item?: ShelfItem & { runtime_minutes: number | null; play: Playback } }>(
      `/api/lucky?genre=${encodeURIComponent(genre)}${maxMinutes ? `&max_minutes=${maxMinutes}` : ""}&type=${type}`,
    ),
  person: (id: number, region = "") =>
    request<PersonPage>(`/api/person/${id}?region=${region}`),
  rail: (key: string, region = "", filter = "all", type = "", sort = "popularity", genre = "") =>
    request<RailPage>(
      `/api/shelf/rail/${encodeURIComponent(key)}?region=${region}&filter=${encodeURIComponent(filter)}&type=${type}&sort=${sort}&genre=${encodeURIComponent(genre)}`,
    ),
  regions: () => request<{ code: string; name: string }[]>("/api/regions"),
  sync: () => request<{ status: string }>("/api/sync", { method: "POST" }),
  search: (scope: "video" | "music" | "library", q: string) =>
    request<SearchResponse>(`/api/search?scope=${scope}&q=${encodeURIComponent(q)}`),
  connections: () => request<Connection[]>("/api/connections"),
  connectStart: (provider: string, origin: string, slot = "primary") =>
    request<{ url: string }>(`/api/connect/${provider}/start?origin=${origin}&slot=${slot}`),
  disconnect: async (provider: string, slot = "primary") => {
    const res = await fetch(`/api/connections/${provider}?slot=${slot}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status}`);
  },
  secondAccounts: () => request<SecondAccount[]>("/api/connections/second"),
  syncLibrary: (provider: string) =>
    request<{ status: string }>(`/api/connections/${provider}/sync`, { method: "POST" }),
  library: () => request<LibraryData>("/api/library"),
  spotifyPlaybackToken: () =>
    request<{ access_token: string }>("/api/playback/spotify/token"),
  resolvePlayback: (title: string, artists: string[], duration_ms?: number | null) =>
    request<{ option: PlayOption | null }>(
      `/api/playback/resolve?title=${encodeURIComponent(title)}&artists=${encodeURIComponent(
        artists.join(", "),
      )}${duration_ms ? `&duration_ms=${duration_ms}` : ""}`,
    ),
  migrations: () => request<MigrationsData>("/api/migrations"),
  startMigration: (body: {
    source: string;
    target: string;
    likes: boolean;
    follows: boolean;
    source_slot?: string;
    target_slot?: string;
  }) =>
    request<MigrationJob & { resumed_existing: boolean }>("/api/migrations", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resumeMigration: (id: number) =>
    request<MigrationJob>(`/api/migrations/${id}/resume`, { method: "POST" }),
  stopMigration: (id: number) =>
    request<{ status: string }>(`/api/migrations/${id}/stop`, { method: "POST" }),
  revertMigration: (id: number) =>
    request<{ status: string }>(`/api/migrations/${id}/revert`, { method: "POST" }),
  review: () => request<{ pending: ReviewItem[] }>("/api/review"),
  reviewApprove: (id: number) =>
    request<ReviewItem>(`/api/review/${id}/approve`, { method: "POST" }),
  reviewSkip: (id: number) =>
    request<ReviewItem>(`/api/review/${id}/skip`, { method: "POST" }),
  reviewReplace: (id: number, candidate: TrackPayload) =>
    request<ReviewItem>(`/api/review/${id}/replace`, {
      method: "POST",
      body: JSON.stringify({ candidate }),
    }),
  reviewBatch: (min_confidence: number) =>
    request<{ approved: number }>("/api/review/approve-batch", {
      method: "POST",
      body: JSON.stringify({ min_confidence }),
    }),
  setAppleToken: (token: string) =>
    request<Connection>("/api/connections/apple_music/token", {
      method: "PUT",
      body: JSON.stringify({ token }),
    }),
  importTitle: (media_type: string, tmdb_id: number) =>
    request<Title>("/api/titles/import", {
      method: "POST",
      body: JSON.stringify({ media_type, tmdb_id }),
    }),
  podcasts: () => request<Podcast[]>("/api/podcasts"),
  podcast: (id: number) => request<Podcast>(`/api/podcasts/${id}`),
  subscribePodcast: (feed_url: string) =>
    request<Podcast>("/api/podcasts", { method: "POST", body: JSON.stringify({ feed_url }) }),
  unsubscribePodcast: async (id: number) => {
    const res = await fetch(`/api/podcasts/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`${res.status}`);
  },
  refreshPodcasts: () =>
    request<{ new_episodes: number }>("/api/podcasts/refresh", { method: "POST" }),
  importPodcastOpml: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/podcasts/opml/import", { method: "POST", body: form });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `${res.status}`);
    }
    return res.json() as Promise<{ subscribed: number }>;
  },
};
