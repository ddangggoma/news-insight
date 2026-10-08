import type { Metadata } from "next";
import Link from "next/link";

import { LoginForm } from "@/components/auth/login-form";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext } from "@/lib/auth";
import { param, type SearchParams } from "@/lib/params";

export const metadata: Metadata = { title: "로그인", robots: { index: false } };

export default async function LoginPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const next = safeNext(param(await searchParams, "next"));
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>DX 인텔리전스 로그인</h1>
          </CardTitle>
          <CardDescription>관리자가 승인한 계정만 로그인할 수 있습니다.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <LoginForm next={next === "/" ? undefined : next} />
          <p className="text-center text-sm text-muted-foreground">
            계정이 없나요?{" "}
            <Link href="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
              회원가입
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
