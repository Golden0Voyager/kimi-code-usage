import * as https from 'https';
import { URL } from 'url';
import {
  WEEKLY_WINDOW_SECONDS,
  FIVE_HOURS_WINDOW_SECONDS,
  MONTHLY_WINDOW_SECONDS,
  type UsageItem,
  type WindowType,
} from './types';
import { t } from './i18n';

export function detectWindowType(label: string): WindowType {
  const lower = label.toLowerCase();
  if (lower.includes('weekly') || lower.includes('week') || lower.includes('\u5468')) return 'weekly';
  if (
    lower.includes('5h') ||
    lower.includes('5 hour') ||
    lower.includes('5-hour') ||
    lower.includes('5hr') ||
    lower.includes('5\u5C0F\u65F6') ||
    lower === '5h' ||
    lower === '5 hours' ||
    lower === '5-hour'
  ) {
    return 'fiveHours';
  }
  if (lower.includes('month') || lower.includes('monthly') || lower.includes('\u6708')) return 'monthly';
  return 'other';
}

export function getWindowSeconds(label: string): number {
  const windowType = detectWindowType(label);
  if (windowType === 'fiveHours') return FIVE_HOURS_WINDOW_SECONDS;
  if (windowType === 'monthly') return MONTHLY_WINDOW_SECONDS;
  return WEEKLY_WINDOW_SECONDS;
}

export function findWindowItem(items: UsageItem[], windowType: WindowType): UsageItem | undefined {
  return items.find((item) => detectWindowType(item.label) === windowType);
}

export function isLowRemaining(item: UsageItem | undefined, thresholdPercent: number): boolean {
  if (!item) return false;
  return item.percent_left < thresholdPercent;
}

export function localizedLimitName(label: string): string {
  const type = detectWindowType(label);
  if (type === 'weekly') return t('Weekly');
  if (type === 'fiveHours') return t('5 Hours');
  if (type === 'monthly') return t('Monthly');
  return label;
}

export function shortLabel(label: string): string {
  const type = detectWindowType(label);
  if (type === 'weekly') return t('W-Short');
  if (type === 'fiveHours') return t('5H-Short');
  if (type === 'monthly') return t('M-Short');
  return label.slice(0, 3);
}

export function parsePayload(payload: unknown): UsageItem[] {
  if (!payload || typeof payload !== 'object') return [];
  const data = payload as Record<string, unknown>;
  const items: UsageItem[] = [];

  const usage = data.usage;
  if (usage && typeof usage === 'object') {
    const row = toRow(usage as Record<string, unknown>, t('Weekly limit'));
    if (row) items.push(row);
  }

  const limits = data.limits;
  if (Array.isArray(limits)) {
    for (let i = 0; i < limits.length; i++) {
      const item = limits[i];
      if (!item || typeof item !== 'object') continue;

      const itemObj = item as Record<string, unknown>;
      const detail = (
        itemObj.detail && typeof itemObj.detail === 'object' ? itemObj.detail : itemObj
      ) as Record<string, unknown>;

      const label = limitLabel(
        itemObj,
        detail,
        (itemObj.window as Record<string, unknown> | undefined) || {},
        i,
      );
      const row = toRow(detail, label);
      if (row) items.push(row);
    }
  }

  return items;
}

