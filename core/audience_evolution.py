# -*- coding: utf-8 -*-
"""
core/audience_evolution.py
「受眾演化演算法」(Audience Evolution Engine)

流程：
1. 產業辨識：依廣告主既有成效最好的受眾標籤，推論其所屬產業類別（比對大數據受眾資料庫）。
2. 標籤評分：對每個受眾標籤/組合計算成效分數 + 與目標TA的相關度分數 (match_score)。
3. 演化（遺傳演算法概念）：
   - 選擇 (Selection)：用分數做競賽選擇，留下表現最好的受眾組合作為「親代」
   - 交配 (Crossover)：把兩個高分親代的標籤屬性重組，產生新的候選受眾組合
   - 突變 (Mutation)：從大數據受眾資料庫隨機引入新標籤，增加多樣性，避免受眾同質化
4. 汰弱留強：對正在曝光的受眾組合，依評分與統計顯著性，全自動決定 ENABLE / ADD_NEW / DISABLE。
"""

from dataclasses import dataclass
import random
from typing import List, Dict, Optional
import numpy as np

from .models import AudienceTag, TagAction
from .metrics import compute_tag_metrics

MIN_TAG_IMPRESSIONS = 500       # 標籤層級統計顯著性門檻
MIN_TAG_CLICKS = 15

DEFAULT_TAG_WEIGHTS = {
    "roas": 0.4,
    "cvr": 0.25,
    "ctr": 0.15,
    "industry_relevance": 0.20,
}


@dataclass
class IndustryProfile:
    """從表現最佳的受眾標籤反推出的「廣告主產業輪廓」"""
    top_categories: List[str]
    keyword_signature: List[str]


class AudienceDataWarehouse:
    """
    模擬「獨家大數據受眾資料庫」。
    正式環境中，這裡會改成查詢公司內部的受眾資料倉儲（例如比對數千個廣告主的歷史受眾成效），
    這裡先用可替換的介面 + 範例資料呈現介接方式。
    """

    def __init__(self, candidate_pool: List[AudienceTag]):
        self._pool = candidate_pool

    def suggest_new_tags(self, industry: Optional[IndustryProfile], n: int = 3) -> List[AudienceTag]:
        """依產業輪廓，從資料庫中挑出尚未使用過、且相關度可能高的候選標籤"""
        pool = self._pool
        if industry:
            pool = sorted(
                pool,
                key=lambda t: -self._industry_match(t, industry),
            )
        return random.sample(pool, k=min(n, len(pool))) if pool else []

    @staticmethod
    def _industry_match(tag: AudienceTag, industry: IndustryProfile) -> float:
        score = 0.0
        if tag.category in industry.top_categories:
            score += 0.6
        if any(k in tag.name for k in industry.keyword_signature):
            score += 0.4
        return score


