import { useEffect, useRef } from "react";

// Re-run `fn` every `ms` while the tab is visible. Pauses in a background tab to
// avoid wasted requests; runs once immediately when deps change.
export function usePoll(fn, ms = 15000, deps = []) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    let alive = true;
    const tick = () => {
      if (alive && typeof document !== "undefined" && !document.hidden) saved.current();
    };
    tick();
    const id = setInterval(tick, ms);
    // Refresh at once when the tab becomes visible again, so a user returning
    // after a while sees current data instead of waiting out the interval.
    const onVis = () => { if (typeof document !== "undefined" && !document.hidden) tick(); };
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      clearInterval(id);
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}
