import { describe, it, expect, vi } from 'vitest';

vi.mock('fs/promises', async (importOriginal) => {
  const actual: any = await importOriginal();
  return {
    ...actual,
    unlink: vi.fn().mockRejectedValue(Object.assign(new Error('EACCES'), { code: 'EACCES' })),
  };
});

import { SnapshotStore } from './storage';
import type { Snapshot } from './types';

function snap(ts: number): Snapshot {
  return {
    ts,
    items: [
      {
        label: 'Weekly limit',
        windowType: 'weekly',
        used: 10,
        limit: 100,
        percent_left: 90,
        paceRatio: 1.0,
      },
    ],
  };
}

describe('SnapshotStore unlink error', () => {
  it('throws when unlink fails with non-ENOENT error', async () => {
    const s = new SnapshotStore('/tmp/unlink-e2e-test.jsonl');
    await s.append(snap(1000));
    await expect(s.prune(Infinity)).rejects.toThrow();
  });
});
