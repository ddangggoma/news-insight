/**
 * Signal regression on the synthetic radar corpus (checklist QA-1).
 *
 * `scripts/dev.sh radar-qa` seeds apps/api/scripts/radar_demo_seed.py at a pinned time, exports the
 * radar responses with scripts/radar_qa_export.py and runs this file with RADAR_QA_DIR set. Each
 * planted pattern must be matched by its rule; ranking between matches is not checked, so a new
 * random draw in the seed does not break the test, but a rule or statistic that stops seeing a
 * planted pattern does. Skipped without RADAR_QA_DIR (plain `npm test`).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import type { Radar } from "@/lib/reader-types";
import { radarSignals, type SignalCandidates, type SignalTone } from "@/lib/radar-signals";

const dir = process.env.RADAR_QA_DIR;

function read(view: string): { radar: Radar; candidates: SignalCandidates } {
  const radar = JSON.parse(readFileSync(join(dir!, `${view}.json`), "utf8")) as Radar;
  const candidates: SignalCandidates = {};
  radarSignals(radar, candidates);
  return { radar, candidates };
}

// view, rule, planted topic, what the seed planted
const PLANTED: [string, SignalTone, string, string][] = [
  ["month-2026-09", "surge", "ai__ai_agents", "AI agents surge"],
  ["month-2026-09", "surge", "robotics_mobility__humanoid_embodied", "humanoid surge"],
  ["week-2026-W40", "surge", "ai__ai_agents", "AI agents surge (last week)"],
  ["week-2026-W40", "new", "유리기판", "glass substrate first appears"],
  ["week-2026-W40", "new", "하이브리드본딩", "hybrid bonding first appears"],
  ["month-2026-09", "new", "vla모델", "VLA first appears"],
  ["week-2026-W40", "back", "메타버스", "메타버스 returns after months of silence"],
  ["month-2026-09", "cool", "display_av__xr_spatial", "XR falls"],
  ["month-2026-09", "cool", "connectivity__cellular_5g_6g", "6G falls"],
  ["week-2026-W40", "early", "robotics_mobility__humanoid_embodied", "Embodied AI is research-led"],
  ["month-2026-09", "early", "security__privacy_crypto", "PQC is research-led"],
  ["week-2026-W40", "shift", "display_av__display_panel", "OLED·MicroLED moves from research to market"],
  ["month-2026-09", "shift", "display_av__display_panel", "OLED·MicroLED shift (month)"],
  ["week-2026-W40", "hype", "robotics_mobility__autonomous_driving", "robotaxi chatter without research"],
  ["week-2026-W40", "thin", "platform_sw__device_os", "One UI spike from one vendor newsroom"],
  ["month-2026-09", "gap", "claudecode", "Claude Code: no Korean source"],
  ["quarter-2026-Q3", "gap", "webassembly", "WASM: no Korean source"],
  ["month-2026-09", "pull", "platform_sw__developer_tools", "coding agents: stars ahead of coverage"],
  ["week-2026-W39", "event", "스마트링", "health launch event day"],
  ["month-2026-09", "link", "동형암호×포스트양자암호", "PQC × homomorphic encryption, newly linked"],
];

describe.skipIf(!dir)("radar signals find the planted patterns", () => {
  test.each(PLANTED)("%s %s %s (%s)", (view, tone, key) => {
    expect(read(view).candidates[tone] ?? []).toContain(key);
  });

  test("falling and research-free themes are not read as rising", () => {
    for (const view of ["week-2026-W39", "week-2026-W40", "month-2026-09", "quarter-2026-Q3"]) {
      const { candidates } = read(view);
      expect(candidates.surge ?? []).not.toContain("connectivity__cellular_5g_6g");
      // XR barely gets stars: developer pull must come from elsewhere
      expect(candidates.pull ?? []).not.toContain("display_av__xr_spatial");
    }
  });

  test("every view yields cards and no theme is shown twice", () => {
    for (const view of ["week-2026-W39", "week-2026-W40", "month-2026-09", "quarter-2026-Q3"]) {
      const signals = radarSignals(read(view).radar);
      expect(signals.length).toBeGreaterThanOrEqual(6);
      const themes = signals.filter((s) => s.focus.kind === "theme").map((s) => s.focus.key);
      expect(new Set(themes).size).toBe(themes.length);
    }
  });
});
