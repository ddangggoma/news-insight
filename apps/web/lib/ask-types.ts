export interface AskEvidence {
  n: number;
  item_id: number;
  title: string;
  source: string;
  url: string;
  first_seen_at: string;
  similarity: number;
}

export interface AskResult {
  question: string;
  answer: string;
  evidence: AskEvidence[];
  cited: number[];
  model: string;
  took_ms: number;
}

export type AskOutcome = { ok: true; result: AskResult } | { ok: false; error: string };

export interface ScopeOption {
  value: string;
  label: string;
}

/** Splits an answer into text and [n] citation parts (only numbers that have evidence). */
export function citationParts(answer: string, count: number): (string | number)[] {
  const parts: (string | number)[] = [];
  let last = 0;
  for (const match of answer.matchAll(/\[(\d{1,2})\]/g)) {
    const n = Number(match[1]);
    if (n < 1 || n > count) continue;
    if (match.index > last) parts.push(answer.slice(last, match.index));
    parts.push(n);
    last = match.index + match[0].length;
  }
  if (last < answer.length) parts.push(answer.slice(last));
  return parts;
}
