"""跑全量评测，输出拦截率、误杀率、P95 延迟三项指标。

用法：
    python scripts/run_eval.py --input data/samples.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from app.fusion import fuse
from app.model_judge import ModelJudge
from app.rule_engine import RuleEngine


def load_samples(path: Path) -> list[dict]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


async def run(samples: list[dict], engine: RuleEngine, judge: ModelJudge,
              threshold: float, mode: str) -> dict:
    tp = fp = tn = fn = 0
    latencies: list[float] = []
    details: list[dict] = []

    for sample in samples:
        started = time.perf_counter()
        rule_result = engine.check(sample["text"])
        model_score = await judge.score(sample["text"])
        decision = fuse(rule_result, model_score, threshold, mode)
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)

        predicted = "block" if decision.verdict == "block" else "pass"
        expected = sample.get("expected", "pass")

        if expected == "block" and predicted == "block":
            tp += 1
        elif expected == "block" and predicted == "pass":
            fn += 1
        elif expected == "pass" and predicted == "block":
            fp += 1
        else:
            tn += 1

        if predicted != expected:
            details.append({
                "id": sample.get("id"),
                "expected": expected,
                "predicted": predicted,
                "risk_type": decision.risk_type,
                "hit_rules": decision.hit_rules,
                "text": sample["text"],
            })

    latencies.sort()
    p95 = latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else 0.0

    return {
        "total": len(samples),
        "block_rate": round(tp / (tp + fn), 4) if (tp + fn) else 0.0,
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        "p95_latency_ms": round(p95, 2),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "errors": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/samples.jsonl")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    detection = config["detection"]

    engine = RuleEngine()
    judge = ModelJudge(config)
    samples = load_samples(ROOT / args.input)

    result = asyncio.run(
        run(samples, engine, judge,
            float(detection["block_threshold"]), str(detection["fusion_mode"]))
    )
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")
    result["model_judge_enabled"] = judge.enabled

    report_dir = ROOT / config["eval"]["report_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"样本数：{result['total']}")
    print(f"拦截率：{result['block_rate']:.2%}")
    print(f"误杀率：{result['false_positive_rate']:.2%}")
    print(f"P95 延迟：{result['p95_latency_ms']} ms")
    print(f"报告已保存：{out}")


if __name__ == "__main__":
    main()
