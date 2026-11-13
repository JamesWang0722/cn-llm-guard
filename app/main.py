"""FastAPI 入口：检测、生成、审计三类接口。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db import AuditDB
from app.fusion import fuse
from app.llm_client import OllamaClient
from app.model_judge import ModelJudge
from app.output_guard import OutputGuard
from app.rule_engine import RuleEngine

BASE = Path(__file__).resolve().parent.parent
CONFIG: dict[str, Any] = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))

engine = RuleEngine()
judge = ModelJudge(CONFIG)
guard = OutputGuard()
llm = OllamaClient(CONFIG)
db = AuditDB(BASE / CONFIG["storage"]["db_path"])

DETECTION = CONFIG["detection"]
THRESHOLD = float(DETECTION["block_threshold"])
FUSION_MODE = str(DETECTION["fusion_mode"])
MAX_CHARS = int(DETECTION["max_input_chars"])

app = FastAPI(title="中文场景大模型护栏", version="0.1.0")


class CheckRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    text: str
    system: str = ""


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE / "frontend" / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_judge": judge.enabled,
        "ollama": await llm.is_alive(),
    }


@app.post("/check")
async def check(req: CheckRequest) -> dict[str, Any]:
    started = time.perf_counter()

    if len(req.text) > MAX_CHARS:
        latency = _elapsed_ms(started)
        db.insert(req.text[:200], "block", "超长输入", 1.0, ["LIMIT"], latency)
        return {
            "verdict": "block",
            "risk_type": "超长输入",
            "score": 1.0,
            "hit_rules": ["LIMIT"],
            "latency_ms": latency,
        }

    rule_result = engine.check(req.text)
    model_score = await judge.score(req.text)
    decision = fuse(rule_result, model_score, THRESHOLD, FUSION_MODE)

    latency = _elapsed_ms(started)
    db.insert(
        req.text,
        decision.verdict,
        decision.risk_type,
        decision.score,
        decision.hit_rules,
        latency,
    )

    return {
        "verdict": decision.verdict,
        "risk_type": decision.risk_type,
        "score": decision.score,
        "hit_rules": decision.hit_rules,
        "latency_ms": latency,
    }


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    started = time.perf_counter()

    rule_result = engine.check(req.text)
    model_score = await judge.score(req.text)
    decision = fuse(rule_result, model_score, THRESHOLD, FUSION_MODE)

    if decision.verdict == "block":
        latency = _elapsed_ms(started)
        db.insert(
            req.text,
            "block",
            decision.risk_type,
            decision.score,
            decision.hit_rules,
            latency,
            stage="input",
        )
        return {
            "verdict": "block",
            "stage": "input",
            "risk_type": decision.risk_type,
            "hit_rules": decision.hit_rules,
            "latency_ms": latency,
        }

    try:
        reply = await llm.generate(req.text, req.system)
    except Exception as exc:  # 模型未就绪时给出明确提示，不吞异常
        return {"verdict": "error", "stage": "llm", "message": str(exc)}

    output = guard.check(reply)
    latency = _elapsed_ms(started)
    verdict = "masked" if output.is_risk else "pass"
    db.insert(
        req.text,
        verdict,
        "；".join(output.risk_types),
        1.0 if output.is_risk else 0.0,
        output.hit_rules,
        latency,
        stage="output",
    )

    return {
        "verdict": verdict,
        "stage": "output",
        "reply": output.masked_text,
        "output_risk": output.risk_types,
        "latency_ms": latency,
    }


@app.get("/logs")
async def logs(limit: int = 50, verdict: str | None = None) -> dict[str, Any]:
    return {"items": db.query(limit=limit, verdict=verdict), "stats": db.stats()}
