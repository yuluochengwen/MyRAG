#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent A/B 评估脚本（30题双模式）

默认执行：
- 数据集: test/agent_eval_dataset.jsonl
- 模式A: 简洁模式（show_steps=false, max_iterations=3）
- 模式B: 工具链模式（show_steps=true, max_iterations=5）
- 每题重复: 3 次

输出文件：
- data/logs/agent_eval_ab_metrics.jsonl
- data/logs/agent_eval_ab_summary.csv
- data/logs/agent_eval_ab_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests


@dataclass
class EvalMode:
    name: str
    payload_overrides: Dict


DEFAULT_BASE_URL = os.getenv("AGENT_TEST_BASE_URL", "http://127.0.0.1:8010")
ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT_DIR / "test" / "agent_eval_dataset.jsonl"
OUT_JSONL = ROOT_DIR / "data" / "logs" / "agent_eval_ab_metrics.jsonl"
OUT_CSV = ROOT_DIR / "data" / "logs" / "agent_eval_ab_summary.csv"
OUT_MD = ROOT_DIR / "data" / "logs" / "agent_eval_ab_report.md"

MODES = [
    EvalMode(name="A_plain", payload_overrides={"show_steps": False, "max_iterations": 3, "temperature": 0.1}),
    EvalMode(name="B_agent", payload_overrides={"show_steps": True, "max_iterations": 5, "temperature": 0.1}),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Agent A/B evaluation.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base url, e.g. http://127.0.0.1:8010")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Dataset JSONL file path")
    parser.add_argument("--repeats", type=int, default=3, help="Repetitions per query per mode")
    parser.add_argument("--max-samples", type=int, default=0, help="Limit number of dataset items for quick smoke test")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP request timeout in seconds")
    parser.add_argument("--llm-model", default="", help="Optional llm_model override")
    return parser.parse_args()


def resolve_dataset_path(dataset_arg: str) -> Path:
    path = Path(dataset_arg)
    if path.is_absolute():
        return path

    if path.exists():
        return path.resolve()

    candidate = ROOT_DIR / path
    return candidate.resolve()


def load_dataset(path: Path, max_samples: int = 0) -> List[Dict]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    items = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))

    if max_samples > 0:
        return items[:max_samples]
    return items


def request_agent(base_url: str, payload: Dict, timeout: int) -> Tuple[int, Dict, int, str]:
    start = time.time()
    try:
        resp = requests.post(f"{base_url}/api/agent/query", json=payload, timeout=timeout)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code != 200:
            return resp.status_code, {}, elapsed_ms, f"HTTP {resp.status_code}: {resp.text[:160]}"
        body = resp.json() if resp.content else {}
        return resp.status_code, body, elapsed_ms, ""
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        return 0, {}, elapsed_ms, str(exc)


def score_answer_quality(answer: str) -> int:
    """简单启发式评分(1-5)，用于毕设报告占位。"""
    text = (answer or "").strip()
    if not text:
        return 1
    length = len(text)
    if "抱歉" in text or "错误" in text:
        return 2
    if length < 30:
        return 3
    if length < 120:
        return 4
    return 5


def aggregate(records: List[Dict]) -> List[Dict]:
    grouped = defaultdict(list)
    for record in records:
        key = (record["mode"], record["category"])
        grouped[key].append(record)

    summary_rows: List[Dict] = []
    for (mode, category), items in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        success_values = [1 if item["success"] else 0 for item in items]
        elapsed_values = [item["elapsed_ms"] for item in items]
        iter_values = [item["iterations"] for item in items]
        step_values = [item["steps"] for item in items]
        quality_values = [item["quality_score"] for item in items]

        summary_rows.append({
            "mode": mode,
            "category": category,
            "samples": len(items),
            "success_rate": round(sum(success_values) / len(success_values), 4),
            "avg_elapsed_ms": round(statistics.mean(elapsed_values), 2),
            "p95_elapsed_ms": round(percentile(elapsed_values, 95), 2),
            "avg_iterations": round(statistics.mean(iter_values), 2),
            "avg_steps": round(statistics.mean(step_values), 2),
            "avg_quality_score": round(statistics.mean(quality_values), 2),
        })

    return summary_rows


def percentile(values: List[int], p: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100)
    floor_idx = int(k)
    ceil_idx = min(floor_idx + 1, len(sorted_vals) - 1)
    if floor_idx == ceil_idx:
        return float(sorted_vals[floor_idx])
    d0 = sorted_vals[floor_idx] * (ceil_idx - k)
    d1 = sorted_vals[ceil_idx] * (k - floor_idx)
    return float(d0 + d1)


