"use client";

import { CircleUser, LogOut, Settings, UserCog } from "lucide-react";
import Link from "next/link";

import { logout } from "@/app/login/actions";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface AccountSummary {
  name: string;
  admin: boolean;
}

export function AccountMenu({ user }: { user: AccountSummary }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`계정 메뉴: ${user.name}`} className="gap-1.5">
          <CircleUser className="size-4" aria-hidden />
          <span className="hidden max-w-[8rem] truncate sm:inline">{user.name}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel className="truncate">{user.name}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/account">
            <Settings aria-hidden />
            내 계정
          </Link>
        </DropdownMenuItem>
        {user.admin ? (
          <DropdownMenuItem asChild>
            <Link href="/console">
              <UserCog aria-hidden />
              운영 콘솔
            </Link>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <form action={logout}>
          <DropdownMenuItem asChild>
            <button type="submit" className="w-full">
              <LogOut aria-hidden />
              로그아웃
            </button>
          </DropdownMenuItem>
        </form>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
