// Let first-load read requests pass through the newly installed worker so they
// are available offline immediately, rather than only after a second visit.
const workerReady = new Promise<void>(resolve => {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator) || navigator.serviceWorker.controller) { resolve(); return; }
  const finish = () => { navigator.serviceWorker.removeEventListener('controllerchange', finish); resolve(); };
  navigator.serviceWorker.addEventListener('controllerchange', finish, { once: true });
  setTimeout(finish, 1500); // Development / unsupported installation fallback.
});
export type Data = Record<string, any>;
export async function api<T = Data>(path: string, options: RequestInit = {}): Promise<T> {
  await workerReady;
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
  });
  let data: any;
  try { data = await response.json(); } catch { throw new Error('The local server returned an unreadable response.'); }
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: Data) => `${d.loc?.join('.')}: ${d.msg}`).join('; ') : `Request failed (${response.status})`);
  }
  return data as T;
}
export const save = <T = Data>(path: string, body: unknown, method = 'POST') => api<T>(path, { method, body: JSON.stringify(body) });
export const dollars = (cents: number | null | undefined) => cents == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
export const percent = (value: number | null | undefined) => value == null ? '—' : `${new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value)}%`;
export function amountCents(value: string): number {
  if (!/^\d+(\.\d{0,2})?$/.test(value)) throw new Error('Enter an amount with at most two decimal places.');
  const [whole, fraction = ''] = value.split('.');
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
}
