import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { FilterChips } from "../components/FilterChips";
import { SearchResultRow } from "../components/SearchResultRow";
import { StatusBanner } from "../components/StatusBanner";
import { api } from "../lib/api";
import { useActivate } from "../lib/searchData";

/** Library (M3): synced likes/subs from connected accounts, playable in place. */
export function Library() {
  const queryClient = useQueryClient();
  const library = useQuery({
    queryKey: ["library"],
    queryFn: api.library,
    refetchInterval: (q) => {
      const sync = q.state.data?.sync;
      return sync && Object.values(sync).some((s) => s.status === "running") ? 3000 : false;
    },
  });
  const { activate } = useActivate();
  const [chip, setChip] = useState("all");

  const syncNow = useMutation({
    mutationFn: (provider: string) => api.syncLibrary(provider),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["library"] }),
  });

  const data = library.data;
  if (!data) {
    return <div className="h-40 animate-pulse rounded-[10px] bg-bg1" />;
  }

  const anyConnected = Object.values(data.connections).some(Boolean);
  if (!anyConnected) {
    return (
      <EmptyState
        message="Connect Spotify or YouTube to sync your likes."
        action={
          <Link
            to="/settings#accounts"
            className="inline-block rounded-[6px] bg-owned px-4 py-2 font-medium text-bg0"
          >
            Connect accounts
          </Link>
        }
      />
    );
  }

  const authIssues = Object.entries(data.sync).filter(([, s]) => s.status === "auth");
  const visible = data.groups.filter((g) => chip === "all" || g.key === chip);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-1 flex items-center justify-between">
        <h1 className="font-display text-[1.6rem] font-bold">Library</h1>
        <div className="flex gap-2">
          {Object.entries(data.connections)
            .filter(([, connected]) => connected)
            .map(([provider]) => (
              <button
                key={provider}
                onClick={() => syncNow.mutate(provider)}
                disabled={data.sync[provider]?.status === "running"}
                className="rounded-[6px] border border-line px-3 py-1 font-mono text-[0.75rem] text-muted hover:bg-bg2 disabled:opacity-40"
              >
                {data.sync[provider]?.status === "running" ? "syncing…" : `sync ${provider}`}
              </button>
            ))}
        </div>
      </div>
      <p className="mb-5 font-mono text-[0.8rem] text-muted">
        {data.groups.reduce((n, g) => n + g.count, 0).toLocaleString()} items ·{" "}
        {data.groups.length} collections
      </p>

      {authIssues.map(([provider, s]) => (
        <StatusBanner key={provider} kind="danger">
          {s.detail} —{" "}
          <Link to="/settings#accounts" className="underline underline-offset-2">
            Reconnect in Settings
          </Link>
        </StatusBanner>
      ))}

      <FilterChips
        chips={[{ key: "all", label: "All" },
                ...data.groups.map((g) => ({ key: g.key, label: g.label }))]}
        active={chip}
        onSelect={setChip}
      />

      <div className="mt-6 space-y-8">
        {visible.map((g) => (
          <section key={g.key}>
            <h2 className="mb-2 flex items-baseline gap-2 font-mono text-[0.75rem] tracking-widest text-muted">
              {g.label.toUpperCase()}
              <span className="opacity-70">{g.count}</span>
              {g.count > g.items.length && (
                <span className="opacity-50">showing first {g.items.length}</span>
              )}
            </h2>
            <div className="rounded-[10px] border border-line bg-bg1 py-1">
              {g.items.map((item, i) => (
                <SearchResultRow
                  key={`${g.key}-${i}`}
                  id={`lib-${g.key}-${i}`}
                  item={item}
                  active={false}
                  onActivate={() => void activate(item)}
                />
              ))}
            </div>
          </section>
        ))}
        {visible.length === 0 && (
          <p className="py-10 text-center text-muted">
            Nothing synced yet — hit a sync button above, or check back in a moment.
          </p>
        )}
      </div>
    </div>
  );
}
