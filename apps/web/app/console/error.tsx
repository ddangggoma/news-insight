"use client";

import { AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { RetryButton } from "@/components/retry-button";

export default function ConsoleError({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle />
      <AlertTitle>데이터를 불러오지 못했습니다</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{error.message}</p>
        <RetryButton variant="outline" size="sm" retry={retry} />
      </AlertDescription>
    </Alert>
  );
}
