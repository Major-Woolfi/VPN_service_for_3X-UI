export function sanitizeInput(input: string): string {
  return input.replace(/[<>"'&]/g, '').trim();
}

export function isValidUsername(username: string): boolean {
  return /^[a-zA-Z0-9_\-]{3,50}$/.test(username);
}

export function isValidPassword(password: string): boolean {
  return password.length >= 10;
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
