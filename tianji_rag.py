"""
天纪RAG — 从98万字的倪海夏天纪字幕中检索相关知识
====================================================
索引策略：按集分割 → 提取星曜/宫位关键词 → 匹配检索
"""

import re
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent
TRANSCRIPT_FILE = BASE_DIR / "天纪字幕.txt"

# 紫微斗数所有术语（用于检索）
ZIWEI_TERMS = {
    # 星曜
    "紫微", "天机", "太阳", "武曲", "天同", "廉贞", "天府", "太阴", "贪狼",
    "巨门", "天相", "天梁", "七杀", "破军", "左辅", "右弼", "文昌", "文曲",
    "天魁", "天钺", "禄存", "天马", "擎羊", "陀罗", "火星", "铃星", "地空", "地劫",
    # 四化
    "化禄", "化权", "化科", "化忌",
    # 宫位
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄", "迁移", "仆役",
    "官禄", "田宅", "福德", "父母", "身宫",
    # 概念
    "三方四正", "大限", "流年", "小限", "五行局",
}


class TianjiRAG:
    def __init__(self):
        self.episodes = {}      # {ep_num: full_text}
        self.paragraphs = []    # [(ep_num, paragraph_text, keywords)]
        self._load_and_index()

    def _load_and_index(self):
        """加载字幕文件并按集分割建立索引"""
        if not TRANSCRIPT_FILE.exists():
            print(f"[RAG] 未找到字幕文件: {TRANSCRIPT_FILE}")
            return

        raw = TRANSCRIPT_FILE.read_text(encoding="utf-8")
        print(f"[RAG] 加载字幕: {len(raw)} 字")

        # 按"第XX集"分割
        parts = re.split(r'(第\d+集)', raw)
        current_ep = None
        current_text = []

        for part in parts:
            if re.match(r'第\d+集', part):
                if current_ep and current_text:
                    full = ''.join(current_text)
                    self.episodes[current_ep] = full
                    # 按句号/换行分段
                    paragraphs = re.split(r'[。\n]', full)
                    for para in paragraphs:
                        para = para.strip()
                        if len(para) > 15:
                            keywords = [t for t in ZIWEI_TERMS if t in para]
                            self.paragraphs.append((current_ep, para, keywords))
                current_ep = part
                current_text = []
            elif current_ep:
                current_text.append(part)

        # 最后一集
        if current_ep and current_text:
            full = ''.join(current_text)
            self.episodes[current_ep] = full

        print(f"[RAG] 索引: {len(self.episodes)} 集, {len(self.paragraphs)} 个段落")

    def search(self, chart_data, max_results=30):
        """
        根据命盘数据检索最相关的天纪原文段落。
        chart_data: iztro 输出的命盘 JSON
        返回: [(episode, paragraph, relevance_score)]
        """
        # 从命盘中提取关键词
        query_terms = set()

        basic = chart_data.get("基本信息", {})
        # 五行局是关键词
        wuxing = chart_data.get("五行局", "")
        if wuxing:
            query_terms.add(wuxing)

        palaces = chart_data.get("命盘", [])
        for p in palaces:
            # 宫位名
            query_terms.add(p.get("宫位", ""))
            # 主星
            for star in (p.get("主星", "").split("、")):
                star = star.strip()
                if star and star != "无":
                    query_terms.add(star)
            # 四化
            for m in (p.get("四化", "").split("、")):
                m = m.strip()
                if m:
                    query_terms.add(m)

        query_terms.discard("")
        query_terms.discard("无")

        # 匹配每个段落
        scored = []
        for ep, para, keywords in self.paragraphs:
            if not keywords:
                continue
            # 相关性 = 命中关键词数
            hits = len(set(keywords) & query_terms)
            if hits > 0:
                # 加权：命中"命宫"加分，有星曜名加分
                score = hits
                if "命宫" in keywords:
                    score += 1
                scored.append((ep, para, score))

        # 排序取 TOP
        scored.sort(key=lambda x: -x[2])
        return scored[:max_results]

    def get_context_for_chart(self, chart_data, max_tokens=8000):
        """
        为命盘生成可注入 prompt 的上下文。
        优先检索命宫、财帛、官禄、夫妻相关的段落。
        """
        results = self.search(chart_data, max_results=40)

        if not results:
            return "（未找到相关天纪内容）"

        # 按集分组，去重
        seen = set()
        chunks = []
        total_chars = 0

        for ep, para, score in results:
            # 去重（高度相似的段落）
            key = para[:30]
            if key in seen:
                continue
            seen.add(key)

            chunks.append(f"【{ep}】{para}")
            total_chars += len(para)
            if total_chars > max_tokens * 2:  # 大约2字/1token
                break

        return "\n".join(chunks)


# 单例
_rag_instance = None


def get_rag():
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = TianjiRAG()
    return _rag_instance
