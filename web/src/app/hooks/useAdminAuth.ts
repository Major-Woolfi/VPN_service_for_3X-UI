"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Hook that requires admin authentication.
 * Redirects to /login if not authenticated, to /profile if not admin.
 * Returns the authenticated user when authorized.
 */
export function useAdminAuth(nextPage: string) {
  const { loading: authLoading, user: authUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (authLoading) return;
    if (!authUser) {
      router.replace(`/login?next=/admin/${nextPage}`);
      return;
    }
    if (!authUser.is_admin) {
      router.replace("/profile");
      return;
    }
  }, [authLoading, router, authUser, nextPage]);

  return { authLoading, authUser, isAuthed: Boolean(authUser && authUser.is_admin) };
}
