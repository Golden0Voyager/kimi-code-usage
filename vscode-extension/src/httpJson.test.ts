import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as https from 'https';

vi.mock('https', () => ({ get: vi.fn() }));

import { httpGetJson } from './httpJson';

function mockRoute(status: number, body: string) {
  const res = {
    statusCode: status,
    on: vi.fn((event: string, cb: (chunk?: string) => void) => {
      if (event === 'data') cb(body);
      if (event === 'end') cb();
    }),
  };
  vi.mocked(https.get).mockImplementation((_url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
    cb(res);
    return { on: vi.fn(), destroy: vi.fn() } as unknown as ReturnType<typeof https.get>;
  });
}

describe('httpGetJson', () => {
  beforeEach(() => {
    vi.mocked(https.get).mockReset();
  });

  it('resolves with status, body and parsed JSON on 2xx', async () => {
    mockRoute(200, '{"a":1}');
    const resp = await httpGetJson('https://x.test/p', 'key', '0.2.1');
    expect(resp).toEqual({ status: 200, body: '{"a":1}', json: { a: 1 } });
  });

  it('passes Bearer auth and versioned User-Agent headers', async () => {
    mockRoute(200, '{}');
    await httpGetJson('https://x.test/p', 'sk-key', '9.9.9');
    const opts = vi.mocked(https.get).mock.calls[0]![1] as { headers: Record<string, string> };
    expect(opts.headers['Authorization']).toBe('Bearer sk-key');
    expect(opts.headers['User-Agent']).toBe('kimi-usage-vscode/9.9.9');
  });

  it('resolves with json=null when the body is not valid JSON', async () => {
    mockRoute(200, 'not json');
    const resp = await httpGetJson('https://x.test/p', 'key', '0.2.1');
    expect(resp.json).toBeNull();
    expect(resp.body).toBe('not json');
  });

  it('resolves non-2xx statuses without throwing', async () => {
    mockRoute(429, 'slow down');
    const resp = await httpGetJson('https://x.test/p', 'key', '0.2.1');
    expect(resp.status).toBe(429);
  });

  it('resolves with status 0 when statusCode is absent', async () => {
    vi.mocked(https.get).mockImplementation((_url: unknown, _opts: unknown, cb: (r: unknown) => void) => {
      cb({
        on: (event: string, fn: (chunk?: string) => void) => {
          if (event === 'data') fn('{}');
          if (event === 'end') fn();
        },
      });
      return { on: vi.fn(), destroy: vi.fn() } as unknown as ReturnType<typeof https.get>;
    });
    const resp = await httpGetJson('https://x.test/p', 'key', '0.2.1');
    expect(resp.status).toBe(0);
  });

  it('rejects on request error', async () => {
    let errorHandler: (() => void) | undefined;
    vi.mocked(https.get).mockImplementation(
      (_url: unknown, _opts: unknown, _cb: unknown) =>
        ({
          on: vi.fn((event: string, cb: () => void) => {
            if (event === 'error') errorHandler = cb;
          }),
          destroy: vi.fn(),
        }) as unknown as ReturnType<typeof https.get>,
    );
    const promise = httpGetJson('https://x.test/p', 'key', '0.2.1');
    errorHandler!();
    await expect(promise).rejects.toThrow();
  });

  it('rejects and destroys the request on timeout', async () => {
    let timeoutHandler: (() => void) | undefined;
    const destroy = vi.fn();
    vi.mocked(https.get).mockImplementation(
      (_url: unknown, _opts: unknown, _cb: unknown) =>
        ({
          on: vi.fn((event: string, cb: () => void) => {
            if (event === 'timeout') timeoutHandler = cb;
          }),
          destroy,
        }) as unknown as ReturnType<typeof https.get>,
    );
    const promise = httpGetJson('https://x.test/p', 'key', '0.2.1');
    timeoutHandler!();
    await expect(promise).rejects.toThrow('Request timeout');
    expect(destroy).toHaveBeenCalled();
  });
});
