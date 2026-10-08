"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useActionState } from "react";

import { type SignupField, type SignupState, signup } from "@/app/signup/actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function FieldError({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p id={id} className="text-sm text-destructive">
      {message}
    </p>
  ) : null;
}

export function SignupForm() {
  const [state, action, pending] = useActionState<SignupState, FormData>(signup, {});
  if (state.done) {
    return (
      <div role="status" className="space-y-3">
        <div className="flex items-start gap-3 rounded-lg border bg-muted/40 p-4 text-sm">
          <MailCheck className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
          <p>
            가입 신청이 접수되었습니다. <strong>관리자에게 승인을 요청하세요.</strong> 승인된 뒤에 로그인할 수 있습니다.
          </p>
        </div>
        <Link href="/login" className="block text-center text-sm font-medium underline-offset-4 hover:underline">
          로그인 화면으로
        </Link>
      </div>
    );
  }
  const errors = state.errors ?? {};
  const described = (field: SignupField, hint?: string) =>
    [errors[field] ? `${field}-error` : null, hint].filter(Boolean).join(" ") || undefined;
  return (
    <form action={action} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="username">아이디</Label>
        <Input
          id="username"
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          required
          minLength={4}
          maxLength={32}
          defaultValue={state.values?.username}
          aria-invalid={Boolean(errors.username)}
          aria-describedby={described("username", "username-hint")}
        />
        <p id="username-hint" className="text-xs text-muted-foreground">
          4~32자 영문 소문자, 숫자, 마침표(.), 밑줄(_), 하이픈(-)
        </p>
        <FieldError id="username-error" message={errors.username} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="name">이름</Label>
        <Input
          id="name"
          name="name"
          autoComplete="name"
          required
          maxLength={50}
          defaultValue={state.values?.name}
          aria-invalid={Boolean(errors.name)}
          aria-describedby={described("name")}
        />
        <FieldError id="name-error" message={errors.name} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="password">비밀번호</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={10}
          maxLength={128}
          aria-invalid={Boolean(errors.password)}
          aria-describedby={described("password", "password-hint")}
        />
        <p id="password-hint" className="text-xs text-muted-foreground">
          10자 이상. 흔한 비밀번호와 아이디가 들어간 비밀번호는 쓸 수 없습니다.
        </p>
        <FieldError id="password-error" message={errors.password} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="confirm">비밀번호 확인</Label>
        <Input
          id="confirm"
          name="confirm"
          type="password"
          autoComplete="new-password"
          required
          maxLength={128}
          aria-invalid={Boolean(errors.confirm)}
          aria-describedby={described("confirm")}
        />
        <FieldError id="confirm-error" message={errors.confirm} />
      </div>
      {/* honeypot: hidden from people and assistive technology */}
      <div aria-hidden className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label htmlFor="website">웹사이트</label>
        <input id="website" name="website" tabIndex={-1} autoComplete="off" />
      </div>
      <div className="space-y-1.5 rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
        <p>
          <strong className="text-foreground">개인정보 수집·이용</strong> 항목: 아이디, 이름, 비밀번호(복원할 수 없는 해시로만 저장).
          목적: 가입 승인과 사용자 표시. 보관: 탈퇴 시까지, 거절된 신청은 30일 뒤 삭제.
        </p>
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            name="consent"
            className="size-4"
            aria-invalid={Boolean(errors.consent)}
            aria-describedby={described("consent")}
          />
          동의합니다
        </label>
        <FieldError id="consent-error" message={errors.consent} />
      </div>
      {errors.form ? (
        <p role="alert" className="text-sm text-destructive">
          {errors.form}
        </p>
      ) : null}
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "신청하는 중…" : "가입 신청"}
      </Button>
    </form>
  );
}
