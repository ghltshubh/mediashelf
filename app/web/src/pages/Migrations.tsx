import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MatchCard } from "../components/MatchCard";
import { ProgressJob } from "../components/ProgressJob";
import type { TrackPayload } from "../lib/api";
import { api } from "../lib/api";

const BATCH_MIN = 0.9;
const ACTIVE = new Set(["pending", "matching", "writing"]);

function SetupCard() {
  const queryClient = useQueryClient();
  const migrations = useQuery({ queryKey: ["migrations"], queryFn: api.migrations });
  const [pairIdx, setPairIdx] = useState(0);
  const [likes, setLikes] = useState(true);
  const [follows, setFollows] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () => {
      const pair = migrations.data!.pairs[pairIdx];
      return api.startMigration({
        source: pair.source, target: pair.target, likes, follows,
        source_slot: pair.source_slot, target_slot: pair.target_slot,
      });
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["migrations"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const data = migrations.data;
  if (!data) return null;
  const pair = data.pairs[pairIdx];

  return (
    <div className="rounded-[10px] border border-line bg-bg1 p-4">
      <div className="flex flex-wrap items-end gap-3">
        <label>
          <span className="font-mono text-[0.75rem] text-muted">DIRECTION</span>
          <select
            value={pairIdx}
            onChange={(e) => setPairIdx(Number(e.target.value))}
            className="mt-1 block rounded-[6px] border border-line bg-bg0 px-3 py-2 text-[0.9rem]"
          >
            {data.pairs.map((p, i) => (
              <option key={p.label} value={i}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 pb-2 text-[0.9rem]">
          <input type="checkbox" checked={likes} onChange={(e) => setLikes(e.target.checked)}
                 className="accent-[var(--owned)]" />
          liked songs
        </label>
        <label className="flex items-center gap-2 pb-2 text-[0.9rem]">
          <input type="checkbox" checked={follows} onChange={(e) => setFollows(e.target.checked)}
                 className="accent-[var(--owned)]" />
          followed artists
        </label>
        <button
          disabled={!pair?.ready || (!likes && !follows) || start.isPending}
          onClick={() => start.mutate()}
          className="rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0 disabled:opacity-40"
        >
          {start.isPending ? "Starting…" : "Start migration"}
        </button>
      </div>
      {!pair?.ready && (
        <p className="mt-2 font-mono text-[0.75rem] text-muted">
          both sides must be connected —{" "}
          <Link to="/settings#accounts" className="text-owned hover:underline">
            Settings → Accounts
          </Link>
        </p>
      )}
      <p className="mt-2 font-mono text-[0.7rem] text-muted">
        daily write budget: {data.budget.used_today}/{data.budget.cap} used · jobs pause at the
        cap and resume after the reset — never an error
      </p>
      {error && <p className="mt-2 font-mono text-[0.8rem] text-[color:var(--danger)]">{error}</p>}
    </div>
  );
}

/** Connect a SECOND account of a service (migration-only) — enables the
    same-service account-to-account directions in the picker above. */
function SecondAccounts() {
  const queryClient = useQueryClient();
  const seconds = useQuery({ queryKey: ["second-accounts"], queryFn: api.secondAccounts });
  const connect = useMutation({
    mutationFn: (provider: string) => api.connectStart(provider, "settings", "secondary"),
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
  });
  const disconnect = useMutation({
    mutationFn: (provider: string) => api.disconnect(provider, "secondary"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["second-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["migrations"] });
    },
  });
  const rows = (seconds.data ?? []).filter((a) => a.configured);
  if (rows.length === 0) return null;

  return (
    <div className="mt-4 rounded-[10px] border border-line bg-bg1 p-4">
      <h3 className="font-display text-[1rem] font-semibold">Second accounts</h3>
      <p className="mt-1 max-w-xl text-[0.85rem] text-muted">
        Connect a second account of the same service to migrate your library from one account to
        another (e.g. YouTube A → YouTube B). Same-service copies are direct and lossless — no
        matching. This account is used only for migration; it never touches your shelf.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {rows.map((a) => (
          <div key={a.provider}
               className="flex items-center gap-2 rounded-[8px] border border-line px-3 py-1.5">
            <span className="font-mono text-[0.8rem]">{a.name}</span>
            {a.connected ? (
              <>
                <span className="font-mono text-[0.72rem] text-[color:var(--play)]">
                  ✓ {a.profile ?? "connected"}
                </span>
                <button onClick={() => disconnect.mutate(a.provider)}
                        className="font-mono text-[0.72rem] text-muted hover:text-[color:var(--danger)]">
                  disconnect
                </button>
              </>
            ) : (
              <button onClick={() => connect.mutate(a.provider)}
                      className="rounded-[6px] border border-owned/60 px-2 py-0.5 font-mono text-[0.72rem] text-owned hover:bg-owned/10">
                ↗ connect 2nd account
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Migrations home: setup card, running/past jobs, and the M4 review queue. */
export function Migrations() {
  const queryClient = useQueryClient();
  const review = useQuery({ queryKey: ["review"], queryFn: api.review });
  const migrations = useQuery({
    queryKey: ["migrations"],
    queryFn: api.migrations,
    refetchInterval: (q) =>
      q.state.data?.jobs.some((j) => ACTIVE.has(j.status)) ? 2000 : false,
  });
  const jobAction = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "resume" | "stop" | "revert" }) =>
      action === "resume" ? api.resumeMigration(id)
      : action === "stop" ? api.stopMigration(id)
      : api.revertMigration(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["migrations"] });
      queryClient.invalidateQueries({ queryKey: ["review"] });
    },
  });
  const [activeIdx, setActiveIdx] = useState(0);
  const [pickerFor, setPickerFor] = useState<number | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["review"] });
  const approve = useMutation({ mutationFn: api.reviewApprove, onSuccess: invalidate });
  const skip = useMutation({ mutationFn: api.reviewSkip, onSuccess: invalidate });
  const replace = useMutation({
    mutationFn: ({ id, candidate }: { id: number; candidate: TrackPayload }) =>
      api.reviewReplace(id, candidate),
    onSuccess: () => {
      setPickerFor(null);
      invalidate();
    },
  });
  const batch = useMutation({
    mutationFn: () => api.reviewBatch(BATCH_MIN),
    onSuccess: invalidate,
  });

  const pending = review.data?.pending ?? [];
  const batchCount = pending.filter((p) => p.confidence >= BATCH_MIN).length;

  useEffect(() => {
    setActiveIdx((i) => Math.min(i, Math.max(0, pending.length - 1)));
  }, [pending.length]);

  // Keyboard: arrows move, A approve, S skip, P pick-another (Part 2 §4.6).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable) return;
      const current = pending[activeIdx];
      if (!current) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, pending.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "a" || e.key === "A") {
        approve.mutate(current.id);
      } else if (e.key === "s" || e.key === "S") {
        skip.mutate(current.id);
      } else if (e.key === "p" || e.key === "P") {
        setPickerFor((p) => (p === current.id ? null : current.id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, activeIdx, approve, skip]);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="font-display text-[1.6rem] font-bold">Migrations</h1>
      <p className="mt-1 max-w-xl text-[0.9rem] text-muted">
        Copy likes and follows between services. Jobs are resumable across days, every write
        is journaled (revertable), and ambiguous matches wait in the review queue below.
      </p>

      <div className="mt-6">
        <SetupCard />
        <SecondAccounts />
      </div>

      {(migrations.data?.jobs.length ?? 0) > 0 && (
        <section className="mt-8 space-y-3">
          <h2 className="font-display text-[1.25rem] font-semibold">Jobs</h2>
          {migrations.data!.jobs.map((job) => (
            <ProgressJob
              key={job.id}
              job={job}
              onResume={() => jobAction.mutate({ id: job.id, action: "resume" })}
              onStop={() => jobAction.mutate({ id: job.id, action: "stop" })}
              onRevert={() => jobAction.mutate({ id: job.id, action: "revert" })}
            />
          ))}
        </section>
      )}

      <section className="mt-8">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="font-display text-[1.25rem] font-semibold">Review queue</h2>
          <span aria-live="polite" className="font-mono text-[0.8rem] text-muted">
            {pending.length} pending
          </span>
          {batchCount > 0 && (
            <button
              onClick={() => batch.mutate()}
              disabled={batch.isPending}
              className="ml-auto rounded-[6px] border border-owned/50 px-3 py-1.5 font-mono text-[0.8rem] text-owned hover:bg-owned/10 disabled:opacity-40"
            >
              approve all ≥{BATCH_MIN * 100}% ({batchCount})
            </button>
          )}
        </div>

        {pending.length === 0 ? (
          <p className="rounded-[10px] border border-line bg-bg1 px-4 py-6 text-center text-[0.9rem] text-muted">
            The review queue is empty. It fills when a migration can't match a track
            confidently — nothing ambiguous is ever written without your approval.
          </p>
        ) : (
          <div className="space-y-3">
            {pending.map((item, i) => (
              <MatchCard
                key={item.id}
                item={item}
                active={i === activeIdx}
                pickerOpen={pickerFor === item.id}
                onFocus={() => setActiveIdx(i)}
                onApprove={() => approve.mutate(item.id)}
                onSkip={() => skip.mutate(item.id)}
                onTogglePicker={() => setPickerFor((p) => (p === item.id ? null : item.id))}
                onReplace={(candidate) => replace.mutate({ id: item.id, candidate })}
              />
            ))}
            <p className="font-mono text-[0.7rem] text-muted">
              ↑↓ move · A approve · P pick another · S skip
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
