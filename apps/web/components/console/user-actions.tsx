"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { type ActionResult, type UserAction, actOnUser, resetUserPassword, setUserRole } from "@/app/console/users/actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SessionUser } from "@/lib/auth";

type Row = Pick<SessionUser, "id" | "username" | "name" | "role" | "status" | "locked">;

interface Step {
  label: string;
  done: string;
  run: () => Promise<ActionResult>;
  variant?: "default" | "outline" | "destructive";
  confirm?: string;
}

function steps(user: Row): Step[] {
  const act = (action: UserAction) => () => actOnUser(user.id, action);
  const list: Step[] = [];
  if (user.status === "pending") {
    list.push({ label: "승인", done: `${user.name} 님을 승인했습니다`, run: act("approve"), variant: "default" });
    list.push({ label: "거절", done: "가입 신청을 거절했습니다", run: act("reject"), variant: "destructive", confirm: `${user.name}(${user.username}) 님의 가입 신청을 거절할까요?` });
  }
  if (user.status === "rejected") list.push({ label: "승인", done: `${user.name} 님을 승인했습니다`, run: act("approve") });
  if (user.status === "active") {
    list.push(
      user.role === "admin"
        ? { label: "독자로 변경", done: "독자로 바꿨습니다", run: () => setUserRole(user.id, "reader") }
        : { label: "관리자로 변경", done: "관리자로 바꿨습니다", run: () => setUserRole(user.id, "admin"), confirm: `${user.name} 님에게 운영 콘솔과 사용자 승인 권한을 줄까요?` },
    );
    list.push({ label: "정지", done: "사용을 정지했습니다", run: act("suspend"), variant: "destructive", confirm: `${user.name} 님의 사용을 정지할까요? 로그인한 기기에서도 바로 로그아웃됩니다.` });
  }
  if (user.status === "suspended") list.push({ label: "다시 사용", done: "다시 쓸 수 있게 했습니다", run: act("reactivate") });
  if (user.locked) list.push({ label: "잠금 해제", done: "잠금을 풀었습니다", run: act("unlock") });
  return list;
}

export function UserActions({ user }: { user: Row }) {
  const [pending, startTransition] = useTransition();
  const [temporary, setTemporary] = useState<string | null>(null);

  function perform(step: Pick<Step, "done" | "run" | "confirm">) {
    if (step.confirm && !window.confirm(step.confirm)) return;
    startTransition(async () => {
      const result = await step.run();
      if (!result.ok) {
        toast.error(result.error ?? "요청에 실패했습니다");
        return;
      }
      if (result.temporaryPassword) setTemporary(result.temporaryPassword);
      else toast.success(step.done);
    });
  }

  const canReset = user.status === "active" || user.status === "suspended";
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {steps(user).map((step) => (
        <Button key={step.label} size="sm" variant={step.variant ?? "outline"} disabled={pending} onClick={() => perform(step)}>
          {step.label}
        </Button>
      ))}
      {canReset ? (
        <Button
          size="sm"
          variant="outline"
          disabled={pending}
          onClick={() =>
            perform({
              done: "",
              run: () => resetUserPassword(user.id),
              confirm: `${user.name} 님의 비밀번호를 초기화할까요? 지금 로그인한 기기에서는 로그아웃됩니다.`,
            })
          }
        >
          비밀번호 초기화
        </Button>
      ) : null}
      <Dialog open={temporary !== null} onOpenChange={(open) => !open && setTemporary(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>임시 비밀번호</DialogTitle>
            <DialogDescription>
              {user.name}({user.username}) 님에게 전해 주세요. 이 창을 닫으면 다시 볼 수 없습니다. 첫 로그인 때 새 비밀번호로 바꾸게 됩니다.
            </DialogDescription>
          </DialogHeader>
          <p className="rounded-md border bg-muted px-3 py-2 font-mono text-base select-all" data-testid="temporary-password">
            {temporary}
          </p>
          <DialogFooter>
            <Button onClick={() => setTemporary(null)}>닫기</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
