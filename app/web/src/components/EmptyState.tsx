import type { ReactNode } from "react";

/** Empty states are instructions, not moods (Part 2 §6): name the exact action. */
export function EmptyState({
  message,
  action,
}: {
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto mt-24 max-w-md rounded-[10px] border border-line bg-bg1 p-8 text-center">
      <p className="text-ink">{message}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
