import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ConnectionCard } from "../components/ConnectionCard";
import { ServiceTile } from "../components/ServiceTile";
import { api } from "../lib/api";

type Validation = { state: "idle" | "checking" | "ok" | "error"; error?: string };

function StepOne({ onDone }: { onDone: () => void }) {
  const [key, setKey] = useState("");
  const [country, setCountry] = useState("US");
  const [validation, setValidation] = useState<Validation>({ state: "idle" });
  const [saveError, setSaveError] = useState<string | null>(null);
  const timer = useRef<number>();
  const queryClient = useQueryClient();

  // Live validation: fires a real test request, shows ✓ or the actual error text.
  useEffect(() => {
    window.clearTimeout(timer.current);
    if (!key.trim()) {
      setValidation({ state: "idle" });
      return;
    }
    setValidation({ state: "checking" });
    timer.current = window.setTimeout(async () => {
      try {
        const res = await api.validateTmdb(key.trim());
        setValidation(res.ok ? { state: "ok" } : { state: "error", error: res.error });
      } catch (e) {
        setValidation({ state: "error", error: (e as Error).message });
      }
    }, 600);
    return () => window.clearTimeout(timer.current);
  }, [key]);

  const save = useMutation({
    mutationFn: () => api.updateSettings({ tmdb_api_key: key.trim(), country }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      onDone();
    },
    onError: (e: Error) => setSaveError(e.message),
  });

  return (
    <div>
      <h1 className="font-display text-[1.6rem] font-bold">Your TMDB key</h1>
      <p className="mt-2 max-w-lg text-[0.95rem] text-muted">
        MediaShelf loads its catalog from TMDB with your own free API key. Create one at{" "}
        <a
          href="https://www.themoviedb.org/settings/api"
          target="_blank"
          rel="noreferrer"
          className="text-owned underline underline-offset-2"
        >
          themoviedb.org/settings/api
        </a>{" "}
        and paste it below.
      </p>

      <label className="mt-6 block max-w-lg">
        <span className="font-mono text-[0.75rem] text-muted">TMDB API KEY</span>
        <input
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          autoFocus
          className="mt-1 w-full rounded-[6px] border border-line bg-bg1 px-3 py-2 font-mono text-[0.875rem] placeholder:text-muted/50"
          placeholder="paste your v3 key or v4 token"
        />
      </label>
      <p aria-live="polite" className="mt-2 min-h-5 font-mono text-[0.8rem]">
        {validation.state === "checking" && <span className="text-muted">checking…</span>}
        {validation.state === "ok" && <span className="text-play">✓ key works</span>}
        {validation.state === "error" && (
          <span className="text-[color:var(--danger)]">{validation.error}</span>
        )}
      </p>

      <label className="mt-4 block max-w-[10rem]">
        <span className="font-mono text-[0.75rem] text-muted">COUNTRY</span>
        <input
          value={country}
          onChange={(e) => setCountry(e.target.value.toUpperCase().slice(0, 2))}
          className="mt-1 w-full rounded-[6px] border border-line bg-bg1 px-3 py-2 font-mono text-[0.875rem]"
        />
      </label>
      <p className="mt-1 font-mono text-[0.7rem] text-muted">2-letter code — sets watch-provider availability</p>

      {saveError && (
        <p className="mt-3 font-mono text-[0.8rem] text-[color:var(--danger)]">{saveError}</p>
      )}
      <button
        disabled={validation.state !== "ok" || save.isPending}
        onClick={() => save.mutate()}
        className="mt-6 rounded-[6px] bg-owned px-5 py-2 font-medium text-bg0 disabled:opacity-40"
      >
        {save.isPending ? "Saving…" : "Continue"}
      </button>
    </div>
  );
}

function StepTwo({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const services = useQuery({ queryKey: ["services"], queryFn: api.services });
  const toggle = useMutation({
    mutationFn: ({ id, subscribed }: { id: number; subscribed: boolean }) =>
      api.setSubscription(id, subscribed),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["services"] }),
  });

  const list = (services.data ?? []).filter(
    (s) => (s.kind === "video" || s.kind === "music") && !s.is_channel,
  );

  return (
    <div>
      <h1 className="font-display text-[1.6rem] font-bold">Your services</h1>
      <p className="mt-2 max-w-lg text-[0.95rem] text-muted">
        Tick what you subscribe to. No logins needed — this just tells the shelf what's yours.
        Lit tiles are yours; dimmed ones aren't.
      </p>

      <div className="mt-6 grid max-w-3xl grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {list.map((s) => (
          <ServiceTile
            key={s.id}
            service={s}
            onToggle={(sub) => toggle.mutate({ id: s.id, subscribed: sub })}
          />
        ))}
      </div>

      <button
        onClick={onDone}
        className="mt-8 rounded-[6px] bg-owned px-5 py-2 font-medium text-bg0"
      >
        Continue
      </button>
    </div>
  );
}

