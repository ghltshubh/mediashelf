import { useMutation, useQueryClient } from "@tanstack/react-query";
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
      {conn.token_expiring_soon && (
        <p className="mt-1 font-mono text-[0.75rem] text-owned">
          developer token expires {conn.token_expires?.slice(0, 10)} — renew it soon
        </p>
      )}

      <div className="mt-3 flex items-center gap-3">
        {canOAuth && conn.state === "none" && (
          <button
            onClick={() => connect.mutate()}
            disabled={!conn.configured || connect.isPending}
            className="rounded-[6px] bg-owned px-3 py-1.5 text-[0.875rem] font-medium text-bg0 disabled:opacity-40"
          >
            Connect
          </button>
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
