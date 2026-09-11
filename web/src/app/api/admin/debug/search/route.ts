import { NextRequest } from 'next/server';
import { proxyAdminRequest } from '@/lib/server/admin-proxy';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const q = searchParams.get('q') || '';

  return proxyAdminRequest(request, `/api/v1/admin/debug/search?q=${encodeURIComponent(q)}`);
}
