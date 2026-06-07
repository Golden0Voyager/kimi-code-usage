export interface UsageItem {
  label: string;
  used: number;
  limit: number;
  remaining: number;
  percent_left: number;
  reset_hint: string | null;
  reset_seconds: number | null;
  reset_at: string | null;
}

export type PaceStateLabel = 'fast' | 'normal' | 'slow';

export interface PaceState {
  ratio: number;
  state: PaceStateLabel;
}

export interface PacePresentation {
  label: string;
  icon: string;
}

export interface ThresholdSettings {
  weekly: number;
  fiveHours: number;
}

export interface ThresholdConfig {
  fast: number;
  slow: number;
}

export interface ErrorPresentation {
  text: string;
  tooltip: string;
  isWarning: boolean;
}

export type LanguageChoice =
  | 'Auto'
  | 'English'
  | 'Chinese'
  | 'Japanese'
  | 'French'
  | 'German'
  | 'Spanish'
  | 'Korean'
  | 'Russian'
  | 'Portuguese'
  | 'Italian';

export type WindowType = 'weekly' | 'fiveHours' | 'monthly' | 'other';

export type PaceTheme =
  | 'Simple'
  | 'Animals'
  | 'Fish'
  | 'Birds'
  | 'Racing'
  | 'Running'
  | 'F1'
  | 'Rocket'
  | 'Star Wars'
  | 'Star Trek'
  | 'Back To The Future'
  | 'Pink Floyd'
  | 'Submarine'
  | 'Airliner'
  | 'Fighter'
  | 'Firearms';

export type PaceSensitivity = 'Relaxed' | 'Normal' | 'Strict' | 'Custom';

export type RedAlertCondition = 'Weekly' | '5 Hours' | 'Either';

export type StatusBarAlignmentChoice = 'Left' | 'Right';

export const WEEKLY_WINDOW_SECONDS = 7 * 24 * 3600;
export const FIVE_HOURS_WINDOW_SECONDS = 5 * 3600;
export const MONTHLY_WINDOW_SECONDS = 30 * 24 * 3600;
export const MIN_REFRESH_MINUTES = 1;
export const DEFAULT_LOW_THRESHOLD = 30;
export const ICON_NAME_PATTERN = /^[a-z][a-z0-9-]*$/;
export const PACE_RATIO_CAP = 5.0;
export const MIN_ELAPSED_SECONDS_FOR_PACE = 3600;
export const DEFAULT_HISTORY_RETENTION_DAYS = 30;
export const DEFAULT_API_CACHE_TTL_SECONDS = 300;

export interface SnapshotItem {
  label: string;
  windowType: WindowType;
  used: number;
  limit: number;
  percent_left: number;
  paceRatio: number | null;
}

export interface Snapshot {
  ts: number;
  items: SnapshotItem[];
}
