import { NextRequest } from "next/server";

import { proxyBotRequest, type ProxyOptions } from "@/lib/server/bot-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function readBody(
  request: NextRequest,
): Promise<ArrayBuffer | undefined> {
  if (request.method === "GET" || request.method === "HEAD") return undefined;
  try {
    return await request.arrayBuffer();
  } catch {
    return undefined;
  }
}

async function handle(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<Response> {
  const { path = [] } = await context.params;

  const options: ProxyOptions = {
    segments: path,
    method: request.method,
    search: request.nextUrl.search,
    body: await readBody(request),
    contentType: request.headers.get("content-type"),
  };

  const { response } = await proxyBotRequest(request, options);
  return response;
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
