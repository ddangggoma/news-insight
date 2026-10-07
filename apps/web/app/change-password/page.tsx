import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { logout } from "@/app/login/actions";
import { PasswordForm } from "@/components/auth/password-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { currentUser } from "@/lib/session";

export const metadata: Metadata = { title: "비밀번호 변경", robots: { index: false } };

// After an admin reset: the temporary password works only to reach this page (proxy.ts).
export default async function ForcedPasswordPage() {
  const user = await currentUser();
  if (!user) redirect("/login");
  if (!user.must_change_password) redirect("/account");
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1>새 비밀번호 설정</h1>
          </CardTitle>
          <CardDescription>관리자가 발급한 임시 비밀번호로 로그인했습니다. 계속하려면 새 비밀번호를 정하세요.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <PasswordForm currentLabel="임시 비밀번호" />
          <form action={logout}>
            <Button type="submit" variant="ghost" size="sm">
              로그아웃
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
