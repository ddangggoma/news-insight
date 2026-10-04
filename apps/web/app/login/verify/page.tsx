import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { completeLogin } from "@/app/login/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { param, type SearchParams } from "@/lib/params";

export const metadata: Metadata = { title: "로그인 확인", robots: { index: false }, referrer: "no-referrer" };

// The link only shows a button: mail scanners that prefetch GET links cannot burn the token.
export default async function VerifyPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const token = param(await searchParams, "token");
  if (!token) redirect("/login");
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>운영 콘솔 로그인</h1>
          </CardTitle>
          <CardDescription>이 브라우저에서 관리자 세션을 시작합니다 (14일 유지).</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={completeLogin}>
            <input type="hidden" name="token" value={token} />
            <Button type="submit" className="w-full">
              로그인
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
