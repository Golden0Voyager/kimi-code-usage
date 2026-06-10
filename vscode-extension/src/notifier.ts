import * as vscode from 'vscode';
import type { UsageItem } from './types';
import { findWindowItem } from './api';
import { t } from './i18n';

export type Severity = 'ok' | 'warning' | 'critical';

export interface AlertEvaluation {
  weekly: Severity;
  fiveHours: Severity;
}

export interface NotifierOptions {
  weeklyWarningPercent: number;
  weeklyCriticalPercent: number;
  fiveHoursWarningPercent: number;
  fiveHoursCriticalPercent: number;
}

export class Notifier {
  private last: AlertEvaluation | null = null;
  private lastPaceFast = false;
  private readonly show: (msg: string) => Thenable<string | undefined>;

  constructor(
    private readonly options: NotifierOptions,
    show?: (msg: string) => Thenable<string | undefined>,
  ) {
    this.show = show || ((msg) => vscode.window.showInformationMessage(msg));
  }

  evaluate(items: UsageItem[]): AlertEvaluation {
    const weeklyItem = findWindowItem(items, 'weekly');
    const fiveHoursItem = findWindowItem(items, 'fiveHours');

    return {
      weekly: severityFor(
        weeklyItem?.percent_left,
        this.options.weeklyWarningPercent,
        this.options.weeklyCriticalPercent,
      ),
      fiveHours: severityFor(
        fiveHoursItem?.percent_left,
        this.options.fiveHoursWarningPercent,
        this.options.fiveHoursCriticalPercent,
      ),
    };
  }

  async checkAndNotify(items: UsageItem[], paceFast: boolean): Promise<void> {
    const current = this.evaluate(items);
    if (this.last == null) {
      this.last = current;
      this.lastPaceFast = paceFast;
      return;
    }
    const messages = diff(this.last, current);
    if (paceFast && !this.lastPaceFast)
      messages.push(t('Consumption pace is running hot. Consider easing usage.'));
    if (!paceFast && this.lastPaceFast) messages.push(t('Pace back to normal. Cruising steadily.'));
    for (const msg of messages) {
      await this.show(msg);
    }
    this.last = current;
    this.lastPaceFast = paceFast;
  }

  reset(): void {
    this.last = null;
    this.lastPaceFast = false;
  }
}

function severityFor(percentLeft: number | undefined, warningAt: number, criticalAt: number): Severity {
  if (percentLeft == null) return 'ok';
  if (percentLeft <= criticalAt) return 'critical';
  if (percentLeft <= warningAt) return 'warning';
  return 'ok';
}

function diff(prev: AlertEvaluation, next: AlertEvaluation): string[] {
  const out: string[] = [];

  if (next.weekly === 'critical' && prev.weekly !== 'critical') {
    out.push(t('Weekly quota at critical level.'));
  } else if (next.weekly === 'warning' && prev.weekly === 'ok') {
    out.push(t('Weekly quota running low.'));
  } else if (prev.weekly !== 'ok' && next.weekly === 'ok') {
    out.push(t('Weekly quota recovered.'));
  }

  if (next.fiveHours === 'critical' && prev.fiveHours !== 'critical') {
    out.push(t('5-hour quota at critical level.'));
  } else if (next.fiveHours === 'warning' && prev.fiveHours === 'ok') {
    out.push(t('5-hour quota running low.'));
  } else if (prev.fiveHours !== 'ok' && next.fiveHours === 'ok') {
    out.push(t('5-hour quota recovered.'));
  }

  return out;
}
