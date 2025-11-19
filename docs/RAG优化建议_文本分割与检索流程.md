# RAG优化建议：文本分割与检索流程优化

> 生成日期：2025年11月19日

## 1. 文本分割优化建议

### 当前系统的问题
项目使用的是 `RecursiveCharacterTextSplitter`，这是一个基于规则的分割器：
- **优点**：快速、可预测、无需额外计算成本
- **缺点**：可能在句子中间分割、破坏语义完整性、固定chunk大小不够灵活

### 优化方案

#### 方案一：LLM语义边界检测（高级）
使用本地LLM识别自然段落和主题边界：

```python
# Backend/app/services/semantic_splitter.py (新文件建议)
from typing import List, Dict
import requests

class LLMSemanticSplitter:
    """使用LLM进行智能语义分割"""
    
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_base_url
    
    async def split_by_semantic_boundary(
        self, 
        text: str, 
        model: str = "qwen2.5:3b",  # 使用轻量级模型
        max_chunk_size: int = 800
    ) -> List[Dict[str, str]]:
        """
        使用LLM识别语义边界进行分割
        
        工作流程:
        1. 将长文本送入LLM
        2. 要求LLM识别主题变化点/段落边界
        3. 根据LLM建议进行分割
        """
        
        prompt = f"""请分析以下文本,识别自然的语义段落边界。
在每个段落结束后标记[SPLIT]。

要求:
- 每个段落应该是一个完整的语义单元
- 段落长度尽量在{max_chunk_size}字符左右
- 不要在句子中间分割
- 保持主题连贯性

文本:
{text[:4000]}  # 限制输入长度避免token超限

请在段落边界处插入[SPLIT]标记:"""

        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # 低温度保证稳定性
                    "num_predict": 2000
                }
            }
        )
        
        result_text = response.json()["response"]
        chunks = result_text.split("[SPLIT]")
        
        return [
            {
                "text": chunk.strip(),
                "metadata": {"split_method": "llm_semantic"}
            }
            for chunk in chunks if chunk.strip()
        ]
```

#### 方案二：混合分割策略（推荐）
结合多种方法的优势：

```python
# Backend/app/services/hybrid_splitter.py
from langchain.text_splitter import RecursiveCharacterTextSplitter
import re
from typing import List

class HybridTextSplitter:
    """混合文本分割策略"""
    
    def __init__(self):
        # 基础分割器
        self.base_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            separators=["\n\n\n", "\n\n", "\n", "。", "!", "?", ";", ",", " ", ""]
        )
    
    def split_with_structure(self, text: str) -> List[Dict]:
        """
        结构化分割:
        1. 识别文档结构(标题、列表、代码块)
        2. 保持结构完整性
        3. 在结构边界优先分割
        """
        chunks = []
        
        # 1. 识别Markdown标题
        header_pattern = r'^#{1,6}\s.+$'
        sections = re.split(f'({header_pattern})', text, flags=re.MULTILINE)
        
        current_section = ""
        current_header = ""
        
        for section in sections:
            if re.match(header_pattern, section):
                # 遇到新标题,保存上一节
                if current_section:
                    chunks.extend(self._split_section(
                        current_section, 
                        header=current_header
                    ))
                current_header = section
                current_section = section + "\n"
            else:
                current_section += section
        
        # 保存最后一节
        if current_section:
            chunks.extend(self._split_section(
                current_section, 
                header=current_header
            ))
        
        return chunks
    
    def _split_section(self, text: str, header: str = "") -> List[Dict]:
        """分割单个章节"""
        # 2. 识别特殊块(代码、表格)
        code_blocks = re.findall(r'```[\s\S]*?```', text)
        
        # 如果包含代码块,保持代码完整性
        if code_blocks and len(text) < 1500:
            return [{
                "text": text,
                "metadata": {
                    "header": header,
                    "has_code": True,
                    "split_method": "preserve_structure"
                }
            }]
        
        # 3. 否则使用递归分割
        base_chunks = self.base_splitter.split_text(text)
        return [
            {
                "text": chunk,
                "metadata": {
                    "header": header,
                    "split_method": "recursive"
                }
            }
            for chunk in base_chunks
        ]
```

#### 方案三：语义嵌入分割（最先进）
使用embedding相似度识别主题变化：

