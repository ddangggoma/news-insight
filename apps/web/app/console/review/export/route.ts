import { api } from "@/lib/api";
import { currentUser } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const user = await currentUser();
  if (!user) return new Response("login required", { status: 401 });
  if (user.role !== "admin" || user.must_change_password) return new Response("admin only", { status: 403 });
  const csv = await api.text("/api/admin/reviews/export.csv");
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="relevance-reviews.csv"',
    },
  });
}
