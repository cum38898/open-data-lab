// node --test tests/  （Node 22.18 以降は TypeScript の型注釈をそのまま実行できる）
import { test } from "node:test";
import assert from "node:assert/strict";
import { daysLeft, employeesEligible, formatYen, normalizeQuery, statusOf } from "../src/lib/status.ts";

const NOW = Date.parse("2026-11-04T12:00:00+09:00");

test("statusOf: 受付期間の前・中・後", () => {
  const r = { start: "2026-11-10T09:00+09:00", end: "2026-12-01T17:00+09:00" };
  assert.equal(statusOf(r, Date.parse("2026-11-01T00:00+09:00")), "upcoming");
  assert.equal(statusOf(r, NOW), "upcoming");
  assert.equal(statusOf(r, Date.parse("2026-11-20T00:00+09:00")), "open");
  assert.equal(statusOf(r, Date.parse("2026-12-01T17:01+09:00")), "closed");
});

test("statusOf: 終了の手がかりが最優先、締切なしは要確認", () => {
  assert.equal(statusOf({ end: "2027-01-01T00:00+09:00", closed_hint: true }, NOW), "closed");
  assert.equal(statusOf({}, NOW), "unknown");
});

test("daysLeft: JST の日付で数える", () => {
  assert.equal(daysLeft("2026-11-04T23:59+09:00", NOW), 0);
  assert.equal(daysLeft("2026-11-05T00:30+09:00", NOW), 1);
  assert.equal(daysLeft(null, NOW), null);
});

test("employeesEligible", () => {
  assert.equal(employeesEligible("従業員数の制約なし", 500), true);
  assert.equal(employeesEligible("20名以下", 20), true);
  assert.equal(employeesEligible("20名以下", 100), false);
  assert.equal(employeesEligible("901名以上", 1000), true);
  assert.equal(employeesEligible("901名以上", 300), false);
  assert.equal(employeesEligible(null, 5), true);
});

test("formatYen", () => {
  assert.equal(formatYen(50000), "5万円");
  assert.equal(formatYen(1431000000), "14億3,100万円");
  assert.equal(formatYen(4000000000), "40億円");
  assert.equal(formatYen(null), "—");
});

test("normalizeQuery: 全角→半角、カタカナ→ひらがな", () => {
  assert.equal(normalizeQuery("ＩＴ導入"), "it導入");
  assert.equal(normalizeQuery("エネルギー"), normalizeQuery("えねるぎー"));
});
