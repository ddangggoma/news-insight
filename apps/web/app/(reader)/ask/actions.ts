"use server";

import { ApiError } from "@/lib/api";
import type { AskOutcome, AskResult } from "@/lib/ask-types";
import { readerPost } from "@/lib/reader-api";
import { requireUser } from "@/lib/session";

const DAYS = new Set([7, 30, 90, 180, 365]);

export async function askQuestion(input: { question: string; days: number; node: string | null }): Promise<AskOutcome> {
  await requireUser();
  const question = input.question.trim().slice(0, 500);
  if (question.length < 2) return { ok: false, error: "질문을 두 글자 이상 입력하세요." };
  const days = DAYS.has(input.days) ? input.days : 30;
  const node = input.node && /^[a-z][a-z0-9_]{1,39}:\S{1,80}$/.test(input.node) ? input.node : null;
  try {
    return { ok: true, result: await readerPost<AskResult>("/ask", { question, days, node }) };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 429) return { ok: false, error: "다른 질문에 답하는 중입니다. 잠시 후 다시 시도하세요." };
    if (error.status === 503) return { ok: false, error: "로컬 모델(LM Studio)에 연결할 수 없습니다. 잠시 후 다시 시도하세요." };
    return { ok: false, error: "답을 만들지 못했습니다." };
  }
}
