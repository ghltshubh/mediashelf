import type { MigrationJob } from "../lib/api";
import { ageOf } from "../lib/time";
import { StatusBanner } from "./StatusBanner";

const RUNNING = new Set(["pending", "matching", "writing"]);

const STATUS_LABEL: Record<string, string> = {
  pending: "starting…",
  matching: "matching",
  review: "waiting on review",
  writing: "writing",
  paused_quota: "paused · quota",
  paused_auth: "paused · reconnect needed",
  done: "done",
  stopped: "stopped",
  failed: "failed",
  reverted: "reverted",
};

/** Running-job card (Part 2 §4.6): progress bar, mono counts, live log; quota
    pause is a calm amber banner with Resume — never presented as an error. */
export function ProgressJob({
  job,
  onResume,
  onStop,
  onRevert,
}: {
  job: MigrationJob;
  onResume: () => void;
  onStop: () => void;
  onRevert: () => void;
}) {
  const c = job.counts;
  const settled = c.added + c.already + c.failed + c.skipped;
  const pct = job.total > 0 ? Math.min(100, (settled / job.total) * 100) : 0;
  const running = RUNNING.has(job.status);

  return (
    <div className="rounded-[10px] border border-line bg-bg1 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-display text-[1rem] font-semibold">
          {job.source === "spotify" ? "Spotify" : "YouTube Music"} →{" "}
          {job.target === "youtube" ? "YouTube Music" : "Spotify"}
        </span>
        <span className="font-mono text-[0.7rem] text-muted">
          {job.scope.likes && "likes"}{job.scope.likes && job.scope.follows && " · "}
          {job.scope.follows && "follows"}
        </span>
        <span className={`ml-auto font-mono text-[0.75rem] ${
          job.status === "failed" ? "text-[color:var(--danger)]"
          : job.status === "paused_quota" ? "text-owned"
          : job.status === "done" ? "text-[color:var(--play)]" : "text-muted"}`}>
          {running && <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>}
          {STATUS_LABEL[job.status] ?? job.status}
        </span>
      </div>

      {job.status === "paused_quota" && (
        <div className="mt-3">
          <StatusBanner kind="quota">
            Daily YouTube limit reached. Saved at {settled}/{job.total}; resumes{" "}
            {job.resume_at ? `automatically ${ageOf(job.resume_at) ? "" : "after the reset"} tomorrow` : "tomorrow"}.{" "}
            <button onClick={onResume} className="underline underline-offset-2">Resume now</button>
          </StatusBanner>
        </div>
      )}
      {job.status === "paused_auth" && (
        <div className="mt-3">
          <StatusBanner kind="danger">
            A connection expired — reconnect in Settings → Accounts, then{" "}
            <button onClick={onResume} className="underline underline-offset-2">resume</button>.
          </StatusBanner>
        </div>
      )}

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-bg2"
           role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded-full bg-owned transition-[width] duration-300"
             style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 font-mono text-[0.8rem] text-muted">
        added {c.added} · already there {c.already} · failed {c.failed} · skipped {c.skipped}
        {c.queued > 0 && <> · <span className="text-owned">in review {c.queued}</span></>}
        {job.total > 0 && <> · of {job.total}</>}
      </p>

      {job.log.length > 0 && (
        <pre aria-live="polite"
             className="mt-3 max-h-40 overflow-y-auto rounded-[6px] bg-bg0 p-3 font-mono text-[0.7rem] leading-relaxed text-muted">
          {job.log.join("\n")}
        </pre>
      )}

      <div className="mt-3 flex items-center gap-2">
        {running && (
          <button onClick={onStop}
                  className="rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] text-muted hover:bg-bg2">
            Stop
          </button>
        )}
        {(job.status === "stopped" || job.status === "review") && (
          <button onClick={onResume}
                  className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.85rem] font-medium text-bg0">
            Resume
          </button>
        )}
        {job.journal_size > 0 && !running && job.status !== "reverted" && (
          <button onClick={onRevert}
                  className="rounded-[6px] border border-line px-3 py-1.5 text-[0.85rem] text-muted hover:bg-bg2"
                  title="Unlikes/unsubscribes exactly what this job wrote">
            Revert this job ({job.journal_size})
          </button>
        )}
      </div>
    </div>
  );
}
