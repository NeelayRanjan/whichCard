import { describe, expect, it, vi, afterEach } from 'vitest';
import { api, amountCents, dollars, percent, save } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('formatting and input units', () => {
  it('formats cents, rates and missing values', () => { expect(dollars(12345)).toBe('$123.45'); expect(dollars(-500)).toBe('-$5.00'); expect(dollars(null)).toBe('—'); expect(percent(4.567)).toBe('4.57%'); });
  it('parses decimal input without reward calculations', () => { expect(amountCents('42.10')).toBe(4210); expect(amountCents('0.29')).toBe(29); expect(() => amountCents('4.333')).toThrow(); expect(() => amountCents('-1')).toThrow(); });
});
describe('local API client', () => {
  it('returns recorded recommendation shape', async () => { const fixture = { ranked: [{ card_id: 'amex-gold', effective_rate_pct: 6, reasons: ['4x × 1.5c = 6%'] }], override: null }; const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture))); vi.stubGlobal('fetch', fetch); expect(await api('/now?category=dining')).toEqual(fixture); expect(fetch.mock.calls[0][0]).toBe('/api/now?category=dining'); });
  it('posts JSON and preserves error messages', async () => { const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'unknown card' }), { status: 422 })); vi.stubGlobal('fetch', fetch); await expect(save('/recommend', { amount_cents: 100 })).rejects.toThrow('unknown card'); expect(fetch.mock.calls[0][1].body).toBe('{"amount_cents":100}'); });
  it('handles validation arrays and malformed data', async () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ['body','amount'], msg: 'must be positive' }] }), { status: 422 }))); await expect(api('/x')).rejects.toThrow('body.amount: must be positive'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('broken'))); await expect(api('/x')).rejects.toThrow('unreadable'); });
  it('lets the browser set multipart boundaries', async () => { const fetch = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetch); await api('/import', { method: 'POST', body: new FormData() }); expect(fetch.mock.calls[0][1].headers).toBeUndefined(); });
});
