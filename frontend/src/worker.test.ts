import { afterEach, expect, it, vi } from 'vitest';
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); vi.resetModules(); });
it('waits for the first service worker to control API reads', async () => {
  vi.useFakeTimers(); vi.resetModules();
  const worker = Object.assign(new EventTarget(), { controller: null });
  vi.stubGlobal('navigator', { serviceWorker: worker });
  const fetch = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetch);
  const { api } = await import('./api');
  const pending = api('/config');
  await Promise.resolve(); expect(fetch).not.toHaveBeenCalled();
  worker.dispatchEvent(new Event('controllerchange'));
  await pending; expect(fetch).toHaveBeenCalledOnce();
});
it('does not hang when a service worker is unavailable in development', async () => {
  vi.useFakeTimers(); vi.resetModules();
  vi.stubGlobal('navigator', { serviceWorker: Object.assign(new EventTarget(), { controller: null }) });
  const fetch = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetch);
  const { api } = await import('./api'); const pending = api('/config');
  await vi.advanceTimersByTimeAsync(1500); await pending; expect(fetch).toHaveBeenCalledOnce();
});
