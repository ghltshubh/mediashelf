import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Connection } from "../lib/api";
import { ageOf } from "../lib/time";

const DOT = {
  ok: "bg-[color:var(--play)]",
  expired: "bg-owned",
  none: "bg-line",
} as const;

/** Connection card: status dot, what connecting adds, Reconnect on expiry —
    expired tokens never surface as raw errors (plan failure modes). */
export function ConnectionCard({
  conn,
  origin,
  onError,
}: {
  conn: Connection;
  origin: "settings" | "onboarding";
  onError: (msg: string) => void;
}) {
  const queryClient = useQueryClient();

  const connect = useMutation({
    mutationFn: () => api.connectStart(conn.provider, origin),
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
    onError: (e: Error) => onError(e.message),
  });

  const disconnect = useMutation({
    mutationFn: () => api.disconnect(conn.provider),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["connections"] }),
  });

  const canOAuth = conn.provider !== "apple_music";

  return (
    <div className="rounded-[10px] border border-line bg-bg1 p-4">
      <div className="flex items-center gap-2">
        <span aria-hidden className={`h-2 w-2 rounded-full ${DOT[conn.state]}`} />
        <span className="font-display text-[1rem] font-semibold">{conn.name}</span>
        {conn.premium && conn.provider === "spotify" && (
          <span className="rounded-full border border-owned/50 px-1.5 font-mono text-[0.65rem] text-owned">
            premium
          </span>
        )}
        {conn.profile && (
          <span className="ml-auto font-mono text-[0.75rem] text-muted">{conn.profile}</span>
        )}
      </div>
      <p className="mt-2 text-[0.85rem] text-muted">{conn.adds}</p>
      <p className="mt-0.5 font-mono text-[0.7rem] text-muted/80">needs: {conn.requires}</p>
      {conn.synced_at && (
        <p className="mt-0.5 font-mono text-[0.7rem] text-muted/80">
          library synced {ageOf(conn.synced_at)}
        </p>
      )}
      {/* A token the provider won't honour. Deliberately louder than a stale
          sync and deliberately not next to Reconnect, which cannot fix it. */}
      {conn.sync?.status === "blocked" && conn.sync.detail && (
        <p className="mt-2 rounded-[6px] border border-[color:var(--danger)]/40 bg-[color:var(--danger)]/10 px-2.5 py-2 text-[0.8rem] text-[color:var(--danger)]">
          {conn.sync.detail}
        </p>
      )}
      {conn.token_expiring_soon && (
        <p className="mt-1 font-mono text-[0.75rem] text-owned">
          developer token expires {conn.token_expires?.slice(0, 10)} — renew it soon
        </p>
      )}

      <div className="mt-3 flex items-center gap-3">
        {/* Unconfigured means no app keys yet, so there is no OAuth flow to
            start. A greyed-out Connect is a dead end — send people to the form
            that unblocks it instead, which is the only action available. */}
        {canOAuth && conn.state === "none" && !conn.configured && (
          <Link
            to="/settings#keys"
            className="hoverable rounded-[6px] border border-owned/50 px-3 py-1.5 text-[0.875rem] font-medium text-owned hover:bg-owned/15"
          >
            Add keys →
          </Link>
        )}
        {canOAuth && conn.state === "none" && conn.configured && (
          <button
            onClick={() => connect.mutate()}
            disabled={connect.isPending}
            className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.875rem] font-medium text-bg0 disabled:opacity-40"
          >
            Connect
          </button>
        )}
        {/* Apple Music has no OAuth — it needs a developer token pasted in. */}
        {!canOAuth && !conn.configured && (
          <Link
            to="/settings#keys"
            className="hoverable rounded-[6px] border border-owned/50 px-3 py-1.5 text-[0.875rem] font-medium text-owned hover:bg-owned/15"
          >
            Add token →
          </Link>
        )}
        {canOAuth && conn.state === "expired" && (
          <button
            onClick={() => connect.mutate()}
            className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.875rem] font-medium text-bg0"
          >
            Reconnect {conn.name}
          </button>
        )}
        {conn.connected && (
          <button
            onClick={() => disconnect.mutate()}
            className="rounded-[6px] border border-line px-3 py-1.5 text-[0.875rem] text-muted hover:bg-bg2"
          >
            Disconnect
          </button>
        )}
      </div>
    </div>
  );
}
