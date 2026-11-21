export function getErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return String(err);
}
