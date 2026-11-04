// テーマごとの集計（ビルド時）。
import { byClass, countBy, daysBetween, loadAll, monthKeys, monthly, todayJstIso, type Topic } from "./data";

export const PENDING_DAYS = 30; // 直近この日数を含む月は「会議録の公開待ちで少なめ」と表示する
export const RECENT_DAYS = 90;

export function pendingFromMonth(now = Date.now()): string {
  return todayJstIso(now - PENDING_DAYS * 86_400_000).slice(0, 7);
}

export function topicStats(t: Topic, now = Date.now()) {
  const { since } = loadAll();
  const today = todayJstIso(now);
  const months = monthKeys(since.slice(0, 7), today.slice(0, 7));
  const buckets = monthly(t.rows, months);
  const pendingFrom = pendingFromMonth(now);
  const complete = buckets.filter((b) => b.month < pendingFrom);
  const peak = complete.reduce((a, b) => (b.total > a.total ? b : a), complete[0] ?? buckets[0]);
  const recent = t.rows.filter((r) => daysBetween(r[1], today) <= RECENT_DAYS).length;
  const latest = t.rows[0]?.[1] ?? null;
  return {
    total: t.rows.length,
    buckets,
    pendingFrom,
    pendingCount: buckets.filter((b) => b.month >= pendingFrom).length,
    peak,
    recent,
    latest,
    classes: byClass(t.rows),
    meetings: countBy(t.rows, (r) => `${r[2] === "衆" ? "衆議院" : r[2] === "参" ? "参議院" : "両院"} ${r[3]}`),
  };
}

export function monthLabel(m: string): string {
  const [y, mm] = m.split("-").map(Number);
  return `${y}年${mm}月`;
}
