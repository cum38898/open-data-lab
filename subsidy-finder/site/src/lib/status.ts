// 受付状態の判定と表示用の整形。サーバー（ビルド時）とブラウザの両方から使う。

export type Status = "open" | "upcoming" | "closed" | "unknown";

export interface StatusInput {
  start?: string | null;
  end?: string | null;
  end_estimated?: boolean;
  closed_hint?: boolean;
}

const DAY = 86_400_000;

/** JST の「今日」の 0 時（UTC ミリ秒） */
export function todayJst(now: number = Date.now()): number {
  const jst = now + 9 * 3600_000;
  return Math.floor(jst / DAY) * DAY - 9 * 3600_000;
}

export function statusOf(r: StatusInput, now: number = Date.now()): Status {
  if (r.closed_hint) return "closed";
  const start = r.start ? Date.parse(r.start) : null;
  const end = r.end ? Date.parse(r.end) : null;
  if (end !== null && now > end) return "closed";
  if (start !== null && now < start) return "upcoming";
  if (end !== null) return "open";
  return "unknown";
}

/** 締切までの日数（今日が締切なら 0）。締切がなければ null */
export function daysLeft(end: string | null | undefined, now: number = Date.now()): number | null {
  if (!end) return null;
  const endDay = todayJst(Date.parse(end));
  return Math.round((endDay - todayJst(now)) / DAY);
}

export const STATUS_LABEL: Record<Status, string> = {
  open: "受付中",
  upcoming: "受付予定",
  closed: "終了",
  unknown: "要確認",
};

export function formatYen(v: number | null | undefined): string {
  if (!v) return "—";
  const oku = Math.floor(v / 1e8);
  const man = Math.round((v % 1e8) / 1e4);
  if (oku && man) return `${oku}億${man.toLocaleString("ja-JP")}万円`;
  if (oku) return `${oku}億円`;
  if (man) return `${man.toLocaleString("ja-JP")}万円`;
  return `${v.toLocaleString("ja-JP")}円`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(Date.parse(iso) + 9 * 3600_000);
  const w = "日月火水木金土"[d.getUTCDay()];
  return `${d.getUTCFullYear()}年${d.getUTCMonth() + 1}月${d.getUTCDate()}日(${w})`;
}

/** 「従業員数」による絞り込み：自社の人数 n が対象に入るか */
export function employeesEligible(rule: string | null | undefined, n: number | null): boolean {
  if (n === null) return true;
  if (!rule || rule.includes("制約なし")) return true;
  const le = rule.match(/(\d+)\s*名以下/);
  if (le) return n <= Number(le[1]);
  const ge = rule.match(/(\d+)\s*名以上/);
  if (ge) return n >= Number(ge[1]);
  return true;
}

/** 検索用の正規化（全角英数→半角、小文字化、カタカナ→ひらがな） */
export function normalizeQuery(s: string): string {
  return s
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60));
}
