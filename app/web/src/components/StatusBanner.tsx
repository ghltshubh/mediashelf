const STYLES = {
  info: "border-line bg-bg1 text-ink",
  quota: "border-owned/40 bg-owned/10 text-owned",
  danger: "border-danger/50 bg-danger/10 text-[color:var(--danger)]",
} as const;

/** info / amber-quota / danger banner. Quota-paused is calm, never an error. */
export function StatusBanner({
  kind,
  children,
}: {
  kind: keyof typeof STYLES;
  children: React.ReactNode;
}) {
  return (
    <div
      role={kind === "danger" ? "alert" : "status"}
      aria-live="polite"
      className={`mb-6 rounded-[10px] border px-4 py-3 text-[0.875rem] ${STYLES[kind]}`}
    >
      {children}
    </div>
  );
}
