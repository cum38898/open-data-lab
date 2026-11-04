"""国会会議録検索システムの検索用APIから、テーマごとの発言を集める。

API 仕様: https://kokkai.ndl.go.jp/api.html
- 登録不要。多重リクエストは避け、取得し終えてから数秒あけて次のリクエストを送る。
- 発言の著作権は各発言者にある。このサイトは発言を「数える」（情報解析）ことと、
  検索結果として短い抜粋を出して会議録へリンクすることに限って使い、本文は保存・公開しない。
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

from .common import DATA_DIR, Polite, http_get_json, log, now_jst_iso, read_json, write_json

API = "https://kokkai.ndl.go.jp/api"
TOPIC_DIR = DATA_DIR / "topics"
COLUMNS = ["id", "date", "house", "meeting", "speaker", "group", "position"]
SNIPPETS_PER_TOPIC = 40
SNIPPET_BEFORE = 45
SNIPPET_AFTER = 75
REFETCH_DAYS = 60  # 会議録は開会から公開まで時間がかかるので、直近60日分は毎回取り直す

polite = Polite(3.0)

HOUSE = {"衆議院": "衆", "参議院": "参", "両院": "両", "両院協議会": "両"}


def speech_url(speech_id: str) -> str:
    issue, order = speech_id.rsplit("_", 1)
    return f"https://kokkai.ndl.go.jp/txt/{issue}/{int(order)}"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def make_snippet(text: str, terms: list[str]) -> str:
    """検索語の前後だけを短く切り出す（本文の転載にならない長さ）。"""
    body = text or ""
    # 冒頭の「○山田委員　」のような話者表示は抜粋に含めない
    body = re.sub(r"^○\S+?[　 ]", "", body)
    flat = re.sub(r"\s+", " ", body.replace("　", " ")).strip()
    norm = _norm(flat)
    pos = -1
    for t in terms:
        for word in _norm(t).split():
            i = norm.find(word)
            if i >= 0 and (pos < 0 or i < pos):
                pos = i
    if pos < 0:
        pos = 0
    start = max(0, pos - SNIPPET_BEFORE)
    end = min(len(flat), pos + SNIPPET_AFTER)
    out = flat[start:end].strip()
    return ("…" if start > 0 else "") + out + ("…" if end < len(flat) else "")


def to_row(rec: dict) -> list:
    return [
        rec["speechID"],
        rec["date"],
        HOUSE.get(rec.get("nameOfHouse") or "", rec.get("nameOfHouse") or ""),
        rec.get("nameOfMeeting") or "",
        (rec.get("speaker") or "").replace("　", " ").strip(),
        rec.get("speakerGroup"),
        rec.get("speakerPosition"),
    ]


def search_speeches(query: str, since: str, until: str | None = None):
    """1つの検索語（AND は半角スペース区切り）で発言を全件取る。"""
    start = 1
    while True:
        params = {"any": query, "from": since, "maximumRecords": 100, "startRecord": start,
                  "recordPacking": "json"}
        if until:
            params["until"] = until
        data = http_get_json(f"{API}/speech", params, polite=polite)
        records = data.get("speechRecord") or []
        yield data.get("numberOfRecords", 0), records
        nxt = data.get("nextRecordPosition")
        if not nxt or not records:
            break
        start = int(nxt)


def fetch_topic(topic: dict, since_all: str) -> dict:
    path = TOPIC_DIR / f"{topic['id']}.json"
    cache = read_json(path, None)
    full = cache is None or cache.get("queries") != topic["queries"] or cache.get("since") != since_all
    rows: dict[str, list] = {} if full else {r[0]: r for r in cache["rows"]}
    snippets: dict[str, str] = {} if full else dict(cache.get("snippets", {}))

    if full:
        since = since_all
    else:
        latest = max((r[1] for r in rows.values()), default=since_all)
        since = max(since_all, (date.fromisoformat(latest) - timedelta(days=REFETCH_DAYS)).isoformat())

    log(f"[{topic['id']}] {'full' if full else 'incremental'} from {since}")
    for q in topic["queries"]:
        got = 0
        for total, records in search_speeches(q, since):
            for rec in records:
                if rec.get("speechOrder") == 0:  # 「会議録情報」（出席者・議題の一覧）は発言ではない
                    continue
                rows[rec["speechID"]] = to_row(rec)
                snippets[rec["speechID"]] = make_snippet(rec.get("speech") or "", topic["queries"])
            got += len(records)
            log(f"  '{q}': {got}/{total}")

    ordered = sorted(rows.values(), key=lambda r: (r[1], r[0]), reverse=True)
    keep_ids = {r[0] for r in ordered[:SNIPPETS_PER_TOPIC]}
    out = {
        "id": topic["id"],
        "queries": topic["queries"],
        "since": since_all,
        "fetched_at": now_jst_iso(),
        "columns": COLUMNS,
        "rows": ordered,
        # 抜粋は新しい発言の分だけ残す
        "snippets": {k: v for k, v in snippets.items() if k in keep_ids},
    }
    write_json(path, out)
    return out


def run(topics_config: dict, only: list[str] | None = None) -> None:
    for topic in topics_config["topics"]:
        if only and topic["id"] not in only:
            continue
        try:
            fetch_topic(topic, topics_config["since"])
        except Exception as e:  # noqa: BLE001  1テーマの失敗で全体を止めない（前回分が残る）
            log(f"[{topic['id']}] failed: {e}")
