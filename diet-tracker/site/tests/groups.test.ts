// node --test "tests/*.test.ts"
import { test } from "node:test";
import assert from "node:assert/strict";
import { CHAIR, GOVERNMENT, NON_MEMBER, OTHER, speakerClass } from "../src/lib/groups.ts";

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

test("議長・委員長、大臣など、議員以外を分ける", () => {
  assert.equal(speakerClass("自由民主党・無所属の会", "国土交通大臣"), GOVERNMENT);
  assert.equal(speakerClass("自由民主党", "内閣府大臣政務官"), GOVERNMENT);
  assert.equal(speakerClass("立憲民主党・無所属", "委員長"), CHAIR);
  assert.equal(speakerClass(null, "政府参考人"), NON_MEMBER);
  assert.equal(speakerClass(null, null), NON_MEMBER);
});