def write_outputs(records: List[Dict], summary_rows: List[Dict], dataset_size: int, repeats: int, base_url: str) -> None:
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)

    with OUT_JSONL.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "mode",
                "category",
                "samples",
                "success_rate",
                "avg_elapsed_ms",
                "p95_elapsed_ms",
                "avg_iterations",
                "avg_steps",
                "avg_quality_score",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    overall = aggregate_overall(summary_rows)
    md_lines = [
        "# Agent A/B 实验报告（自动生成）",
        "",
        f"- 生成时间: {datetime.now().isoformat()}",
        f"- 后端地址: {base_url}",
        f"- 数据集规模: {dataset_size}",
        f"- 每题重复次数: {repeats}",
        f"- 原始结果: {OUT_JSONL}",
        f"- 汇总CSV: {OUT_CSV}",
        "",
        "## 分类汇总",
        "",
        "| 模式 | 类别 | 样本 | 成功率 | 平均耗时(ms) | P95耗时(ms) | 平均迭代 | 平均步骤 | 平均质量分 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for row in summary_rows:
        md_lines.append(
            f"| {row['mode']} | {row['category']} | {row['samples']} | {row['success_rate']:.2%} | {row['avg_elapsed_ms']:.2f} | {row['p95_elapsed_ms']:.2f} | {row['avg_iterations']:.2f} | {row['avg_steps']:.2f} | {row['avg_quality_score']:.2f} |"
        )

    md_lines.extend([
        "",
        "## 模式总体对比",
        "",
        "| 模式 | 成功率 | 平均耗时(ms) | P95耗时(ms) | 平均迭代 | 平均步骤 | 平均质量分 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])

    for row in overall:
        md_lines.append(
            f"| {row['mode']} | {row['success_rate']:.2%} | {row['avg_elapsed_ms']:.2f} | {row['p95_elapsed_ms']:.2f} | {row['avg_iterations']:.2f} | {row['avg_steps']:.2f} | {row['avg_quality_score']:.2f} |"
        )

    md_lines.extend([
        "",
        "## 建议结论模板",
        "",
        "1. 若 B_agent 成功率更高且耗时可接受，可在答辩强调 Agent 工具链在复杂任务上的稳定性优势。",
        "2. 若 A_plain 耗时明显更低，可说明在低复杂度问题下可采用轻量模式节省延迟。",
        "3. 在论文中同时报告成功率与 P95 耗时，避免只看平均值造成结论偏差。",
    ])

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")


def aggregate_overall(summary_rows: List[Dict]) -> List[Dict]:
    grouped = defaultdict(list)
    for row in summary_rows:
        grouped[row["mode"]].append(row)

    overall_rows = []
    for mode, rows in sorted(grouped.items()):
        total_samples = sum(r["samples"] for r in rows)
        if total_samples == 0:
            continue

        def weighted_avg(field: str) -> float:
            return sum(r[field] * r["samples"] for r in rows) / total_samples

        overall_rows.append({
            "mode": mode,
            "success_rate": weighted_avg("success_rate"),
            "avg_elapsed_ms": weighted_avg("avg_elapsed_ms"),
            "p95_elapsed_ms": weighted_avg("p95_elapsed_ms"),
            "avg_iterations": weighted_avg("avg_iterations"),
            "avg_steps": weighted_avg("avg_steps"),
            "avg_quality_score": weighted_avg("avg_quality_score"),
        })

    return overall_rows


def main() -> int:
    args = parse_args()

    dataset_path = resolve_dataset_path(args.dataset)
    dataset = load_dataset(dataset_path, max_samples=max(0, args.max_samples))
    repeats = max(1, args.repeats)

    records: List[Dict] = []

    print("=" * 72)
    print("Agent A/B Evaluation")
    print("=" * 72)
    print(f"base_url={args.base_url}")
    print(f"dataset={dataset_path}")
    print(f"samples={len(dataset)} repeats={repeats} total_calls={len(dataset) * repeats * len(MODES)}")

    for mode in MODES:
        for item in dataset:
            query = item.get("query", "")
            for run_idx in range(1, repeats + 1):
                payload = {
                    "query": query,
                    "session_id": f"eval_{mode.name}_{item.get('id')}_{run_idx}",
                    **mode.payload_overrides,
                }
                if args.llm_model:
                    payload["llm_model"] = args.llm_model

                status_code, body, elapsed_ms, error_msg = request_agent(args.base_url, payload, timeout=args.timeout)
                success = bool(body.get("success")) if status_code == 200 else False
                answer = body.get("answer", "") if status_code == 200 else ""
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "mode": mode.name,
                    "dataset_id": item.get("id"),
                    "category": item.get("category", "unknown"),
                    "query": query,
                    "run": run_idx,
                    "http_status": status_code,
                    "success": success,
                    "elapsed_ms": elapsed_ms,
                    "iterations": int(body.get("iterations", 0)) if isinstance(body, dict) else 0,
                    "steps": len(body.get("steps", [])) if isinstance(body, dict) and isinstance(body.get("steps"), list) else 0,
                    "quality_score": score_answer_quality(answer),
                    "answer": answer,
                    "error": error_msg,
                }
                records.append(record)

                print(
                    f"[{mode.name}] id={item.get('id'):>2} run={run_idx} "
                    f"ok={str(success):<5} status={status_code:<3} elapsed={elapsed_ms:>5}ms "
                    f"iter={record['iterations']} steps={record['steps']}"
                )

    summary_rows = aggregate(records)
    write_outputs(records, summary_rows, dataset_size=len(dataset), repeats=repeats, base_url=args.base_url)

    print("-" * 72)
    print(f"raw jsonl: {OUT_JSONL}")
    print(f"summary csv: {OUT_CSV}")
    print(f"report md : {OUT_MD}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
