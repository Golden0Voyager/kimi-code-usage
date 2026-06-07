import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { SnapshotStore, buildSnapshotPath } from './storage';
import type { Snapshot } from './types';

let dir = '';
let store: SnapshotStore;

beforeEach(async () => {
  dir = await fs.mkdtemp(path.join(os.tmpdir(), 'kimi-storage-'));
  store = new SnapshotStore(path.join(dir, 'history.jsonl'));
});

afterEach(async () => {
  await fs.rm(dir, { recursive: true, force: true });
});

function snap(ts: number, used = 0, limit = 100): Snapshot {
  return {
    ts,
    items: [
      {
        label: 'Weekly limit',
        windowType: 'weekly',
        used,
        limit,
        percent_left: ((limit - used) / limit) * 100,
        paceRatio: 1.0,
      },
    ],
  };
}

describe('SnapshotStore', () => {
  it('returns empty list when file is missing', async () => {
    const list = await store.list();
    expect(list).toEqual([]);
  });

  it('appends and reads snapshots in order', async () => {
    await store.append(snap(1000));
    await store.append(snap(2000));
    await store.append(snap(3000));
    const list = await store.list();
    expect(list.map((s) => s.ts)).toEqual([1000, 2000, 3000]);
  });

  it('filters by sinceMs', async () => {
    await store.append(snap(1000));
    await store.append(snap(2000));
    await store.append(snap(3000));
    const list = await store.list({ sinceMs: 2000 });
    expect(list.map((s) => s.ts)).toEqual([2000, 3000]);
  });

  it('respects limit (last N)', async () => {
    for (let i = 0; i < 5; i++) await store.append(snap((i + 1) * 1000));
    const list = await store.list({ limit: 2 });
    expect(list.map((s) => s.ts)).toEqual([4000, 5000]);
  });

  it('skips corrupted lines', async () => {
    await store.append(snap(1000));
    const fp = path.join(dir, 'history.jsonl');
    await fs.appendFile(fp, '{not valid json}\n', 'utf8');
    await store.append(snap(2000));
    const list = await store.list();
    expect(list.map((s) => s.ts)).toEqual([1000, 2000]);
  });

  it('skips structurally invalid snapshot lines', async () => {
    await store.append(snap(1000));
    const fp = path.join(dir, 'history.jsonl');
    await fs.appendFile(
      fp,
      `${JSON.stringify({
        ts: 1500,
        items: [{ label: 'Weekly limit', windowType: 'weekly', used: 10, limit: 100 }],
      })}\n`,
      'utf8',
    );
    await fs.appendFile(
      fp,
      `${JSON.stringify({
        ts: 1600,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'weekly',
            used: Number.NaN,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      })}\n`,
      'utf8',
    );
    await fs.appendFile(
      fp,
      `${JSON.stringify({
        ts: 1700,
        items: [
          {
            label: 'Weekly limit',
            windowType: 'invalid',
            used: 10,
            limit: 100,
            percent_left: 90,
            paceRatio: null,
          },
        ],
      })}\n`,
      'utf8',
    );
    await store.append(snap(2000));
    const list = await store.list();
    expect(list.map((s) => s.ts)).toEqual([1000, 2000]);
  });

  it('prunes snapshots older than cutoff', async () => {
    await store.append(snap(1000));
    await store.append(snap(5000));
    await store.append(snap(10000));
    const removed = await store.prune(5000);
    expect(removed).toBe(1);
    const list = await store.list();
    expect(list.map((s) => s.ts)).toEqual([5000, 10000]);
  });

  it('does not drop an append queued before prune completes', async () => {
    await store.append(snap(1000));
    const append = store.append(snap(5000));
    const removed = await store.prune(3000);
    await append;

    expect(removed).toBe(1);
    const list = await store.list();
    expect(list.map((s) => s.ts)).toEqual([5000]);
  });

  it('clear removes the file', async () => {
    await store.append(snap(1000));
    await store.clear();
    const list = await store.list();
    expect(list).toEqual([]);
  });

  it('writes to a path that does not yet exist', async () => {
    const nested = path.join(dir, 'nested', 'deeper', 'history.jsonl');
    const s = new SnapshotStore(nested);
    await s.append(snap(42));
    const list = await s.list();
    expect(list).toHaveLength(1);
  });
});

describe('buildSnapshotPath', () => {
  it('joins under global storage', () => {
    expect(buildSnapshotPath('/var/storage')).toBe(path.join('/var/storage', 'history.jsonl'));
  });
});
