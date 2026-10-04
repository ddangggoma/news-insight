import { api } from "@/lib/api";
import { currentAdmin } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  if (!(await currentAdmin())) return new Response("login required", { status: 401 });
  const csv = await api.text("/api/admin/reviews/export.csv");
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="relevance-reviews.csv"',
    },
  });
}
