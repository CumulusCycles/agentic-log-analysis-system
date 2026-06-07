// Shared time-window widget used by Log Explorer + Vectorstore Stats.
//
// Four presets — `1h`, `24h`, `7d`, and `custom`. When `custom` is active,
// the two `<input type="datetime-local">` fields are enabled; otherwise
// disabled. The component is fully controlled: parents own (`preset`,
// `customSince`, `customUntil`) and react to `onChange` calls that carry
// the resolved (`since`, `until`) ISO strings together with the new preset
// so the parent can persist its filter state and refetch in a single render.

import { useMemo } from "react";

import {
  resolveTimeWindow,
  type TimeWindowChange,
  type TimeWindowPreset,
} from "../lib/time-window";

interface Props {
  value: TimeWindowPreset;
  customSince: string | null;
  customUntil: string | null;
  onChange: (next: TimeWindowChange) => void;
  // Optional id-prefix so two selectors can coexist on the same page
  // (LogExplorer + future polled views) without colliding radio names.
  idPrefix?: string;
}

const PRESETS: { id: TimeWindowPreset; label: string }[] = [
  { id: "1h", label: "Last 1h" },
  { id: "24h", label: "Last 24h" },
  { id: "7d", label: "Last 7d" },
  { id: "custom", label: "Custom" },
];

export function TimeWindowSelector({
  value,
  customSince,
  customUntil,
  onChange,
  idPrefix = "time-window",
}: Props) {
  const radioName = `${idPrefix}-radio`;
  const sinceId = `${idPrefix}-since`;
  const untilId = `${idPrefix}-until`;
  const isCustom = value === "custom";

  const resolved = useMemo(
    () => resolveTimeWindow(value, customSince, customUntil),
    [value, customSince, customUntil],
  );

  function emit(next: Partial<TimeWindowChange>) {
    const merged = {
      preset: next.preset ?? value,
      customSince: next.customSince ?? customSince,
      customUntil: next.customUntil ?? customUntil,
    };
    const resolvedNext = resolveTimeWindow(merged.preset, merged.customSince, merged.customUntil);
    onChange({ ...merged, ...resolvedNext });
  }

  function onPresetChange(preset: TimeWindowPreset) {
    emit({ preset });
  }

  function onSinceChange(localValue: string) {
    emit({ customSince: localValue || null });
  }

  function onUntilChange(localValue: string) {
    emit({ customUntil: localValue || null });
  }

  return (
    <fieldset>
      <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Time window
      </legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <label
            key={p.id}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
          >
            <input
              type="radio"
              name={radioName}
              checked={value === p.id}
              onChange={() => onPresetChange(p.id)}
              data-testid={`${idPrefix}-${p.id}`}
            />
            {p.label}
          </label>
        ))}
      </div>
      {isCustom && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2" data-testid={`${idPrefix}-custom-fields`}>
          <label className="flex flex-col text-xs text-slate-600">
            <span className="mb-0.5">From</span>
            <input
              id={sinceId}
              type="datetime-local"
              value={customSince ?? ""}
              onChange={(e) => onSinceChange(e.target.value)}
              data-testid={`${idPrefix}-custom-since`}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-slate-500 focus:outline-none"
            />
          </label>
          <label className="flex flex-col text-xs text-slate-600">
            <span className="mb-0.5">To</span>
            <input
              id={untilId}
              type="datetime-local"
              value={customUntil ?? ""}
              onChange={(e) => onUntilChange(e.target.value)}
              data-testid={`${idPrefix}-custom-until`}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs focus:border-slate-500 focus:outline-none"
            />
          </label>
        </div>
      )}
      {/* Status hint — only visible when the operator picked Custom and the
          inputs are incomplete. Defence against silently sending one-sided
          ranges that span the whole corpus. */}
      {isCustom && (resolved.since === null || resolved.until === null) && (
        <p className="mt-1 text-[11px] text-slate-500">
          Pick both From and To to apply a custom range.
        </p>
      )}
    </fieldset>
  );
}
