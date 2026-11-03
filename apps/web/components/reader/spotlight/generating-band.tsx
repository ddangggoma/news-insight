/** Shown while today's list is not published yet and an earlier day is on screen. */
export function GeneratingBand() {
  return (
    <p role="status" className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm">
      오늘 목록 생성 중
    </p>
  );
}