```python
# Backend/app/services/embedding_based_splitter.py
import numpy as np
from typing import List
from app.services.embedding_service import UnifiedEmbeddingService

class EmbeddingBasedSplitter:
    """基于语义相似度的智能分割"""
    
    def __init__(self, embedding_service: UnifiedEmbeddingService):
        self.embedding_service = embedding_service
    
    async def split_by_semantic_similarity(
        self, 
        text: str,
        similarity_threshold: float = 0.75  # 相似度阈值
    ) -> List[str]:
        """
        工作原理:
        1. 将文本按句子分割
        2. 计算相邻句子的embedding相似度
        3. 在相似度突降处分割(主题变化点)
        """
        
        # 1. 分割成句子
        sentences = self._split_into_sentences(text)
        
        # 2. 获取每个句子的embedding
        embeddings = []
        for sentence in sentences:
            emb = await self.embedding_service.get_embedding(sentence)
            embeddings.append(np.array(emb))
        
        # 3. 计算相邻句子相似度
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = np.dot(embeddings[i], embeddings[i+1])
            similarities.append(sim)
        
        # 4. 识别相似度突降点(主题变化)
        split_points = [0]
        for i, sim in enumerate(similarities):
            if sim < similarity_threshold:
                split_points.append(i + 1)
        split_points.append(len(sentences))
        
        # 5. 根据分割点组合chunk
        chunks = []
        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i + 1]
            chunk = " ".join(sentences[start:end])
            chunks.append(chunk)
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """分割成句子"""
        import re
        # 中英文句子分割
        sentences = re.split(r'[。!?;！？；]\s*', text)
        return [s.strip() for s in sentences if s.strip()]
```

---

## 2. RAG检索流程优化建议

### 当前系统问题
知识库检索流程相对简单：
1. 用户查询 → embedding → ChromaDB检索 → 返回topK
2. 缺少查询优化、重排序、上下文扩展等高级功能

### 优化方案

#### 优化1：查询改写（Query Rewriting）
```python
# Backend/app/services/query_optimizer.py
class QueryOptimizer:
    """查询优化器"""
    
    async def expand_query(self, query: str, model: str = "qwen2.5:3b") -> List[str]:
        """
        查询扩展:生成多个相关查询
        
        示例:
        输入: "Python异常处理"
        输出: [
            "Python异常处理",
            "Python try except使用方法",
            "Python错误捕获机制",
            "如何处理Python运行时错误"
        ]
        """
        prompt = f"""请为以下查询生成3个语义相关的变体问题。
每个变体应该从不同角度表达相同的信息需求。

原始查询: {query}

变体问题(每行一个):
1."""

        response = await self._call_ollama(model, prompt)
        queries = [query] + self._parse_numbered_list(response)
        return queries[:4]  # 最多4个变体
    
    async def decompose_query(self, query: str) -> List[str]:
        """
        复杂查询分解
        
        示例:
        输入: "Python FastAPI如何集成JWT认证和CORS配置"
        输出: [
            "Python FastAPI JWT认证实现",
            "FastAPI CORS配置方法"
        ]
        """
        # 识别是否是复合查询
        if " 和 " in query or "以及" in query or len(query) > 40:
            prompt = f"""将以下复杂查询分解为2-3个简单的子查询。

复杂查询: {query}

子查询(每行一个):
1."""
            response = await self._call_ollama("qwen2.5:3b", prompt)
            return self._parse_numbered_list(response)
        
        return [query]
```

#### 优化2：混合检索（Hybrid Search）
```python
# Backend/app/services/hybrid_retriever.py
class HybridRetriever:
    """混合检索:向量检索 + 关键词检索"""
    
    async def hybrid_search(
        self,
        query: str,
        kb_id: int,
        top_k: int = 10,
        alpha: float = 0.7  # 向量检索权重
    ) -> List[Dict]:
        """
        混合检索策略:
        score = alpha * vector_score + (1-alpha) * bm25_score
        """
        
        # 1. 向量检索
        vector_results = await self.vector_search(query, kb_id, top_k * 2)
        
        # 2. BM25关键词检索
        bm25_results = await self.bm25_search(query, kb_id, top_k * 2)
        
        # 3. 融合排序(Reciprocal Rank Fusion)
        merged = self._reciprocal_rank_fusion(
            vector_results, 
            bm25_results,
            alpha
        )
        
        return merged[:top_k]
    
    def _reciprocal_rank_fusion(
        self, 
        vector_results: List,
        bm25_results: List,
        alpha: float
    ) -> List[Dict]:
        """RRF算法融合两种检索结果"""
        scores = {}
        k = 60  # RRF常数
        
        # 向量检索得分
        for rank, result in enumerate(vector_results):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + alpha / (k + rank + 1)
        
        # BM25得分
        for rank, result in enumerate(bm25_results):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0) + (1-alpha) / (k + rank + 1)
        
        # 按得分排序
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [self._get_doc_by_id(doc_id) for doc_id, _ in ranked]
```

