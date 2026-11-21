import { NextRequest } from "next/server";
import { proxyAdminRequest } from "@/lib/server/admin-proxy";
import { readJsonBody } from "@/lib/server/json-body";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ user_id: string }> },
) {
  const { body, error } = await readJsonBody(request);
  if (error) return error;

  const { user_id: userId } = await params;

  return proxyAdminRequest(request, `/api/v1/admin/users/${encodeURIComponent(userId)}/ip-limit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? null),
  });
}
