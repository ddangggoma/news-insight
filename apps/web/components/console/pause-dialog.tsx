"use client";

import { Pause } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function PauseDialog({ action }: { action: (reason: string) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, startTransition] = useTransition();
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Pause /> 일시정지
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>소스 일시정지</DialogTitle>
          <DialogDescription>재개할 때까지 수집하지 않습니다. 사유는 검증 이력에 남습니다.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="pause-reason">사유</Label>
          <Input id="pause-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="예: 약관 재검토" />
        </div>
        <DialogFooter>
          <Button
            disabled={pending || reason.trim().length === 0}
            onClick={() =>
              startTransition(async () => {
                try {
                  await action(reason.trim());
                  toast.success("일시정지했습니다");
                  setOpen(false);
                } catch (error) {
                  toast.error(error instanceof Error ? error.message : "요청에 실패했습니다");
                }
              })
            }
          >
            {pending ? "처리 중…" : "일시정지"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
