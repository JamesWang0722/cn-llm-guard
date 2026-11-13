"""输出侧审查：敏感信息、违规内容、引用核查。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

# 个人信息识别，命中即脱敏
PII_PATTERNS = {
    "身份证号": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "银行卡号": re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "邮箱": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
}


@dataclass
class OutputResult:
    is_risk: bool
    risk_types: list[str] = field(default_factory=list)
    masked_text: str = ""
    hit_rules: list[str] = field(default_factory=list)


class OutputGuard:
    def __init__(self, rules_path: Path | None = None) -> None:
        self.rules: list[dict[str, Any]] = self._load(rules_path or RULES_DIR / "output_rules.yaml")

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("rules", [])

    def check(self, text: str) -> OutputResult:
        risk_types: list[str] = []
        hit_rules: list[str] = []
        masked = text

        for name, pattern in PII_PATTERNS.items():
            if pattern.search(masked):
                risk_types.append(name)
                masked = pattern.sub(f"[{name}已脱敏]", masked)

        for rule in self.rules:
            keywords = rule.get("keywords", [])
            if any(kw in text for kw in keywords):
                risk_types.append(rule.get("risk_type", "违规内容"))
                hit_rules.append(rule["id"])

        return OutputResult(
            is_risk=bool(risk_types),
            risk_types=sorted(set(risk_types)),
            masked_text=masked,
            hit_rules=hit_rules,
        )
