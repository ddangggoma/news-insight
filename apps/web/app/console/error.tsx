"use client";

import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export default function ConsoleError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle />
      <AlertTitle>데이터를 불러오지 못했습니다</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{error.message}</p>
        <Button variant="outline" size="sm" onClick={reset}>
          다시 시도
        </Button>
      </AlertDescription>
    </Alert>
  );
}
