import { NextRequest } from 'next/server';
import { proxyAdminRequest } from '@/lib/server/admin-proxy';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const page = searchParams.get('page') || '1';
  const limit = searchParams.get('limit') || '50';

  return proxyAdminRequest(req, `/api/v1/users?page=${page}&limit=${limit}`);
}
