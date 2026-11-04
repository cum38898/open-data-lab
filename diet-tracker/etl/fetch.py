"""データ取得の入口。

    python -m etl.fetch                 # テーマと法律をすべて更新
    python -m etl.fetch --topics rapidus,ainu
    python -m etl.fetch --skip-laws
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import kokkai, laws

CONFIG = Path(__file__).with_name("topics.json")
LAWS_SINCE = "2025-01-01"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", help="カンマ区切りのテーマID（省略時はすべて）")
    ap.add_argument("--skip-topics", action="store_true")
    ap.add_argument("--skip-laws", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not args.skip_topics:
        kokkai.run(cfg, only=args.topics.split(",") if args.topics else None)
    if not args.skip_laws:
        laws.run(LAWS_SINCE)


if __name__ == "__main__":
    main()
