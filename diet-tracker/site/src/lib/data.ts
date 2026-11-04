// ETL の出力（../data）をビルド時に読み込んで集計する。サーバー側専用。
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { OTHER, speakerClass, TRAILING_CLASSES } from "./groups";

const DATA_DIR = resolve(process.cwd(), process.env.DATA_DIR ?? "../data");
const CONFIG_PATH = resolve(process.cwd(), process.env.TOPICS_CONFIG ?? "../etl/topics.json");

export interface Category {
  id: string;
  label: string;
}
export interface TopicConfig {
  id: string;
  label: string;
  category: string;
  queries: string[];
}
/** [発言ID, 日付, 院, 会議名, 発言者, 会派, 肩書き] */
export type Row = [string, string, string, string, string, string | null, string | null];

export interface Topic extends TopicConfig {
  rows: Row[];
  snippets: Record<string, string>;
  fetchedAt: string | null;
}

export interface LawMeeting {
  issueID: string;
  date: string;
  house: string;
  meeting: string;
  issue: string;
  speeches: number;
}
export interface Law {
  law_id: string;
  num: string;
  promulgated: string;
  title: string;
  abbrev: string | null;
  category: string | null;
  meetings: LawMeeting[];
}

function readJson<T>(path: string, fallback: T): T {
  if (!existsSync(path)) return fallback;
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

let cached: { since: string; categories: Category[]; topics: Topic[]; laws: Law[]; fetchedAt: string } | null = null;

export function loadAll() {
  if (cached) return cached;
  const cfg = readJson<{ since: string; categories: Category[]; topics: TopicConfig[] }>(CONFIG_PATH, {
    since: "2023-01-01",
    categories: [],
    topics: [],
  });
  const topics: Topic[] = cfg.topics.map((t) => {
    const d = readJson<{ rows: Row[]; snippets: Record<string, string>; fetched_at: string } | null>(
      resolve(DATA_DIR, "topics", `${t.id}.json`),
      null,
    );
    return { ...t, rows: d?.rows ?? [], snippets: d?.snippets ?? {}, fetchedAt: d?.fetched_at ?? null };
  });
  const lawsRaw = readJson<{ laws: any[]; fetched_at?: string }>(resolve(DATA_DIR, "laws.json"), { laws: [] });
  const laws: Law[] = lawsRaw.laws.map((l) => ({
    ...l,
    meetings: (l.meetings ?? []).map((m: any[]) => ({
      issueID: m[0],
      date: m[1],
      house: m[2],
      meeting: m[3],
      issue: m[4],
      speeches: m[5],
    })),
  }));
  const fetched = [...topics.map((t) => t.fetchedAt), lawsRaw.fetched_at ?? null].filter(Boolean) as string[];
  cached = {
    since: cfg.since,
    categories: cfg.categories,
    topics,
    laws,
    fetchedAt: fetched.length ? fetched.sort()[0] : "",
  };
  return cached;
}

export function speechUrl(id: string): string {
  const i = id.lastIndexOf("_");
  return `https://kokkai.ndl.go.jp/txt/${id.slice(0, i)}/${Number(id.slice(i + 1))}`;
}
export function meetingUrl(issueID: string): string {
  return `https://kokkai.ndl.go.jp/txt/${issueID}`;
}

/** "2023-01" 〜 当月までの月キー */
export function monthKeys(since: string, untilIso: string): string[] {
  const [sy, sm] = since.split("-").map(Number);
  const [uy, um] = untilIso.split("-").map(Number);
  const out: string[] = [];
  for (let y = sy, m = sm; y < uy || (y === uy && m <= um); m === 12 ? (y++, (m = 1)) : m++) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
  }
  return out;
}

export interface MonthBucket {
  month: string;
  shu: number;
  san: number;
  other: number;
  total: number;
}

export function monthly(rows: Row[], months: string[]): MonthBucket[] {
  const map = new Map(months.map((m) => [m, { month: m, shu: 0, san: 0, other: 0, total: 0 }]));
  for (const r of rows) {
    const b = map.get(r[1].slice(0, 7));
    if (!b) continue;
    if (r[2] === "衆") b.shu++;
    else if (r[2] === "参") b.san++;
    else b.other++;
    b.total++;
  }
  return months.map((m) => map.get(m)!);
}

export function countBy<T>(rows: T[], key: (r: T) => string): { label: string; value: number }[] {
  const m = new Map<string, number>();
  for (const r of rows) m.set(key(r), (m.get(key(r)) ?? 0) + 1);
  return [...m.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value);
}

const MAX_PARTIES = 10;

/** 会派・立場別の件数。会派は多い順に最大10、それ以外は「その他・無所属」にまとめ、議員以外の区分は末尾に置く */
export function byClass(rows: Row[]) {
  const counts = countBy(rows, (r) => speakerClass(r[5], r[6]));
  const parties = counts.filter((c) => !TRAILING_CLASSES.includes(c.label));
  const head = parties.slice(0, MAX_PARTIES);
  const folded = parties.slice(MAX_PARTIES).reduce((s, c) => s + c.value, 0);
  const other = (counts.find((c) => c.label === OTHER)?.value ?? 0) + folded;
  const tail = TRAILING_CLASSES.map((t) =>
    t === OTHER ? (other ? { label: OTHER, value: other } : null) : counts.find((c) => c.label === t),
  ).filter(Boolean) as typeof counts;
  return [...head, ...tail];
}

/** 日付文字列（YYYY-MM-DD）の差（日） */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86_400_000);
}

export function todayJstIso(now = Date.now()): string {
  return new Date(now + 9 * 3600_000).toISOString().slice(0, 10);
}

export function formatJpDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${y}年${m}月${d}日`;
}

export function queryLabel(queries: string[]): string {
  return queries.map((q) => `「${q}」`).join("または");
}
