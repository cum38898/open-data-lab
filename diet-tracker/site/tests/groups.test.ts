// node --test "tests/*.test.ts"
import { test } from "node:test";
import assert from "node:assert/strict";
import { CHAIR, GOVERNMENT, NON_MEMBER, OTHER, isGovernmentPosition, speakerClass } from "../src/lib/groups.ts";

test("会派の正式名称を短い名前にまとめる", () => {
  assert.equal(speakerClass("自由民主党・無所属の会", null), "自民");
  assert.equal(speakerClass("立憲民主・社民・無所属", null), "立憲");
  assert.equal(speakerClass("日本維新の会・教育無償化を実現する会", null), "維新");
  assert.equal(speakerClass("国民民主党・無所属クラブ", null), "国民");
  assert.equal(speakerClass("日本共産党", null), "共産");
  assert.equal(speakerClass("無所属", null), OTHER);
  assert.equal(speakerClass("各派に属しない議員", null), OTHER);
});

test("規則にない会派は正式名称の最初の部分を使う", () => {
  assert.equal(speakerClass("中道改革連合・無所属", null), "中道改革連合");
  assert.equal(speakerClass("チームみらい", null), "チームみらい");
  assert.equal(speakerClass("沖縄の風", null), "沖縄の風");
});

test("大臣など政府側の答弁", () => {
  assert.equal(speakerClass("自由民主党・無所属の会", "国土交通大臣"), GOVERNMENT);
  assert.equal(speakerClass("自由民主党", "内閣府大臣政務官"), GOVERNMENT);
  assert.equal(speakerClass("自由民主党", "経済産業副大臣"), GOVERNMENT);
  assert.equal(speakerClass("自由民主党", "内閣官房長官"), GOVERNMENT);
  // 肩書きに「委員長」を含むが大臣（Codex の指摘）
  assert.equal(speakerClass("自由民主党", "国家公安委員会委員長・内閣府特命担当大臣（防災・海洋政策）"), GOVERNMENT);
  // 民間出身の大臣（会派なし）
  assert.equal(speakerClass(null, "デジタル大臣"), GOVERNMENT);
});

test("議長・委員長は取得時の判定（chair）だけで決める", () => {
  // 委員会の委員長は API の肩書きが空
  assert.equal(speakerClass("自由民主党・無所属の会", null, 1), CHAIR);
  assert.equal(speakerClass("自由民主党・無所属の会", null, 0), "自民");
  // 肩書きに「会長」「委員長」を含む参考人・政府職員は議長・委員長ではない
  assert.equal(speakerClass(null, "日本放送協会会長"), NON_MEMBER);
  assert.equal(speakerClass(null, "全国労働組合総連合議長"), NON_MEMBER);
  assert.equal(speakerClass(null, "公正取引委員会委員長"), NON_MEMBER);
});

test("政府職員の肩書き（大臣官房）は大臣扱いしない", () => {
  assert.equal(isGovernmentPosition("経済産業省大臣官房審議官"), false);
  assert.equal(speakerClass(null, "経済産業省大臣官房審議官"), NON_MEMBER);
  assert.equal(speakerClass(null, "政府参考人"), NON_MEMBER);
  assert.equal(speakerClass(null, null), NON_MEMBER);
});
