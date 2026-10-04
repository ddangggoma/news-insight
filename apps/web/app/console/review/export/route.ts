import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const csv = await api.text("/api/admin/reviews/export.csv");
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="relevance-reviews.csv"',
    },
  });
}
