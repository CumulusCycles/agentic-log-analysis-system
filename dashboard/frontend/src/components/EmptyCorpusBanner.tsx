import { Link } from "react-router-dom";

// One-line nudge shown on the Overview when Chroma has zero embedded entries.
// The corpus_empty flag is computed server-side in /api/status (PR 3).
export function EmptyCorpusBanner() {
  return (
    <div
      role="status"
      className="mt-3 flex items-center justify-between rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900"
      data-testid="empty-corpus-banner"
    >
      <span>
        Embedded-log corpus is empty. Run a scenario to populate it before semantic search and the
        upcoming AI Chat will return anything useful.
      </span>
      <Link
        to="/log-generator"
        className="ml-3 rounded-md bg-amber-700 px-3 py-1 text-xs font-medium text-white hover:bg-amber-800"
      >
        Open Log Generator
      </Link>
    </div>
  );
}
