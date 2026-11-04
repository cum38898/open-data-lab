// 発言者を「会派」などの集計用の区分に振り分ける。ブラウザでもビルド時でも使える純粋関数のみ。

// 会派の正式名称（例：「自由民主党・無所属の会」「立憲民主党・無所属」）から短い名前へ。上から順に判定する
const PARTY_RULES: [RegExp, string][] = [
  [/自由民主党/, "自民"],
  [/立憲民主/, "立憲"],
  [/日本維新の会/, "維新"],
  [/公明党/, "公明"],
  [/国民民主党/, "国民"],
  [/日本共産党/, "共産"],
  [/れいわ新選組/, "れいわ"],
  [/参政党/, "参政"],
  [/社会民主党/, "社民"],
  [/日本保守党/, "保守"],
  [/有志の会/, "有志の会"],
  [/教育無償化を実現する会/, "教育無償化"],
];

export const CHAIR = "議長・委員長";
export const GOVERNMENT = "政府（大臣など）";
export const NON_MEMBER = "参考人・政府職員など";
export const OTHER = "その他・無所属";

/** 発言者の区分。議長・委員長の議事進行と、大臣などの答弁は会派と分けて数える */
export function speakerClass(group: string | null | undefined, position: string | null | undefined): string {
  const pos = position ?? "";
  if (/議長|委員長|会長/.test(pos)) return CHAIR;
  if (/大臣|政務官|長官/.test(pos)) return GOVERNMENT;
  if (!group) return NON_MEMBER;
  for (const [re, name] of PARTY_RULES) if (re.test(group)) return name;
  // 規則にない会派は、正式名称の最初の部分をそのまま使う（例：「〇〇・無所属の会」→「〇〇」）。
  // 会派の構成を推測して既存の政党に寄せることはしない
  const head = group.split("・")[0].trim();
  if (!head || /^無所属|各派に属しない/.test(head)) return OTHER;
  return head;
}

/** 会派の表示順（主要会派→その他→議員以外）。件数の多い順に並べたあと、これらの区分は末尾にまとめる */
export const TRAILING_CLASSES = [OTHER, GOVERNMENT, CHAIR, NON_MEMBER];
