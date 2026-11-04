"""Jグランツ公開API から、北海道の事業者が使える補助金（対象地域に「北海道」または「全国」を含むもの）を取得する。

API ドキュメント: https://developers.digital.go.jp/documents/jgrants/api/

- 一覧API はキーワード（2文字以上）が必須なので、汎用的な語を複数投げて ID で重複を除く。
- 詳細API は公募要領などの添付ファイルを base64 で含み、1件で数MB〜十数MBになることがある。
  そのため詳細を取るのは「受付中・受付予定・直近で終了」のものだけにし、取得結果は
  data/jgrants.json にキャッシュして、一覧側の内容が変わったものだけを再取得する。
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import timedelta

from .common import (
    DATA_DIR,
    html_to_text,
    http_get_json,
    iso_to_jst,
    iso_to_jst_date,
    log,
    now_jst_iso,
    one_line,
    read_json,
    sanitize_html,
    today_jst,
    write_json,
)
from .municipalities import detect_municipality

API = "https://api.jgrants-portal.go.jp/exp/v1/public/subsidies"
CACHE = DATA_DIR / "jgrants.json"

KEYWORDS = [
    "補助", "助成", "支援", "事業", "交付", "給付", "奨励", "促進", "対策", "制度",
    "募集", "年度", "導入", "整備", "推進", "開発", "経費", "補助金", "助成金", "支援金",
]

KEEP_CLOSED_DAYS = 180     # 終了後この日数までは「過去の公募」として残す
DETAIL_CLOSED_DAYS = 30    # 終了後この日数までは詳細も取得する
REFRESH_OPEN_DAYS = 7      # 受付中のものはこの日数ごとに詳細を取り直す
MAX_DETAILS_PER_RUN = 400  # 1回の実行で取りに行く詳細の上限（API への負荷対策）
SLEEP = 1.0


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split("/") if v.strip()]


def fetch_list() -> dict[str, dict]:
    items: dict[str, dict] = {}
    for kw in KEYWORDS:
        params = {"keyword": kw, "sort": "created_date", "order": "DESC", "acceptance": "0"}
        try:
            data = http_get_json(API, params)
        except Exception as e:  # noqa: BLE001  1キーワードの失敗で全体を止めない
            log(f"  list '{kw}' failed: {e}")
            continue
        for row in data.get("result", []):
            items[row["id"]] = row
        log(f"  list '{kw}': {len(data.get('result', []))} (unique so far {len(items)})")
        time.sleep(SLEEP)
    return items


def is_hokkaido_eligible(row: dict) -> bool:
    areas = split_list(row.get("target_area_search"))
    return "北海道" in areas or "全国" in areas


def signature(row: dict) -> str:
    """一覧の内容が変わったかを判定するためのハッシュ。"""
    keys = ["title", "acceptance_start_datetime", "acceptance_end_datetime", "subsidy_max_limit",
            "target_area_search", "target_number_of_employees", "institution_name"]
    blob = json.dumps({k: row.get(k) for k in keys}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def fetch_detail(sid: str) -> dict | None:
    data = http_get_json(f"{API}/id/{sid}", timeout=180)
    result = data.get("result") or []
    if not result:
        return None
    d = result[0]
    # 添付ファイルは中身（base64）を捨てて名前だけ残す
    attachments = []
    for key in ("application_guidelines", "outline_of_grant", "application_form"):
        for f in d.get(key) or []:
            if isinstance(f, dict) and f.get("name"):
                attachments.append(f["name"])
    keep = [
        "subsidy_catch_phrase", "detail", "use_purpose", "industry", "target_area_detail",
        "subsidy_rate", "project_end_deadline", "front_subsidy_detail_page_url",
        "request_reception_presence", "is_enable_multiple_request", "institution_name",
    ]
    out = {k: d.get(k) for k in keep}
    out["attachments"] = attachments
    return out


def normalize_record(row: dict, detail: dict | None) -> dict:
    sid = row["id"]
    areas = split_list(row.get("target_area_search"))
    national = "全国" in areas or len(areas) >= 47
    detail = detail or {}
    body_html = sanitize_html(detail.get("detail"), "https://www.jgrants-portal.go.jp/")
    body_text = html_to_text(body_html)
    area_detail = one_line(detail.get("target_area_detail") or "")

    municipality = None
    if not national:
        municipality = detect_municipality(
            " ".join([row.get("title") or "", row.get("institution_name") or "", area_detail])
        )

    if national:
        scope = "national"
    elif municipality:
        scope = "municipal"
    else:
        scope = "hokkaido"  # 北海道を含む複数道県・道全域

    return {
        "id": f"jg-{sid}",
        "source": "jgrants",
        "title": one_line(row.get("title") or ""),
        "summary": one_line(detail.get("subsidy_catch_phrase") or "", 200),
        "body_html": body_html,
        "body_text": body_text,
        "url": detail.get("front_subsidy_detail_page_url") or f"https://www.jgrants-portal.go.jp/subsidy/{sid}",
        # Jグランツには実施機関の項目がない。市町村の制度だけは市町村名を実施機関とみなす
        "organization": municipality or "",
        # institution_name は実施機関名ではなく予算事業・制度の名前（一覧APIでは空のことが多い）
        "program": one_line(detail.get("institution_name") or row.get("institution_name") or "") or None,
        "scope": scope,
        "municipality": municipality,
        "areas": areas if len(areas) < 47 else ["全国"],
        "area_detail": area_detail,
        "purposes": split_list(detail.get("use_purpose")),
        "industries": split_list(detail.get("industry")),
        "employees": row.get("target_number_of_employees"),
        "max_amount": row.get("subsidy_max_limit") or None,
        "rate": one_line(detail.get("subsidy_rate") or "", 300) or None,
        "start": iso_to_jst(row.get("acceptance_start_datetime")),
        "end": iso_to_jst(row.get("acceptance_end_datetime")),
        "end_estimated": False,
        "closed_hint": False,
        "updated": None,
        "attachments": detail.get("attachments") or [],
        "has_detail": bool(detail),
        "license": "jgrants",
        "number": row.get("name"),
    }


def run() -> list[dict]:
    today = today_jst()
    keep_from = (today - timedelta(days=KEEP_CLOSED_DAYS)).isoformat()
    detail_from = (today - timedelta(days=DETAIL_CLOSED_DAYS)).isoformat()

    cache = {c["id"]: c for c in read_json(CACHE, {"items": []})["items"]}

    log("jgrants: fetching list")
    rows = fetch_list()
    if not rows:
        raise RuntimeError("jgrants: list API returned nothing")

    targets = []
    for row in rows.values():
        if not is_hokkaido_eligible(row):
            continue
        end = iso_to_jst_date(row.get("acceptance_end_datetime"))
        if end and end < keep_from:
            continue
        targets.append(row)
    log(f"jgrants: {len(targets)} records eligible for Hokkaido within window")

    fetched = 0
    new_cache = {}
    for row in sorted(targets, key=lambda r: r.get("acceptance_end_datetime") or "9999", reverse=True):
        sid = row["id"]
        sig = signature(row)
        end = iso_to_jst_date(row.get("acceptance_end_datetime"))
        want_detail = end is None or end >= detail_from
        cached = cache.get(sid)
        detail = cached.get("detail") if cached else None
        detail_fetched = cached.get("detail_fetched") if cached else None

        still_open = end is None or end >= today.isoformat()
        refresh_due = (detail_fetched or "") < (today - timedelta(days=REFRESH_OPEN_DAYS)).isoformat()
        changed = cached is None or cached.get("sig") != sig
        stale = want_detail and (detail is None or changed or (still_open and refresh_due))
        if stale and fetched < MAX_DETAILS_PER_RUN:
            try:
                detail = fetch_detail(sid)
                detail_fetched = today.isoformat()
                fetched += 1
                if fetched % 20 == 0:
                    log(f"  details fetched: {fetched}")
            except Exception as e:  # noqa: BLE001
                log(f"  detail {sid} failed: {e}")
            time.sleep(SLEEP)
        new_cache[sid] = {"id": sid, "sig": sig, "row": row, "detail": detail, "detail_fetched": detail_fetched}

    log(f"jgrants: fetched {fetched} details")
    write_json(CACHE, {"generated": now_jst_iso(), "items": list(new_cache.values())})
    return [normalize_record(c["row"], c["detail"]) for c in new_cache.values()]


def load_cached() -> list[dict]:
    """ネットワークに出ずにキャッシュから正規化レコードを作る（サイト開発用）。"""
    cache = read_json(CACHE, {"items": []})["items"]
    return [normalize_record(c["row"], c["detail"]) for c in cache]
