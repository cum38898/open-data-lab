"""各データ源を取得・正規化し、サイトが読む data/subsidies.json を作る。

    python -m etl.build            # 取得してから統合（GitHub Actions の定期実行）
    python -m etl.build --offline  # キャッシュだけで統合（サイト開発用）

どれかのデータ源の取得に失敗した場合は、そのデータ源だけ前回のキャッシュで代用する。
"""

from __future__ import annotations

import argparse
from datetime import datetime

from . import hokkaido_pref, jgrants
from .common import DATA_DIR, JST, log, read_json, write_json

SOURCES = {
    "jgrants": {
        "module": jgrants,
        "name": "Jグランツ（デジタル庁）",
        "url": "https://www.jgrants-portal.go.jp/",
        "credit": "出典：Jグランツ（デジタル庁）公開API",
    },
    "hokkaido_pref": {
        "module": hokkaido_pref,
        "name": "北海道庁ホームページ「助成制度」",
        "url": "https://www.pref.hokkaido.lg.jp/news/joseiseido/",
        "credit": "出典：北海道ホームページ（CC BY 4.0）。本サイトで本文を抜粋・整形し、受付期限を推定しています。",
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="ネットワークに出ずキャッシュから作る")
    args = ap.parse_args()

    records: list[dict] = []
    status = {}
    for key, src in SOURCES.items():
        mod = src["module"]
        try:
            rows = mod.load_cached() if args.offline else mod.run()
            status[key] = "ok" if not args.offline else "cached"
        except Exception as e:  # noqa: BLE001
            log(f"{key}: failed ({e}); falling back to cache")
            rows = mod.load_cached()
            status[key] = "stale"
        log(f"{key}: {len(rows)} records")
        records.extend(rows)

    # 同じ補助金が両方に載っている場合の重複除去は、タイトル完全一致のみ（Jグランツ側を残す）
    seen_titles = {r["title"] for r in records if r["source"] == "jgrants"}
    records = [r for r in records if r["source"] == "jgrants" or r["title"] not in seen_titles]
    records.sort(key=lambda r: (r.get("end") or "9999", r["title"]))

    # 「データ更新日時」は、各データ源のうち最も古い取得時刻にする（キャッシュから作った場合も正しく出る）
    fetched = []
    for src in SOURCES.values():
        g = read_json(src["module"].CACHE, {}).get("generated")
        if g:
            fetched.append(g if "T" in g else f"{g}T00:00+09:00")
    generated_at = min(fetched) if fetched else datetime.now(JST).isoformat(timespec="minutes")

    out = {
        "generated_at": generated_at,
        "sources": {
            k: {"name": v["name"], "url": v["url"], "credit": v["credit"], "status": status.get(k)}
            for k, v in SOURCES.items()
        },
        "records": records,
    }
    write_json(DATA_DIR / "subsidies.json", out)
    log(f"wrote {len(records)} records to data/subsidies.json")


if __name__ == "__main__":
    main()
