"""规则引擎：从 YAML 加载关键词与正则规则，对输入做风险匹配。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


@dataclass
class RuleHit:
    rule_id: str
    risk_type: str
    weight: float


@dataclass
class RuleResult:
    is_risk: bool
    score: float
    hits: list[RuleHit] = field(default_factory=list)

    @property
    def hit_ids(self) -> list[str]:
        return [h.rule_id for h in self.hits]

    @property
    def risk_types(self) -> list[str]:
        return sorted({h.risk_type for h in self.hits})


class RuleEngine:
    """支持 keyword 与 regex 两类规则，命中即累加风险分。"""

    def __init__(self, rules_path: Path | None = None) -> None:
        self.path = rules_path or RULES_DIR / "input_rules.yaml"
        self.rules: list[dict[str, Any]] = self._load(self.path)
        self._compiled: dict[str, re.Pattern] = {}
        for rule in self.rules:
            if rule.get("type") == "regex":
                self._compiled[rule["id"]] = re.compile(rule["pattern"])

    @staticmethod
    def _load(path: Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("rules", [])

    def _match(self, text: str, rule: dict[str, Any]) -> bool:
        rule_type = rule.get("type", "keyword")
        if rule_type == "keyword":
            return any(kw in text for kw in rule.get("keywords", []))
        if rule_type == "regex":
            pattern = self._compiled.get(rule["id"])
            return bool(pattern and pattern.search(text))
        return False

    def check(self, text: str) -> RuleResult:
        if not text:
            return RuleResult(is_risk=False, score=0.0)

        hits: list[RuleHit] = []
        for rule in self.rules:
            if self._match(text, rule):
                hits.append(
                    RuleHit(
                        rule_id=rule["id"],
                        risk_type=rule.get("risk_type", "未分类"),
                        weight=float(rule.get("weight", 0.8)),
                    )
                )

        # 取最高权重作为规则侧得分，命中多条时给少量加成
        score = max((h.weight for h in hits), default=0.0)
        if len(hits) > 1:
            score = min(1.0, score + 0.05 * (len(hits) - 1))

        return RuleResult(is_risk=bool(hits), score=round(score, 3), hits=hits)