function StepThree({ onDone }: { onDone: () => void }) {
  const connections = useQuery({ queryKey: ["connections"], queryFn: api.connections });
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const setYtdlp = useMutation({
    mutationFn: (enabled: boolean) => api.updateSettings({ ytdlp_enabled: enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const s = settings.data;
  const [error, setError] = useState<string | null>(null);

  return (
    <div>
      <h1 className="font-display text-[1.6rem] font-bold">Connect accounts (optional)</h1>
      <p className="mt-2 max-w-lg text-[0.95rem] text-muted">
        Connecting adds in-app playback and library sync. Each service uses your own free
        API keys — nothing is shared, nothing phones home.
      </p>
      {error && <p className="mt-3 font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}

      <div className="mt-6 max-w-xl space-y-3">
        {(connections.data ?? []).map((c) => (
          <ConnectionCard key={c.provider} conn={c} origin="onboarding" onError={setError} />
        ))}
      </div>
      <p className="mt-3 max-w-xl font-mono text-[0.75rem] text-muted">
        YouTube and Apple Music need keys added in Settings → Accounts first — both are guided there.
      </p>

      {/* yt-dlp suggestion — honest one-paragraph explanation (M6), off by default. */}
      <div className="mt-6 max-w-xl rounded-[10px] border border-line bg-bg1 p-4">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-[1.05rem] font-semibold">yt-dlp (optional)</h2>
          {s?.ytdlp_detected ? (
            <label className="flex shrink-0 items-center gap-2 text-[0.85rem]">
              <input
                type="checkbox"
                checked={!!s?.ytdlp_enabled}
                onChange={(e) => setYtdlp.mutate(e.target.checked)}
                className="accent-[var(--owned)]"
              />
              enable
            </label>
          ) : (
            <span className="shrink-0 font-mono text-[0.72rem] text-muted">not installed</span>
          )}
        </div>
        <p className="mt-1 text-[0.9rem] text-muted">
          Saves API quota, especially for search — it reads YouTube's public pages via unofficial
          access (ToS-gray), metadata only, never downloads or plays media. Off by default; change
          it any time in Settings → Plugins.
        </p>
        {!s?.ytdlp_detected && (
          <p className="mt-2 font-mono text-[0.72rem] text-muted">
            Install it locally with <code>pipx install yt-dlp</code> to enable.
          </p>
        )}
      </div>

      {/* "Do this later" is a first-class button, not a text link (Part 2 §4.1). */}
      <div className="mt-8 flex items-center gap-4">
        <button
          onClick={onDone}
          className="rounded-[6px] bg-owned px-5 py-2 font-medium text-bg0"
        >
          Done — open the shelf
        </button>
        <button
          onClick={onDone}
          className="rounded-[6px] border border-line px-5 py-2 font-medium text-ink hover:bg-bg2"
        >
          Do this later
        </button>
      </div>
    </div>
  );
}

export function Onboarding() {
  const [params] = useSearchParams();
  // Returning from an OAuth redirect mid-onboarding lands back on step 3.
  const [step, setStep] = useState<1 | 2 | 3>(
    params.get("connected") || params.get("connect_error") ? 3 : 1,
  );
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  const finish = useMutation({
    mutationFn: () => api.updateSettings({ onboarded: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      navigate("/");
    },
  });

  // Returning users who already have a key skip step 1.
  useEffect(() => {
    if (settings.data?.tmdb_api_key_set && step === 1) setStep(2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.data?.tmdb_api_key_set]);

  return (
    <div className="mx-auto max-w-3xl pt-10">
      <p className="mb-8 font-mono text-[0.75rem] text-muted">{step} of 3</p>
      {step === 1 && <StepOne onDone={() => setStep(2)} />}
      {step === 2 && <StepTwo onDone={() => setStep(3)} />}
      {step === 3 && <StepThree onDone={() => finish.mutate()} />}
    </div>
  );
}
