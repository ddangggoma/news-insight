import type { Metadata } from "next";

import { logoutOthers } from "@/app/account/actions";
import { PasswordForm } from "@/components/auth/password-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import { param, type SearchParams } from "@/lib/params";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "내 계정", robots: { index: false } };

const ROLE_LABEL = { reader: "독자", admin: "관리자" } as const;

export default async function AccountPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const user = await requireUser();
  const query = await searchParams;
  const notice = param(query, "changed")
    ? "비밀번호를 바꿨습니다. 다른 기기의 로그인은 모두 끝났습니다."
    : param(query, "others")
      ? "다른 기기의 로그인을 모두 끝냈습니다."
      : null;
  return (
    <main className="mx-auto max-w-xl space-y-4 px-4 py-6 md:px-6">
      <h1 className="text-xl font-semibold">내 계정</h1>
      {notice ? (
        <p role="status" className="rounded-md border bg-muted/40 p-3 text-sm">
          {notice}
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>계정 정보</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[6rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">아이디</dt>
            <dd>{user.username}</dd>
            <dt className="text-muted-foreground">이름</dt>
            <dd>{user.name}</dd>
            <dt className="text-muted-foreground">권한</dt>
            <dd>{ROLE_LABEL[user.role]}</dd>
            <dt className="text-muted-foreground">마지막 로그인</dt>
            <dd>{formatDateTime(user.last_login_at)}</dd>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>비밀번호 변경</h2>
          </CardTitle>
          <CardDescription>바꾸면 다른 기기의 로그인은 모두 끝납니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <PasswordForm />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>로그인한 기기</h2>
          </CardTitle>
          <CardDescription>이 브라우저를 뺀 모든 기기에서 로그아웃합니다.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={logoutOthers}>
            <Button type="submit" variant="outline">
              다른 기기 모두 로그아웃
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