class AudienceEvolutionEngine:
    def __init__(
        self,
        warehouse: AudienceDataWarehouse,
        weights: Dict[str, float] = None,
        mutation_rate: float = 0.2,
        elite_ratio: float = 0.3,
    ):
        self.warehouse = warehouse
        self.weights = weights or DEFAULT_TAG_WEIGHTS
        self.mutation_rate = mutation_rate
        self.elite_ratio = elite_ratio

    # ------------------------------------------------------------------ #
    def identify_industry(self, tags: List[AudienceTag], top_n: int = 5) -> IndustryProfile:
        """主動辨識廣告主的受眾產業：取成效最好的 top_n 個標籤，歸納類別與關鍵字"""
        scored = sorted(tags, key=lambda t: -self._score_tag(t))[:top_n]
        categories = list({t.category for t in scored if t.category})
        keywords = list({kw for t in scored for kw in t.name.split()})
        return IndustryProfile(top_categories=categories, keyword_signature=keywords)

    def score_tags(self, tags: List[AudienceTag]) -> List[AudienceTag]:
        """對每個標籤計算成效指標 + 綜合評分 (match_score)"""
        for tag in tags:
            compute_tag_metrics(tag)
            tag.match_score = self._score_tag(tag)
        return tags

    def _score_tag(self, tag: AudienceTag) -> float:
        roas_component = min(tag.roas / 3.0, 1.0)          # ROAS 3 以上視為滿分基準
        cvr_component = min(tag.cvr * 10, 1.0)
        ctr_component = min(tag.ctr * 20, 1.0)
        relevance = tag.industry_relevance

        w = self.weights
        return (
            w["roas"] * roas_component
            + w["cvr"] * cvr_component
            + w["ctr"] * ctr_component
            + w["industry_relevance"] * relevance
        )

    # ------------------------------------------------------------------ #
    def evolve(self, current_tags: List[AudienceTag], generation: int) -> List[AudienceTag]:
        """
        產生下一代受眾組合：
        - Elite（高分親代）直接保留
        - Crossover：兩個親代的 category / industry_relevance 取加權平均，產生新組合
        - Mutation：一定機率從資料庫引入全新候選標籤
        """
        scored = self.score_tags(current_tags)
        ranked = sorted(scored, key=lambda t: -t.match_score)

        elite_count = max(1, int(len(ranked) * self.elite_ratio))
        elites = ranked[:elite_count]

        next_gen: List[AudienceTag] = list(elites)

        # Crossover：把菁英兩兩配對繁殖新受眾組合
        for i in range(0, len(elites) - 1, 2):
            parent_a, parent_b = elites[i], elites[i + 1]
            child = self._crossover(parent_a, parent_b, generation)
            next_gen.append(child)

        # Mutation：引入資料庫的新候選標籤，維持多樣性、避免受眾同質化
        industry = self.identify_industry(current_tags)
        n_mutants = max(1, int(len(current_tags) * self.mutation_rate))
        mutants = self.warehouse.suggest_new_tags(industry, n=n_mutants)
        for m in mutants:
            m.generation = generation
            m.action_reason = "由受眾資料庫新引入，用於維持多樣性/探索新受眾"
        next_gen.extend(mutants)

        return next_gen

    def _crossover(self, a: AudienceTag, b: AudienceTag, generation: int) -> AudienceTag:
        new_id = f"{a.tag_id}+{b.tag_id}-g{generation}"
        return AudienceTag(
            tag_id=new_id,
            name=f"{a.name} x {b.name}",
            platform=a.platform,
            category=a.category if a.match_score >= b.match_score else b.category,
            industry_relevance=(a.industry_relevance + b.industry_relevance) / 2,
            generation=generation,
            parent_tags=(a.tag_id, b.tag_id),
        )

    # ------------------------------------------------------------------ #
    def decide_actions(self, tags: List[AudienceTag]) -> List[AudienceTag]:
        """汰弱留強：對正在曝光的受眾組合，全自動決定開啟/新增/關閉"""
        for tag in tags:
            significant = (
                tag.impressions >= MIN_TAG_IMPRESSIONS or tag.clicks >= MIN_TAG_CLICKS
            )
            if not significant:
                tag.suggested_action = TagAction.KEEP
                tag.action_reason = "曝光/點擊樣本不足，維持現狀持續觀察"
                continue

            if tag.generation > 0 and tag.impressions == 0:
                tag.suggested_action = TagAction.ADD_NEW
                tag.action_reason = "演化產生之新受眾組合，建議新增測試"
            elif tag.match_score >= 0.6:
                tag.suggested_action = TagAction.ENABLE
                tag.action_reason = f"綜合評分 {tag.match_score:.2f}，表現優異，建議開啟/加碼"
            elif tag.match_score >= 0.35:
                tag.suggested_action = TagAction.KEEP
                tag.action_reason = f"綜合評分 {tag.match_score:.2f}，表現普通，維持現狀"
            else:
                tag.suggested_action = TagAction.DISABLE
                tag.action_reason = f"綜合評分 {tag.match_score:.2f}，表現不佳，建議關閉釋出預算"
        return tags
