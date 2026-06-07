// Shared helpers for the TimeWindowSelector widget. Lives outside the
// component file so react-refresh's HMR contract isn't broken
// (a `.tsx` file that exports both a component AND a regular function
// can't be hot-replaced cleanly).

export type TimeWindowPreset = "1h" | "24h" | "7d" | "custom";

export interface TimeWindowChange {
  preset: TimeWindowPreset;
  customSince: string | null;
  customUntil: string | null;
  since: string | null;
  until: string | null;
}

const PRESET_OFFSETS_MS: Record<Exclude<TimeWindowPreset, "custom">, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

// Resolve a preset to its (`since`, `until`) ISO strings. `custom` returns
// the operator-supplied bounds (converted from `datetime-local` to ISO Z).
export function resolveTimeWindow(
  preset: TimeWindowPreset,
  customSince: string | null,
  customUntil: string | null,
  now: Date = new Date(),
): { since: string | null; until: string | null } {
  if (preset === "custom") {
    return {
      since: localToIso(customSince),
      until: localToIso(customUntil),
    };
  }
  const offset = PRESET_OFFSETS_MS[preset];
  return {
    since: new Date(now.getTime() - offset).toISOString(),
    until: null,
  };
}

// `<input type="datetime-local">` emits "YYYY-MM-DDTHH:MM" interpreted as
// local time. Construct a Date from the same string and emit its ISO Z form
// so the backend (which treats incoming datetimes as UTC) sees the operator's
// intended instant.
function localToIso(localValue: string | null): string | null {
  if (!localValue) return null;
  const dt = new Date(localValue);
  if (Number.isNaN(dt.getTime())) return null;
  return dt.toISOString();
}
