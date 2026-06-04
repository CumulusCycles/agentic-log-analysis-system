import { useEffect, useRef } from "react";

// Runs `fn` once on mount and then every `intervalMs`. Pauses while the tab is
// hidden (no point burning the token clock on offscreen polling) and resumes
// on visibilitychange. Cancels on unmount.
//
// `fn` is captured in a ref so the polling loop doesn't restart when the
// caller passes a fresh closure on each render.
export function usePolling(fn: () => void | Promise<void>, intervalMs: number) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let cancelled = false;

    function run() {
      if (cancelled) return;
      if (typeof document !== "undefined" && document.hidden) return;
      void fnRef.current();
    }

    run();
    const handle = window.setInterval(run, intervalMs);

    function onVisibility() {
      if (!document.hidden) run();
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      window.clearInterval(handle);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [intervalMs]);
}
