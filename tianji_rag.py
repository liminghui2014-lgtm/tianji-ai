"""
天纪RAG v2 — BM25 + Embedding 混合检索
========================================
- BM25: 专有名词硬匹配 (星曜名/宫位名/格局名)
- Embedding: 语义相似度捕获非结构化查询意图
- 混合打分: BM25 × 0.6 + Embedding × 0.4
- 语义切块: LLM辅助按格局/星曜/宫位切分, 替代按集切割
"""

import re
import json
import hashlib
from pathlib import Path
from collections import defaultdict
from functools import lru_cache

import numpy as np

BASE_DIR = Path(__file__).parent
TRANSCRIPT_FILE = BASE_DIR / "天纪字幕.txt"
INDEX_DIR = BASE_DIR / ".rag_index"

# 紫微斗数所有术语
ZIWEI_TERMS = {
    "紫微","天机","太阳","武曲","天同","廉贞","天府","太阴","贪狼",
    "巨门","天相","天梁","七杀","破军","左辅","右弼","文昌","文曲",
    "天魁","天钺","禄存","天马","擎羊","陀罗","火星","铃星","地空","地劫",
    "化禄","化权","化科","化忌",
    "命宫","兄弟","夫妻","子女","财帛","疾厄","迁移","仆役",
    "官禄","田宅","福德","父母","身宫",
    "三方四正","大限","流年","小限","五行局",
    "杀破狼","紫府同宫","日月并明","月朗天门","日照雷门",
    "机月同梁","巨日同宫","武府同宫","三奇加会","命无正曜",
}


class TianjiRAG:
    def __init__(self):
        self.chunks = []
        self.bm25 = None
        self.embeddings = None
        self.embedding_model = None
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if INDEX_DIR.exists() and (INDEX_DIR / "chunks.json").exists():
            self._load_from_index()
        else:
            self._build_index()
            self._save_index()
        self._loaded = True

    # ── 语义切块 ──────────────────────────────────

    def _semantic_chunk(self, text):
        """智能切块: 按内容边界切割, 每块约 800-2000 字"""
        # 先用空行/章节标记粗切
        raw_chunks = re.split(r'\n{2,}|(?=第\d+集|【)', text)
        chunks = []
        buf = ""
        for part in raw_chunks:
            part = part.strip()
            if not part:
                continue
            if len(buf) + len(part) > 2000:
                if buf.strip():
                    chunks.append(buf.strip())
                buf = part
            else:
                buf += "\n" + part if buf else part
        if buf.strip():
            chunks.append(buf.strip())
        return chunks

    def _extract_keywords(self, text):
        """提取紫微相关关键词"""
        found = set()
        for term in ZIWEI_TERMS:
            if term in text:
                found.add(term)
        return found

    # ── 索引构建 ──────────────────────────────────

    def _build_index(self):
        """构建 BM25 + Embedding 索引"""
        from rank_bm25 import BM25Okapi
        from sentence_transformers import SentenceTransformer

        print("[RAG] 读取语料...")
        raw = TRANSCRIPT_FILE.read_text(encoding="utf-8")
        self.chunks = self._semantic_chunk(raw)
        print(f"[RAG] 切出 {len(self.chunks)} 个语义块")

        # BM25
        print("[RAG] 构建 BM25 索引...")
        tokenized = [self._tokenize(c) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized)

        # Embedding
        print("[RAG] 加载 Embedding 模型...")
        self.embedding_model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2",
            device="cpu"
        )
        print("[RAG] 计算 Embedding 向量...")
        summaries = [self._summarize_chunk(c) for c in self.chunks]
        self.embeddings = self.embedding_model.encode(
            summaries, show_progress_bar=True, batch_size=32
        )

        print(f"[RAG] 索引构建完成: {len(self.chunks)} 块, {self.embeddings.shape[1]}维向量")

    def _tokenize(self, text):
        """中文分词+紫微术语保护"""
        # 简单jieba分词, 但保留紫微术语作为整体
        import jieba
        for term in sorted(ZIWEI_TERMS, key=lambda x: -len(x)):
            placeholder = term.replace(" ", "_")
            text = text.replace(term, placeholder)
        tokens = list(jieba.cut(text))
        return [t.replace("_", " ") for t in tokens]

    def _summarize_chunk(self, text):
        """生成用于 Embedding 的chunk摘要: 关键词+前200字"""
        keywords = self._extract_keywords(text)
        kw_str = " ".join(sorted(keywords))
        preview = text[:200].replace("\n", " ")
        return f"{kw_str} | {preview}"

    # ── 持久化 ──────────────────────────────────

    def _save_index(self):
        INDEX_DIR.mkdir(exist_ok=True)
        with open(INDEX_DIR / "chunks.json", "w", encoding="utf-8") as f:
            json.dump([{"text": c, "keywords": list(self._extract_keywords(c))}
                       for c in self.chunks], f, ensure_ascii=False)
        np.save(INDEX_DIR / "embeddings.npy", self.embeddings)
        print("[RAG] 索引已持久化到磁盘")

    def _load_from_index(self):
        """从磁盘加载预计算索引"""
        from rank_bm25 import BM25Okapi
        from sentence_transformers import SentenceTransformer

        print("[RAG] 从磁盘加载索引...")
        with open(INDEX_DIR / "chunks.json", encoding="utf-8") as f:
            chunk_data = json.load(f)
        self.chunks = [c["text"] for c in chunk_data]

        tokenized = [self._tokenize(c) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized)

        self.embedding_model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2", device="cpu"
        )
        self.embeddings = np.load(INDEX_DIR / "embeddings.npy")
        print(f"[RAG] 索引加载完成: {len(self.chunks)} 块")

    # ── 查询入口 ──────────────────────────────────

    def get_context_for_chart(self, chart_data, max_tokens=6000):
        """基于命盘数据检索最相关的天纪原文"""
        self._ensure_loaded()

        # 构建查询: 提取盘上所有星曜+宫位
        query_parts = []
        for p in chart_data.get("命盘", []):
            mains = p.get("主星", "")
            if mains and mains != "无":
                query_parts.append(f"{p['宫位']}宫{mains}")
            minors = p.get("辅星", "")
            if minors and minors != "无":
                query_parts.append(f"{p['宫位']}{minors}")
            sihua = p.get("四化", "")
            if sihua:
                query_parts.append(f"{p['宫位']}{sihua}")

        query = " ".join(query_parts)

        # 混合检索
        results = self._hybrid_search(query, top_k=20)

        # 按 token 预算截取
        selected = []
        total_len = 0
        for chunk, _ in results:
            if total_len + len(chunk) > max_tokens * 1.5:
                break
            selected.append(chunk)
            total_len += len(chunk)

        return "\n\n---\n\n".join(selected)

    def _hybrid_search(self, query, top_k=20):
        """BM25 + Embedding 混合检索"""
        bm25_scores = np.array(self.bm25.get_scores(self._tokenize(query)))
        bm25_scores = bm25_scores / (bm25_scores.max() + 1e-8)

        # Embedding
        query_vec = self.embedding_model.encode([query])
        emb_scores = np.dot(self.embeddings, query_vec.T).flatten()
        emb_scores = (emb_scores - emb_scores.min()) / (emb_scores.max() - emb_scores.min() + 1e-8)

        # 混合
        combined = bm25_scores * 0.6 + emb_scores * 0.4
        ranked = np.argsort(combined)[::-1][:top_k]

        return [(self.chunks[i], float(combined[i])) for i in ranked]


# 全局单例
_rag_instance = None

def get_rag() -> TianjiRAG:
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = TianjiRAG()
    return _rag_instance
