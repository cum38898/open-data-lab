// ビルド時に ETL の出力（../data/subsidies.json）を読み込む。サーバー側専用。
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { normalizeQuery } from "./status";

export interface SubsidyRecord {
  id: string;
  source: "jgrants" | "hokkaido_pref";
  title: string;
  summary: string;
  body_html: string;
  body_text: string;
  url: string;
  organization: string;
  program?: string | null;
  scope: "national" | "hokkaido" | "municipal";
  municipality: string | null;
  areas: string[];
  area_detail: string;
  purposes: string[];
  industries: string[];
  field?: string | null;
  employees: string | null;
  max_amount: number | null;
  rate: string | null;
  start: string | null;
  end: string | null;
  end_estimated: boolean;
  closed_hint: boolean;
  updated: string | null;
  attachments: string[];
  has_detail: boolean;
  license: "jgrants" | "cc-by-hokkaido" | "link-only";
  contact?: string | null;
  number: string | null;
}

export interface SourceInfo {
  name: string;
  url: string;
  credit: string;
  status: string | null;
}

export interface Dataset {
  generated_at: string;
  sources: Record<string, SourceInfo>;
  records: SubsidyRecord[];
}

let cache: Dataset | null = null;

export function loadDataset(): Dataset {
  if (cache) return cache;
  const path = resolve(process.cwd(), process.env.DATA_PATH ?? "../data/subsidies.json");
  cache = JSON.parse(readFileSync(path, "utf-8")) as Dataset;
  return cache;
}

/** URL に使う ID（jGrants の ID は大文字小文字を区別するのでそのまま使う） */
export function slugOf(r: SubsidyRecord): string {
  return r.id;
}

export const SCOPE_LABEL: Record<SubsidyRecord["scope"], string> = {
  national: "国・全国",
  hokkaido: "北海道",
  municipal: "道内市町村",
};

/** 一覧・詳細のタグに出す対象地域の短い表示 */
export function areaLabel(r: SubsidyRecord): string {
  if (r.municipality) return r.municipality;
  if (r.scope === "hokkaido" && r.areas.length > 1) return `北海道ほか${r.areas.length - 1}都府県`;
  return SCOPE_LABEL[r.scope];
}

/** ブラウザに送る検索用の軽量レコード */
export function toSearchRow(r: SubsidyRecord) {
  const haystack = normalizeQuery(
    [
      r.title,
      r.summary,
      r.organization,
      r.program ?? "",
      r.municipality ?? "",
      r.purposes.join(" "),
      r.industries.join(" "),
      r.area_detail,
      r.field ?? "",
      r.body_text.slice(0, 1500),
    ].join(" "),
  );
  return {
    id: r.id,
    t: r.title,
    s: r.summary,
    o: r.organization,
    src: r.source,
    sc: r.scope,
    m: r.municipality,
    p: r.purposes,
    i: r.industries,
    f: r.field ?? null,
    e: r.employees,
    x: r.max_amount,
    st: r.start,
    en: r.end,
    es: r.end_estimated,
    ch: r.closed_hint,
    u: r.updated,
    q: haystack,
  };
}

export type SearchRow = ReturnType<typeof toSearchRow>;

/** 件数の多い順に値を並べる（絞り込みの選択肢用） */
export function facetValues(records: SubsidyRecord[], pick: (r: SubsidyRecord) => string[]): string[] {
  const counts = new Map<string, number>();
  for (const r of records) for (const v of pick(r)) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([v]) => v);
}
