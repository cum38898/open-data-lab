"""新しく公布された法律（e-Gov 法令API）ごとに、国会でいつ・どこで審議されたかを集める。

- e-Gov 法令API v2: https://laws.e-gov.go.jp/api/2/ （法令は著作権の対象外。出典として e-Gov 法令検索を明記）
- 国会会議録検索システムの「会議単位簡易出力」（本文を含まない）で、法律の題名を含む会議を探す。
  法案は「〇〇に関する法律案」と呼ばれるので、題名の部分一致でほぼ拾える。
"""

from __future__ import annotations

from datetime import date, timedelta

from .common import DATA_DIR, Polite, http_get_json, log, now_jst_iso, read_json, today_jst, write_json
from .kokkai import API as KOKKAI_API, HOUSE, polite as kokkai_polite

EGOV = "https://laws.e-gov.go.jp/api/2/laws"
PATH = DATA_DIR / "laws.json"
egov_polite = Polite(1.0)

LOOKBACK_DAYS = 400  # 公布日からさかのぼって探す期間（提出から成立まで国会をまたぐことがある）
REFETCH_DAYS = 120   # 公布から日が浅い法律は、会議録の公開待ちがあるので取り直す


def fetch_new_laws(since: str) -> list[dict]:
    laws = []
    offset = 0
    while True:
        data = http_get_json(EGOV, {"law_type": "Act", "promulgation_date_from": since, "limit": 100,
                                    "offset": offset}, polite=egov_polite)
        for item in data.get("laws", []):
            info = item.get("law_info", {})
            rev = item.get("current_revision_info") or item.get("revision_info") or {}
            laws.append({
                "law_id": info.get("law_id"),
                "num": info.get("law_num"),
                "promulgated": info.get("promulgation_date"),
                "title": rev.get("law_title"),
                "abbrev": rev.get("abbrev"),
                "category": rev.get("category"),
            })
        nxt = data.get("next_offset")
        if not nxt or not data.get("laws"):
            break
        offset = int(nxt)
    return [law for law in laws if law["law_id"] and law["title"]]


def fetch_meetings(title: str, promulgated: str) -> list[list]:
    until = promulgated
    since = (date.fromisoformat(promulgated) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    meetings = []
    start = 1
    while True:
        data = http_get_json(f"{KOKKAI_API}/meeting_list", {
            "any": title, "from": since, "until": until, "maximumRecords": 100, "startRecord": start,
            "recordPacking": "json"}, polite=kokkai_polite)
        for m in data.get("meetingRecord") or []:
            speeches = [s for s in m.get("speechRecord") or [] if s.get("speechOrder") != 0]
            meetings.append([
                m["issueID"], m["date"], HOUSE.get(m.get("nameOfHouse") or "", m.get("nameOfHouse") or ""),
                m.get("nameOfMeeting") or "", m.get("issue") or "", len(speeches),
            ])
        nxt = data.get("nextRecordPosition")
        if not nxt or not data.get("meetingRecord"):
            break
        start = int(nxt)
    meetings.sort(key=lambda r: (r[1], r[0]))
    return meetings


def run(since: str) -> None:
    today = today_jst()
    cache = {law["law_id"]: law for law in read_json(PATH, {"laws": []})["laws"]}
    laws = fetch_new_laws(since)
    log(f"laws: {len(laws)} new acts promulgated since {since}")
    refetch_from = (today - timedelta(days=REFETCH_DAYS)).isoformat()
    out = []
    for law in sorted(laws, key=lambda x: x["promulgated"], reverse=True):
        cached = cache.get(law["law_id"])
        if cached and cached.get("meetings") is not None and law["promulgated"] < refetch_from:
            out.append({**law, "meetings": cached["meetings"], "fetched_at": cached.get("fetched_at")})
            continue
        try:
            meetings = fetch_meetings(law["title"], law["promulgated"])
            log(f"  {law['promulgated']} {law['title'][:30]}: {len(meetings)} meetings")
            out.append({**law, "meetings": meetings, "fetched_at": now_jst_iso()})
        except Exception as e:  # noqa: BLE001
            log(f"  failed {law['title'][:30]}: {e}")
            if cached:
                out.append(cached)
    write_json(PATH, {"since": since, "fetched_at": now_jst_iso(), "laws": out})
