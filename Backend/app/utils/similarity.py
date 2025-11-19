"""向量相似度计算工具"""
import math
from typing import List


def normalize_l2_distance_to_similarity(distance: float) -> float:
    """
    将L2距离转换为相似度分数（适用于归一化向量）
    
    对于归一化向量（L2范数=1），L2距离和余弦相似度的关系：
    cosine_similarity = 1 - (L2_distance² / 2)
    
    Args:
        distance: L2距离（欧氏距离）
        
    Returns:
        相似度分数，范围 [0, 1]
        - 1.0 表示完全相同
        - 0.0 表示完全不相关
    """
    similarity = 1 - (distance * distance / 2)
    
    # 截断到 [0, 1] 范围
    # 注意：余弦相似度理论范围是 [-1, 1]，但对于文本embedding通常是正值
    return max(0.0, min(1.0, similarity))


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    计算两个向量的余弦相似度
    
    注意: 当前未在生产代码中使用，为未来语义去重功能预留
    
    Args:
        vec_a: 向量A
        vec_b: 向量B
        
    Returns:
        余弦相似度，范围 [-1, 1]
    """
    import numpy as np
    
    a = np.array(vec_a)
    b = np.array(vec_b)
    
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def format_search_results(
    results: dict,
    file_info_map: dict,
    kb_id: int,
    score_threshold: float = 0.0
) -> List[dict]:
    """
    格式化ChromaDB检索结果
    
    Args:
        results: ChromaDB返回的原始结果
        file_info_map: 文件ID到文件名的映射
        kb_id: 知识库ID
        score_threshold: 相似度阈值
        
    Returns:
        格式化后的结果列表
    """
    formatted_results = []
    
    if not results.get('ids') or len(results['ids']) == 0:
        return formatted_results
    
    distances = results['distances'][0]
    
    for i, doc_id in enumerate(results['ids'][0]):
        distance = distances[i]
        
        # 将L2距离转换为相似度（假设向量已归一化）
        similarity = normalize_l2_distance_to_similarity(distance)
        
        # 应用阈值过滤
        if similarity < score_threshold:
            continue
        
        metadata = results['metadatas'][0][i] if results.get('metadatas') else {}
        file_id = int(metadata.get('file_id', 0))
        
        formatted_results.append({
            'chunk_id': doc_id,
            'content': results['documents'][0][i],
            'similarity': round(similarity, 4),
            'metadata': {
                'kb_id': int(metadata.get('kb_id', kb_id)),
                'file_id': file_id,
                'filename': file_info_map.get(file_id, '未知文件'),
                'chunk_index': int(metadata.get('chunk_index', 0))
            },
            '_distance': round(distance, 4)  # 调试用
        })
    
    return formatted_results
