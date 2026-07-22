/** Mono key/value line for metadata, stats, and logs. */
export function KeyValueMono({ pairs }: { pairs: [string, string][] }) {
  return (
    <dl className="font-mono text-[0.8rem] text-muted">
      {pairs.map(([k, v]) => (
        <div key={k} className="flex gap-2 py-0.5">
          <dt className="min-w-32 opacity-70">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