#### 优化3：重排序（Reranking）
```python
# Backend/app/services/reranker.py
class CrossEncoderReranker:
    """使用交叉编码器重排序"""
    
    def __init__(self):
        from sentence_transformers import CrossEncoder
        # 加载重排序模型
        self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    
    def rerank(
        self, 
        query: str, 
        candidates: List[Dict],
        top_k: int = 5
    ) -> List[Dict]:
        """
        重排序:
        1. 初检:向量检索召回topK*2候选
        2. 精排:CrossEncoder计算query-doc精确相关性
        3. 返回top_k最相关结果
        """
        
        # 构造query-doc对
        pairs = [(query, doc["text"]) for doc in candidates]
        
        # 计算相关性得分
        scores = self.model.predict(pairs)
        
        # 添加得分并排序
        for doc, score in zip(candidates, scores):
            doc["rerank_score"] = float(score)
        
        reranked = sorted(
            candidates, 
            key=lambda x: x["rerank_score"], 
            reverse=True
        )
        
        return reranked[:top_k]
```

#### 优化4：上下文窗口扩展
```python
# 在 knowledge_base_service.py 中添加
async def search_with_context_expansion(
    self,
    query: str,
    kb_id: int,
    top_k: int = 3
) -> List[Dict]:
    """
    检索结果上下文扩展
    
    问题: 单个chunk可能缺少上下文信息
    解决: 返回chunk的前后相邻chunk
    """
    
    # 1. 基础检索
    results = await self.search_knowledge_base(query, kb_id, top_k)
    
    # 2. 为每个结果扩展上下文
    expanded_results = []
    for result in results:
        chunk_id = result["chunk_id"]
        
        # 获取相邻chunk
        prev_chunk = await self._get_adjacent_chunk(chunk_id, offset=-1)
        next_chunk = await self._get_adjacent_chunk(chunk_id, offset=1)
        
        # 拼接上下文
        full_context = ""
        if prev_chunk:
            full_context += f"[上文] {prev_chunk['text']}\n\n"
        full_context += f"[核心] {result['text']}\n\n"
        if next_chunk:
            full_context += f"[下文] {next_chunk['text']}"
        
        expanded_results.append({
            **result,
            "expanded_text": full_context
        })
    
    return expanded_results
```

---

## 3. 实施优先级建议

### 立即可做（低成本高收益）
1. ✅ 优化RecursiveCharacterTextSplitter的separators参数（已完成）
2. 🔥 **实现混合检索**（向量+BM25）
3. 🔥 **添加查询扩展功能**
4. **实现上下文窗口扩展**

### 中期优化（需要额外模型）
5. 集成CrossEncoder重排序模型
6. 实现基于embedding相似度的语义分割

### 高级功能（需要更多计算资源）
7. LLM语义边界检测
8. 多查询融合检索

---

## 4. 具体实施推荐顺序

### 优先级1：混合检索
- **原因**：对检索质量提升最明显
- **实现难度**：中等
- **依赖**：需要实现BM25索引

### 优先级2：上下文窗口扩展
- **原因**：实现简单，效果好
- **实现难度**：低
- **依赖**：当前系统即可支持

### 优先级3：查询改写
- **原因**：利用现有的Ollama模型
- **实现难度**：中等
- **依赖**：需要Ollama API调用封装

### 优先级4：重排序
- **原因**：效果显著
- **实现难度**：中等
- **依赖**：需要下载CrossEncoder模型（约90MB）

---

## 5. 技术要点总结

### 文本分割核心思想
- **规则分割**：快速但不精确（当前方案）
- **语义分割**：准确但计算密集（LLM、Embedding方案）
- **混合分割**：结合结构识别和规则分割（推荐）

### RAG检索核心思想
- **单路召回** → **多路召回**（向量+BM25+稀疏）
- **粗排** → **精排**（Embedding → CrossEncoder）
- **点检索** → **上下文检索**（单chunk → 前后chunk扩展）
- **单查询** → **多查询**（查询改写、分解、扩展）

### 性能与效果权衡
| 方案 | 效果提升 | 计算成本 | 实现难度 |
|------|---------|---------|---------|
| 混合检索 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 上下文扩展 | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ |
| 查询改写 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 重排序 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| LLM分割 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Embedding分割 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 6. 参考资源

### 相关论文
- **混合检索**：["Precise Zero-Shot Dense Retrieval without Relevance Labels"](https://arxiv.org/abs/2212.10496)
- **重排序**：["RankT5: Fine-Tuning T5 for Text Ranking"](https://arxiv.org/abs/2210.10634)
- **语义分割**：["Semantic Text Segmentation with LLMs"](https://arxiv.org/abs/2304.09121)

### 开源项目
- **LlamaIndex**：高级RAG框架
- **LangChain**：包含多种文本分割器
- **RAGatouille**：集成重排序的RAG工具

### 模型推荐
- **Embedding模型**：`bge-large-zh-v1.5`（中文）
- **重排序模型**：`bge-reranker-large`（中文）
- **CrossEncoder**：`cross-encoder/ms-marco-MiniLM-L-6-v2`（英文）

---

**文档版本**：v1.0  
**最后更新**：2025年11月19日
