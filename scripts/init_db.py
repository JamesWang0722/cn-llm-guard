"""初始化 SQLite 数据库。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from app.db import AuditDB


def main() -> None:
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    db_path = ROOT / config["storage"]["db_path"]
    db = AuditDB(db_path)
    print(f"数据库已初始化：{db_path}")
    print(f"当前记录数：{db.stats()['total']}")


if __name__ == "__main__":
    main()
