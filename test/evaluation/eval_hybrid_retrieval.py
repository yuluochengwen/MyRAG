#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""混合检索离线评测脚本（Recall@k / MRR / nDCG）。

数据集格式：JSONL，每行示例
{
  "kb_id": 1,
  "query": "如何开机",
  "relevant_chunk_ids": ["file_12_chunk_3"],
  "relevant_keywords": ["电源键", "开机"]
}
"""

import asyncio
import importlib
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

backend_path = Path(__file__).parent.parent / "Backend"
sys.path.insert(0, str(backend_path))

def load_dataset(dataset_path: Path) -> List[Dict]:
    items: List[Dict] = []
    with dataset_path.open("r", encoding="utf-8") as fp:
        for line_no, line in enumerate(fp, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except Exception as error:
                raise ValueError(f"第 {line_no} 行不是合法JSON: {error}") from error

            if "kb_id" not in row or "query" not in row:
                raise ValueError(f"第 {line_no} 行缺少字段 kb_id/query")

            row.setdefault("relevant_chunk_ids", [])
            row.setdefault("relevant_keywords", [])
            items.append(row)
    return items


def reciprocal_rank(ranked_hits: List[bool]) -> float:
    for index, hit in enumerate(ranked_hits, start=1):
        if hit:
            return 1.0 / index
    return 0.0


def dcg_at_k(ranked_hits: List[bool], k: int) -> float:
    score = 0.0
    for i, hit in enumerate(ranked_hits[:k], start=1):
        rel = 1.0 if hit else 0.0
        if rel > 0:
            score += rel / math.log2(i + 1)
    return score


def ndcg_at_k(ranked_hits: List[bool], k: int, total_relevant: int) -> float:
    if total_relevant <= 0:
        return 0.0
    dcg = dcg_at_k(ranked_hits, k)
    ideal_hits = [True] * min(total_relevant, k)
    idcg = dcg_at_k(ideal_hits, k)
    if idcg <= 0:
        return 0.0
    return dcg / idcg


def evaluate_single(result_items: List[Dict], relevant_chunk_ids: List[str], relevant_keywords: List[str], top_k: int) -> Tuple[float, float, float]:
    ranked_hits: List[bool] = []
    relevant_id_set = set(str(item) for item in relevant_chunk_ids)
    keyword_set = set(relevant_keywords)

    for item in result_items[:top_k]:
        chunk_id = str(item.get("chunk_id") or "")
        content = str(item.get("content") or "")
        hit = False
        if chunk_id and chunk_id in relevant_id_set:
            hit = True
        elif keyword_set and any(keyword in content for keyword in keyword_set):
            hit = True
        ranked_hits.append(hit)

    recall = 1.0 if any(ranked_hits) else 0.0
    mrr = reciprocal_rank(ranked_hits)
    ndcg = ndcg_at_k(ranked_hits, top_k, max(1, len(relevant_id_set) if relevant_id_set else len(keyword_set)))
    return recall, mrr, ndcg


async def run_eval(dataset: List[Dict], top_k: int) -> None:
    module = importlib.import_module("app.services.hybrid_retrieval_service")
    get_hybrid_retrieval_service = getattr(module, "get_hybrid_retrieval_service")
    service = get_hybrid_retrieval_service()

    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0

    for index, row in enumerate(dataset, start=1):
        kb_id = int(row["kb_id"])
        query = str(row["query"])
        payload = await service.hybrid_search(kb_id=kb_id, query=query, top_k=top_k, enable_graph=True)
        results = payload.get("results", [])

        recall, mrr, ndcg = evaluate_single(
            result_items=results,
            relevant_chunk_ids=row.get("relevant_chunk_ids", []),
            relevant_keywords=row.get("relevant_keywords", []),
            top_k=top_k
        )

        recall_sum += recall
        mrr_sum += mrr
        ndcg_sum += ndcg

        print(f"[{index}/{len(dataset)}] kb={kb_id}, query={query[:30]}..., Recall@{top_k}={recall:.3f}, MRR={mrr:.3f}, nDCG@{top_k}={ndcg:.3f}")

    total = max(1, len(dataset))
    print("\n===== 混合检索离线评测结果 =====")
    print(f"样本数: {len(dataset)}")
    print(f"Recall@{top_k}: {recall_sum / total:.4f}")
    print(f"MRR: {mrr_sum / total:.4f}")
    print(f"nDCG@{top_k}: {ndcg_sum / total:.4f}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python eval_hybrid_retrieval.py <dataset.jsonl> [top_k]")
        sys.exit(1)

    dataset_path = Path(sys.argv[1])
    if not dataset_path.exists():
        print(f"数据集不存在: {dataset_path}")
        sys.exit(1)

    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    dataset = load_dataset(dataset_path)
    asyncio.run(run_eval(dataset, top_k))


if __name__ == "__main__":
    main()
