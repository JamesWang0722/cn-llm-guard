"""规则结果与模型结果的融合策略。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rule_engine import RuleResult


@dataclass
class Decision:
    verdict: str          # block / pass
    score: float
    risk_type: str
    hit_rules: list[str]


def fuse(
    rule_result: RuleResult,
    model_score: float | None,
    threshold: float = 0.70,
    mode: str = "or",
) -> Decision:
    """or：任一判恶即拦截；and：两者都判恶才拦截。"""
    model_hit = model_score is not None and model_score >= threshold

    if mode == "and":
        is_risk = rule_result.is_risk and model_hit
    else:
        is_risk = rule_result.is_risk or model_hit

    scores = [rule_result.score]
    if model_score is not None:
        scores.append(model_score)

    risk_type = "；".join(rule_result.risk_types) if rule_result.is_risk else ""
    if model_hit and not risk_type:
        risk_type = "模型判定"

    return Decision(
        verdict="block" if is_risk else "pass",
        score=round(max(scores, default=0.0), 3),
        risk_type=risk_type,
        hit_rules=rule_result.hit_ids,
    )
