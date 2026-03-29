#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent 评估脚本（毕设实验用）

使用方式:
1. 启动后端服务
2. 运行: python test/eval_agent_workbench.py
3. 输出: data/logs/agent_eval_metrics.jsonl
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = os.getenv("AGENT_TEST_BASE_URL", "http://127.0.0.1:8010")
OUT_FILE = Path("data/logs/agent_eval_metrics.jsonl")

EVAL_QUERIES = [
    {"category": "fact", "query": "现在几点了？"},
    {"category": "math", "query": "计算 10+20*3"},
    {"category": "kb", "query": "搜索知识库中关于 RAG 的内容"},
]


def run_one(query: str, show_steps: bool = True):
    payload = {
        "query": query,
        "max_iterations": 5,
        "temperature": 0.1,
        "show_steps": show_steps,
    }
    start = time.time()
    response = requests.post(f"{BASE_URL}/api/agent/query", json=payload, timeout=120)
    elapsed_ms = int((time.time() - start) * 1000)

    if response.status_code != 200:
        return {
            "success": False,
            "http_status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "answer": "",
            "iterations": 0,
            "steps": 0,
        }

    body = response.json()
    return {
        "success": bool(body.get("success")),
        "http_status": response.status_code,
        "elapsed_ms": elapsed_ms,
        "answer": body.get("answer", ""),
        "iterations": int(body.get("iterations", 0)),
        "steps": len(body.get("steps", [])),
    }


def main():
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = []

    for item in EVAL_QUERIES:
        result = run_one(item["query"], show_steps=True)
        record = {
            "timestamp": datetime.now().isoformat(),
            "category": item["category"],
            "query": item["query"],
            **result,
        }
        records.append(record)
        print(f"[{item['category']}] success={record['success']} elapsed_ms={record['elapsed_ms']} iterations={record['iterations']} steps={record['steps']}")

    with OUT_FILE.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    passed = sum(1 for r in records if r["success"])
    print("-" * 60)
    print(f"完成: {passed}/{len(records)} 成功")
    print(f"输出文件: {OUT_FILE}")


if __name__ == "__main__":
    main()
