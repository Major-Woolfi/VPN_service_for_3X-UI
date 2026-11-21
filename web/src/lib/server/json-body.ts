import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import { MAX_REQUEST_BODY_BYTES } from "./bot-proxy";

interface JsonBodyResult {
  body: unknown;
  error: NextResponse | null;
}

function badRequest(message: string, status: number): NextResponse {
  return NextResponse.json({ Error: message }, { status });
}

export async function readJsonBody(request: NextRequest): Promise<JsonBodyResult> {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_REQUEST_BODY_BYTES) {
    return { body: null, error: badRequest("request_body_too_large", 413) };
  }

  let raw: string;
  try {
    raw = await request.text();
  } catch {
    return { body: null, error: badRequest("invalid_json", 400) };
  }

  if (new TextEncoder().encode(raw).byteLength > MAX_REQUEST_BODY_BYTES) {
    return { body: null, error: badRequest("request_body_too_large", 413) };
  }

  try {
    return { body: JSON.parse(raw) as unknown, error: null };
  } catch {
    return { body: null, error: badRequest("invalid_json", 400) };
  }
}
