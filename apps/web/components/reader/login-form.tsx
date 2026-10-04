"use client";

import { MailCheck } from "lucide-react";
import { useActionState } from "react";

import { type LoginState, requestLogin } from "@/app/login/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function LoginForm() {
  const [state, action, pending] = useActionState<LoginState, FormData>(requestLogin, { sent: false });
  if (state.sent) {
    return (
      <div role="status" className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
        <MailCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
        <p>
          관리자 주소라면 로그인 링크를 보냈습니다. 메일의 링크는 15분 동안 한 번만 쓸 수 있습니다.
        </p>
      </div>
    );
  }
  return (
    <form action={action} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="email">관리자 이메일</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required placeholder="name@example.com" />
      </div>
      {state.error ? (
        <p role="alert" className="text-sm text-destructive">
          {state.error}
        </p>
      ) : null}
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "보내는 중…" : "로그인 링크 받기"}
      </Button>
    </form>
  );
}
