import { NextRequest } from "next/server";

import {
  MAX_REQUEST_BODY_BYTES,
  proxyBotRequest,
  type ProxyOptions,
} from "@/lib/server/bot-proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface BodyResult {
  body: ArrayBuffer | undefined;
  tooLarge: boolean;
}

async function readBody(request: NextRequest): Promise<BodyResult> {
  if (request.method === "GET" || request.method === "HEAD") {
    return { body: undefined, tooLarge: false };
  }
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_REQUEST_BODY_BYTES) {
    return { body: undefined, tooLarge: true };
  }
  const body = request.body;
  if (!body) return { body: undefined, tooLarge: false };
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_REQUEST_BODY_BYTES) {
        await reader.cancel();
        return { body: undefined, tooLarge: true };
      }
      chunks.push(value);
    }
  } catch {
    return { body: undefined, tooLarge: false };
  }
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { body: merged.buffer, tooLarge: false };
}

async function handle(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
): Promise<Response> {
  const { path = [] } = await context.params;
  const { body, tooLarge } = await readBody(request);
  if (tooLarge) {
    return Response.json({ Error: "request_body_too_large" }, { status: 413 });
  }

  const options: ProxyOptions = {
    segments: path,
    method: request.method,
    search: request.nextUrl.search,
    body,
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







