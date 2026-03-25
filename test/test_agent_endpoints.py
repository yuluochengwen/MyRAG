#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Agent API 端点集成测试脚本（需先启动后端）"""

import time
import os
import requests

BASE_URL = os.getenv("AGENT_TEST_BASE_URL", "http://localhost:8000")
TIMEOUT = 60


def _print_result(name: str, passed: bool, detail: str = ""):
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name} {detail}")


def test_health() -> bool:
    try:
        resp = requests.get(f"{BASE_URL}/api/agent/health", timeout=TIMEOUT)
        if resp.status_code != 200:
            _print_result("health", False, f"status={resp.status_code}")
            return False
        body = resp.json()
        ok = body.get("status") == "ok"
        _print_result("health", ok)
        return ok
    except Exception as exc:
        _print_result("health", False, f"error={exc}")
        return False


def test_tools() -> bool:
    try:
        resp = requests.get(f"{BASE_URL}/api/agent/tools", timeout=TIMEOUT)
        if resp.status_code != 200:
            _print_result("tools", False, f"status={resp.status_code}")
            return False
        body = resp.json()
        names = {tool.get("name") for tool in body}
        expected = {"calculator", "get_current_time"}
        ok = expected.issubset(names)
        _print_result("tools", ok, f"found={sorted(names)}")
        return ok
    except Exception as exc:
        _print_result("tools", False, f"error={exc}")
        return False


def test_query() -> bool:
    payload = {
        "query": "计算 10+20*3",
        "max_iterations": 5,
        "temperature": 0.1,
        "show_steps": True
    }
    try:
        start = time.time()
        resp = requests.post(f"{BASE_URL}/api/agent/query", json=payload, timeout=TIMEOUT)
        elapsed = time.time() - start
        if resp.status_code != 200:
            _print_result("query", False, f"status={resp.status_code}, elapsed={elapsed:.2f}s")
            return False

        body = resp.json()
        fields_ok = all(key in body for key in ["answer", "steps", "success", "iterations"])
        semantic_ok = isinstance(body.get("steps"), list) and isinstance(body.get("success"), bool)
        ok = fields_ok and semantic_ok
        _print_result("query", ok, f"elapsed={elapsed:.2f}s, success={body.get('success')}")
        return ok
    except Exception as exc:
        _print_result("query", False, f"error={exc}")
        return False


def test_query_without_steps() -> bool:
    payload = {
        "query": "现在几点了？",
        "max_iterations": 3,
        "show_steps": False
    }
    try:
        resp = requests.post(f"{BASE_URL}/api/agent/query", json=payload, timeout=TIMEOUT)
        if resp.status_code != 200:
            _print_result("query_without_steps", False, f"status={resp.status_code}")
            return False

        body = resp.json()
        ok = isinstance(body.get("steps"), list) and len(body.get("steps", [])) == 0
        _print_result("query_without_steps", ok)
        return ok
    except Exception as exc:
        _print_result("query_without_steps", False, f"error={exc}")
        return False


def main() -> int:
    print("=" * 60)
    print("Agent API 端点测试")
    print("=" * 60)
    print(f"BASE_URL: {BASE_URL}")

    checks = [
        test_health,
        test_tools,
        test_query,
        test_query_without_steps,
    ]

    results = [check() for check in checks]
    passed = sum(1 for item in results if item)
    total = len(results)

    print("-" * 60)
    print(f"结果: {passed}/{total} 通过")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
