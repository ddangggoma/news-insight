import type { AccessKind } from "@/lib/access-log";
import type { Role } from "@/lib/auth";

export type { AccessKind };

export interface AccessAccount {
  id: number;
  username: string;
  name: string;
  role: Role;
}

export interface AccessRequest {
  id: number;
  at: string;
  user: AccessAccount;
  kind: AccessKind;
  method: string;
  path: string;
  query: string | null;
  ip: string | null;
}

export interface LoginEvent {
  id: number;
  at: string;
  event: string;
  user: AccessAccount | null;
  ip: string | null;
  user_agent: string | null;
}

export interface AccountUsage {
  user: AccessAccount;
  requests: number;
  pages: number;
  actions: number;
  ips: number;
  last_at: string | null;
  last_ip: string | null;
  logins: number;
  failures: number;
}

export interface PathUsage {
  path: string;
  kind: AccessKind;
  count: number;
  last_at: string;
}

export interface UsageReport {
  accounts: AccountUsage[];
  paths: PathUsage[];
  keep_days: number;
}

export const KIND_LABEL: Record<AccessKind, string> = {
  page: "페이지",
  action: "작업",
  api: "데이터 요청",
  media: "음성 브리핑",
};

export const LOGIN_OUTCOME_LABEL = { ok: "로그인", fail: "실패", logout: "로그아웃" } as const;

export const EVENT_LABEL: Record<string, string> = {
  signup: "가입 신청",
  create_admin: "관리자 계정 생성(CLI)",
  login_ok: "로그인",
  login_fail: "로그인 실패",
  login_locked: "잠긴 계정으로 로그인 시도",
  login_pending: "승인 전 로그인 시도",
  login_rejected: "거절된 계정으로 로그인 시도",
  login_suspended: "정지된 계정으로 로그인 시도",
  locked: "연속 실패로 잠김",
  logout: "로그아웃",
  logout_others: "다른 기기 모두 로그아웃",
  approve: "승인",
  reject: "거절",
  suspend: "정지",
  reactivate: "다시 사용",
  role_admin: "관리자로 변경",
  role_reader: "독자로 변경",
  password_change: "비밀번호 변경",
  password_reset: "비밀번호 초기화",
  unlock: "잠금 해제",
};

// Docker Desktop hands every connection to Caddy from its VM gateway (ops/Caddyfile): this
// address means the visitor's own address never reached the site.
export const DOCKER_GATEWAY = "192.168.65.1";

const BROWSERS: [RegExp, string][] = [
  [/Edg(?:e|A|iOS)?\/(\d+)/, "Edge"],
  [/Whale\/(\d+)/, "Whale"],
  [/SamsungBrowser\/(\d+)/, "Samsung"],
  [/Firefox\/(\d+)/, "Firefox"],
  [/CriOS\/(\d+)/, "Chrome"],
  [/Chrome\/(\d+)/, "Chrome"],
  [/Version\/(\d+)[\d.]* (?:Mobile\/\S+ )?Safari/, "Safari"],
];
const SYSTEMS: [RegExp, string][] = [
  [/iPhone/, "iPhone"],
  [/iPad/, "iPad"],
  [/Android/, "Android"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "macOS"],
  [/Linux/, "Linux"],
];

/** "Chrome 141 · macOS" from a user agent; the raw string when nothing is recognized. */
export function describeAgent(agent: string | null): string {
  if (!agent) return "";
  const browser = BROWSERS.map(([pattern, name]) => {
    const match = pattern.exec(agent);
    return match ? `${name} ${match[1]}` : null;
  }).find(Boolean);
  const system = SYSTEMS.find(([pattern]) => pattern.test(agent))?.[1];
  const parts = [browser, system].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : agent;
}
