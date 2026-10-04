import { param, type SearchParams } from "@/lib/params";
import { parseFocus, type RadarView } from "@/lib/radar";
import { SCOPES, type Scope } from "@/lib/reader-filters";
import { BUSINESS_LABEL, FIELD_LABEL } from "@/lib/taxonomy";

/** Radar view state from the URL; unknown values fall back to the defaults. */
export function radarView(sp: SearchParams): RadarView {
  const scopeParam = param(sp, "scope");
  const raw = sp.business;
  const business = (Array.isArray(raw) ? raw : raw ? [raw] : []).filter((b, i, all) => b in BUSINESS_LABEL && all.indexOf(b) === i);
  const field = param(sp, "field");
  return {
    scope: scopeParam && scopeParam in SCOPES ? (scopeParam as Scope) : "relevant",
    business,
    field: field && field in FIELD_LABEL ? field : null,
    focus: parseFocus(param(sp, "focus")),
  };
}
