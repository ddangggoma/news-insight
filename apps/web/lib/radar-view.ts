import { param, type SearchParams } from "@/lib/params";
import { parseFocus, type RadarView } from "@/lib/radar";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import { FIELD_LABEL, SIGNAL_LABEL } from "@/lib/taxonomy";

/** Radar view state from the URL; unknown values fall back to the defaults. */
export function radarView(sp: SearchParams): RadarView {
  const scopeParam = param(sp, "scope");
  const raw = sp.signal;
  const signal = (Array.isArray(raw) ? raw : raw ? [raw] : []).filter((s, i, all) => s in SIGNAL_LABEL && all.indexOf(s) === i);
  const field = param(sp, "field");
  return {
    scope: scopeParam && scopeParam in SCOPES ? (scopeParam as Scope) : "relevant",
    signal,
    field: field && field in FIELD_LABEL ? field : null,
    focus: parseFocus(param(sp, "focus")),
  };
}
