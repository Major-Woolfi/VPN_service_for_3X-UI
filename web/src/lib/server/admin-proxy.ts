import 'server-only';

import { NextRequest, NextResponse } from 'next/server';

import { DEFAULT_API_BASE } from '../api';
import type { SanitizedUser } from '../types';

const REQUEST_TIMEOUT_MS = 10_000;
const SESSION_COOKIE_NAME = 'vpn_token';

function getBotApiBase(): string {
  return (process.env.BOT_API_URL || DEFAULT_API_BASE)
    .replace(/\/api\/v1\/?$/, '')
    .replace(/\/$/, '');
}

function sanitizePath(path: string): string {
  const cleaned = path.replace(/\.\./g, '').replace(/\/+/g, '/').replace(/[	\n\r]/g, '');
  return cleaned.startsWith('/') ? cleaned : `/${cleaned}`;
}

function extractSessionToken(request: NextRequest): string | null {
  const fromCookie = request.cookies.get(SESSION_COOKIE_NAME)?.value;
  if (fromCookie) return fromCookie;

  const authorization = request.headers.get('authorization');
  if (authorization?.startsWith('Bearer ')) {
    return authorization.slice('Bearer '.length);
  }
  return null;
}

async function readUpstreamResponse(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return response.json();
  }

  const text = await response.text();
  return text ? { error: text } : { error: response.statusText };
}

interface VerifyAdminResult {
  isAdmin: boolean;
  status: number;
}

async function verifyAdmin(token: string): Promise<VerifyAdminResult> {
  try {
    const response = await fetch(`${getBotApiBase()}/api/v1/profile`, {
      cache: 'no-store',
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { isAdmin: false, status: response.status };
    }
    const data = (await response.json().catch(() => null)) as (SanitizedUser & {
      is_admin?: boolean;
    }) | null;
    return { isAdmin: !!data && !!data.is_admin, status: 200 };
  } catch {
    return { isAdmin: false, status: 503 };
  }
}

export async function proxyAdminRequest(
  request: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  const token = extractSessionToken(request);

  if (!token) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const authorization = `Bearer ${token}`;

  try {
    const { isAdmin, status } = await verifyAdmin(token);

    if (!isAdmin) {
      const errorMessage = status === 401 ? 'Unauthorized' : 'Forbidden';
      return NextResponse.json({ error: errorMessage }, { status });
    }

    const sanitized = sanitizePath(path);
    const response = await fetch(`${getBotApiBase()}${sanitized}`, {
      ...init,
      cache: 'no-store',
      headers: {
        Authorization: authorization,
        ...init.headers,
      },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const data = await readUpstreamResponse(response);

    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    const isTimeout = error instanceof DOMException && error.name === 'TimeoutError';

    return NextResponse.json(
      { error: isTimeout ? 'Bot API request timed out' : 'Bot API unavailable' },
      { status: isTimeout ? 504 : 503 },
    );
  }
}
