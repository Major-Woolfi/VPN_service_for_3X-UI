import { NextRequest } from 'next/server';
import { proxyAdminRequest } from '@/lib/server/admin-proxy';

export async function GET(request: NextRequest) {
  return proxyAdminRequest(request, '/api/v1/admin/health');
}
