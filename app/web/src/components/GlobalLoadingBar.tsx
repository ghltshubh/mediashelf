import { useIsFetching } from "@tanstack/react-query";
import { useEffect, useState } from "react";

/** Thin top progress bar shown whenever data is in flight — page switches and
    the slower title/person/similar loads (which do live TMDB lookups). A short
    delay keeps it from flashing on instant, cached loads. */
export function GlobalLoadingBar() {
  const fetching = useIsFetching();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (fetching > 0) {
      const t = window.setTimeout(() => setVisible(true), 150);
      return () => window.clearTimeout(t);
    }
    setVisible(false);
  }, [fetching]);

  return (
    <div
      aria-hidden={!visible}
      className={`pointer-events-none fixed inset-x-0 top-0 z-[70] h-[3px] overflow-hidden transition-opacity duration-200 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="loading-seg" />
    </div>
  );
}