function toRow(data: Record<string, unknown>, defaultLabel: string): UsageItem | null {
  const limit = toInt(data.limit);
  let used = toInt(data.used);

  if (used == null) {
    const remaining = toInt(data.remaining);
    if (remaining != null && limit != null) used = limit - remaining;
  }
  if (used == null && limit == null) return null;

  const u = Math.max(0, used ?? 0);
  const l = Math.max(0, limit ?? 0);

  let reset_seconds: number | null = null;
  for (const key of ['reset_in', 'resetIn', 'ttl']) {
    const s = toInt(data[key]);
    if (s != null) {
      reset_seconds = s;
      break;
    }
  }

  if (reset_seconds == null) {
    for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
      const v = data[key];
      if (!v) continue;
      const sec = secondsUntil(String(v));
      if (sec != null && sec > 0) {
        reset_seconds = sec;
        break;
      }
    }
  }

  let reset_at: string | null = null;
  for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
    const v = data[key];
    if (v) {
      reset_at = String(v);
      break;
    }
  }

  const remaining = l > 0 ? clamp(l - u, 0, l) : 0;

  return {
    label: String(data.name || data.title || defaultLabel),
    used: u,
    limit: l,
    remaining,
    percent_left: l > 0 ? (remaining / l) * 100 : 0,
    reset_hint: resetHint(data),
    reset_seconds,
    reset_at,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function limitLabel(
  item: Record<string, unknown>,
  detail: Record<string, unknown>,
  window: Record<string, unknown>,
  idx: number,
): string {
  for (const key of ['name', 'title', 'scope']) {
    const value = item[key] ?? detail[key];
    if (value) return String(value);
  }

  const duration = toInt(window.duration ?? item.duration ?? detail.duration);
  const timeUnit = String(window.timeUnit ?? item.timeUnit ?? detail.timeUnit ?? '');

  if (duration != null) {
    if (timeUnit.includes('MINUTE')) {
      return duration >= 60 && duration % 60 === 0
        ? `${Math.floor(duration / 60)}h limit`
        : `${duration}m limit`;
    }
    if (timeUnit.includes('HOUR')) return `${duration}h limit`;
    if (timeUnit.includes('DAY')) return `${duration}d limit`;
    return `${duration}s limit`;
  }

  return `Limit #${idx + 1}`;
}

function resetHint(data: Record<string, unknown>): string | null {
  for (const key of ['reset_at', 'resetAt', 'reset_time', 'resetTime']) {
    const v = data[key];
    if (v) return formatResetTime(String(v));
  }
  for (const key of ['reset_in', 'resetIn', 'ttl', 'window']) {
    const s = toInt(data[key]);
    if (s) return t('Resets in {0}', formatDuration(s));
  }
  return null;
}

export function normalizeIso(val: string): string {
  let iso = val;
  if (iso.includes('.') && iso.endsWith('Z')) {
    const [base, frac] = iso.slice(0, -1).split('.');
    iso = `${base!}.${frac!.slice(0, 6)}Z`;
  }
  return iso;
}

export function secondsUntil(val: string): number | null {
  try {
    const iso = normalizeIso(val);
    const dt = new Date(iso.replace('Z', '+00:00'));
    if (Number.isNaN(dt.getTime())) return null;
    return Math.floor((dt.getTime() - Date.now()) / 1000);
  } catch {
    return null;
  }
}

export function formatResetTime(val: string): string {
  const sec = secondsUntil(val);
  if (sec == null) return t('Resets at {0}', val);
  if (sec <= 0) return t('Reset');
  return t('Resets in {0}', formatDuration(sec));
}

export function formatDuration(seconds: number): string {
  const parts: string[] = [];

  const days = Math.floor(seconds / 86400);
  if (days) parts.push(`${days}${t('day-short')}`);

  const rem = seconds % 86400;
  const hours = Math.floor(rem / 3600);
  if (hours) parts.push(`${hours}${t('hour-short')}`);

  const mins = Math.floor((rem % 3600) / 60);
  if (mins) parts.push(`${mins}${t('minute-short')}`);

  const secs = rem % 60;
  if (secs && !parts.length) parts.push(`${secs}${t('second-short')}`);

  return parts.join(' ') || `0${t('second-short')}`;
}

export function formatResetTimeAbsolute(val: string): { absolute: string; relative: string } {
  try {
    const iso = normalizeIso(val);
    const dt = new Date(iso.replace('Z', '+00:00'));
    if (Number.isNaN(dt.getTime())) {
      return { absolute: val, relative: t('Unknown') };
    }

    const now = new Date();
    const sec = Math.floor((dt.getTime() - now.getTime()) / 1000);
    const relative = sec <= 0 ? t('Reset') : formatDuration(sec);

    const hours = dt.getHours().toString().padStart(2, '0');
    const mins = dt.getMinutes().toString().padStart(2, '0');

    const resetDay = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);

    if (resetDay.getTime() === today.getTime()) {
      return { absolute: t('Today {0}:{1}', hours, mins), relative };
    }
    if (resetDay.getTime() === tomorrow.getTime()) {
      return { absolute: t('Tomorrow {0}:{1}', hours, mins), relative };
    }

    const weekdays = [t('Sun'), t('Mon'), t('Tue'), t('Wed'), t('Thu'), t('Fri'), t('Sat')];
    return { absolute: `${weekdays[dt.getDay()]} ${hours}:${mins}`, relative };
  } catch {
    return { absolute: val, relative: t('Unknown') };
  }
}

export function toInt(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

let userAgentVersion = '0.1.9';

export function setUserAgentVersion(version: string): void {
  userAgentVersion = version;
}

export function isLinkIssue(err: unknown): boolean {
  const raw = String(err ?? '').toLowerCase();
  return (
    raw.includes('invalid url') ||
    raw.includes('timeout') ||
    raw.includes('enotfound') ||
    raw.includes('econnreset') ||
    raw.includes('network') ||
    raw.includes('socket')
  );
}

export function fetchUsage(baseUrl: string, apiKey: string): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const url = new URL(baseUrl + '/usages');
    const req = https.get(
      url,
      {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'User-Agent': `kimi-usage-vscode/${userAgentVersion}`,
        },
        timeout: 10000,
      },
      (res) => {
        let body = '';
        res.on('data', (chunk) => (body += chunk));
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            try {
              resolve(JSON.parse(body));
            } catch {
              reject(new Error(t('Invalid JSON response')));
            }
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
          }
        });
      },
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(t('Request timeout')));
    });
  });
}
