import { NextRequest } from "next/server";
import { proxyAdminRequest } from "@/lib/server/admin-proxy";

function parsePageParam(value: string | null, fallback: number, max: number): number {
  if (!value) return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) return fallback;
  return Math.min(parsed, max);
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = parsePageParam(searchParams.get("page"), 1, 10_000);
  const limit = parsePageParam(searchParams.get("limit"), 50, 200);
  const search = searchParams.get("search")?.trim() || "";
  const coOwner = searchParams.get("co_owner") === "1";

  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
  });
  if (search) {
    params.set("search", search);
  }
  if (coOwner) {
    params.set("co_owner", "true");
  }

  return proxyAdminRequest(req, `/api/v1/users?${params.toString()}`);
}
