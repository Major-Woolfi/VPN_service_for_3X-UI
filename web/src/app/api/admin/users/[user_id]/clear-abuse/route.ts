import { NextRequest, NextResponse } from 'next/server';
import { proxyAdminRequest } from '@/lib/server/admin-proxy';

export async function POST(request: NextRequest, { params }: { params: Promise<{ user_id: string }> }) {
  const body = await request.json();
  const { user_id: userId } = await params;

  return proxyAdminRequest(
    request,
    `/api/v1/admin/users/${userId}/clear-abuse`,
    { method: 'POST', body: JSON.stringify(body) }
  );
}
