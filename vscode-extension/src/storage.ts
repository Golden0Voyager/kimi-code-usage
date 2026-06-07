import * as fs from 'fs/promises';
import * as path from 'path';
import type { Snapshot, WindowType } from './types';

export interface ListOptions {
  sinceMs?: number;
  limit?: number;
}

export class SnapshotStore {
  private writeQueue: Promise<unknown> = Promise.resolve();

  constructor(private readonly filePath: string) {}

  async append(snapshot: Snapshot): Promise<void> {
    const line = JSON.stringify(snapshot) + '\n';
    await this.enqueue(async () => {
      try {
        await fs.mkdir(path.dirname(this.filePath), { recursive: true });
        await fs.appendFile(this.filePath, line, 'utf8');
      } catch (e) {
        console.error('[KimiCodeUsage] Failed to append snapshot', e);
      }
    });
  }

  async list(options: ListOptions = {}): Promise<Snapshot[]> {
    await this.writeQueue.catch(() => undefined);
    return this.readUnsafe(options);
  }

  async prune(olderThanMs: number): Promise<number> {
    return this.enqueue(async () => {
      const all = await this.readUnsafe();
      const keep = all.filter((s) => s.ts >= olderThanMs);
      const removed = all.length - keep.length;
      if (removed === 0) return 0;
      await this.rewriteUnsafe(keep);
      return removed;
    });
  }

  async clear(): Promise<void> {
    await this.enqueue(async () => {
      await this.clearUnsafe();
    });
  }

  private enqueue<T>(task: () => Promise<T>): Promise<T> {
    const run = this.writeQueue.then(task, task);
    this.writeQueue = run.catch(() => undefined);
    return run;
  }

  private async readUnsafe(options: ListOptions = {}): Promise<Snapshot[]> {
    let raw: string;
    try {
      raw = await fs.readFile(this.filePath, 'utf8');
    } catch (e) {
      if (isMissingFile(e)) return [];
      throw e;
    }
    const out: Snapshot[] = [];
    const lines = raw.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const parsed = JSON.parse(trimmed) as Snapshot;
        if (!isValidSnapshot(parsed)) continue;
        if (options.sinceMs != null && parsed.ts < options.sinceMs) continue;
        out.push(parsed);
      } catch {
        // Skip corrupted line; prune() will eventually clear it.
      }
    }
    if (options.limit && out.length > options.limit) {
      return out.slice(-options.limit);
    }
    return out;
  }

  private async rewriteUnsafe(snapshots: Snapshot[]): Promise<void> {
    if (snapshots.length === 0) {
      await this.clearUnsafe();
      return;
    }
    const body = snapshots.map((s) => JSON.stringify(s)).join('\n') + '\n';
    await fs.mkdir(path.dirname(this.filePath), { recursive: true });
    await fs.writeFile(this.filePath, body, 'utf8');
  }

  private async clearUnsafe(): Promise<void> {
    try {
      await fs.unlink(this.filePath);
    } catch (e) {
      if (!isMissingFile(e)) throw e;
    }
  }
}

function isMissingFile(e: unknown): boolean {
  return !!e && typeof e === 'object' && (e as { code?: string }).code === 'ENOENT';
}

function isValidSnapshot(s: unknown): s is Snapshot {
  if (!s || typeof s !== 'object') return false;
  const snap = s as Partial<Snapshot>;
  if (!isFiniteNumber(snap.ts)) return false;
  if (!Array.isArray(snap.items)) return false;
  return snap.items.every(isValidSnapshotItem);
}

function isValidSnapshotItem(it: unknown): boolean {
  if (!it || typeof it !== 'object') return false;
  const item = it as Record<string, unknown>;
  return (
    typeof item.label === 'string' &&
    isWindowType(item.windowType) &&
    isFiniteNumber(item.used) &&
    isFiniteNumber(item.limit) &&
    isFiniteNumber(item.percent_left) &&
    (item.paceRatio === null || isFiniteNumber(item.paceRatio))
  );
}

function isWindowType(value: unknown): value is WindowType {
  return value === 'weekly' || value === 'fiveHours' || value === 'monthly' || value === 'other';
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function buildSnapshotPath(globalStoragePath: string): string {
  return path.join(globalStoragePath, 'history.jsonl');
}
