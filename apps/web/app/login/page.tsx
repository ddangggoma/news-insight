import type { Metadata } from "next";
import Link from "next/link";

import { LoginForm } from "@/components/reader/login-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { param, type SearchParams } from "@/lib/params";

export const metadata: Metadata = { title: "관리자 로그인", robots: { index: false } };

export default async function LoginPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const expired = param(await searchParams, "error") === "expired";
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>운영 콘솔 로그인</h1>
          </CardTitle>
          <CardDescription>등록된 관리자 이메일로 일회용 로그인 링크를 보냅니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {expired ? (
            <p role="alert" className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              링크가 만료되었거나 이미 사용되었습니다. 새 링크를 요청하세요.
            </p>
          ) : null}
          <LoginForm />
          <Link href="/" className="block text-center text-sm text-muted-foreground hover:text-foreground">
            ← 오늘의 브리핑으로
          </Link>
        </CardContent>
      </Card>
    </main>
  );
}
