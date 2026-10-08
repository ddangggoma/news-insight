"use client";

import { useActionState } from "react";

import { type PasswordState, changePassword } from "@/app/account/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const FIELDS = [
  { name: "current", label: "현재 비밀번호", autoComplete: "current-password" },
  { name: "password", label: "새 비밀번호", autoComplete: "new-password" },
  { name: "confirm", label: "새 비밀번호 확인", autoComplete: "new-password" },
] as const;

export function PasswordForm({ currentLabel }: { currentLabel?: string }) {
  const [state, action, pending] = useActionState<PasswordState, FormData>(changePassword, {});
  const errors = state.errors ?? {};
  return (
    <form action={action} className="space-y-3">
      {FIELDS.map((field) => (
        <div key={field.name} className="space-y-1.5">
          <Label htmlFor={field.name}>{field.name === "current" && currentLabel ? currentLabel : field.label}</Label>
          <Input
            id={field.name}
            name={field.name}
            type="password"
            autoComplete={field.autoComplete}
            required
            maxLength={128}
            aria-invalid={Boolean(errors[field.name])}
            aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
          />
          {errors[field.name] ? (
            <p id={`${field.name}-error`} className="text-sm text-destructive">
              {errors[field.name]}
            </p>
          ) : null}
        </div>
      ))}
      <p className="text-xs text-muted-foreground">10자 이상. 흔한 비밀번호와 아이디가 들어간 비밀번호는 쓸 수 없습니다.</p>
      {errors.form ? (
        <p role="alert" className="text-sm text-destructive">
          {errors.form}
        </p>
      ) : null}
      <Button type="submit" disabled={pending}>
        {pending ? "바꾸는 중…" : "비밀번호 변경"}
      </Button>
    </form>
  );
}
