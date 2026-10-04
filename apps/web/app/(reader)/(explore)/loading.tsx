import { Skeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <main className="mx-auto max-w-[1440px] space-y-4 px-4 py-5 md:px-6" aria-busy>
      <Skeleton className="h-20 w-full" />
      {Array.from({ length: 5 }, (_, index) => (
        <Skeleton key={index} className="h-24 w-full" />
      ))}
    </main>
  );
}
