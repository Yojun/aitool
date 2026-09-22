# -*- coding: utf-8 -*-
"""
core/clustering.py
「群集偵查者」(Cluster Scout)

作法：
1. 把每檔廣告的多項成效指標（CTR / CVR / ROAS / CPA / 轉換效率）視為多維度空間中的一個點。
2. 用 K-Means 在這個幾何空間中把廣告分群（自動用輪廓係數 silhouette score 挑選最佳群數 k）。
3. 每個群集計算「綜合分數」(各維度標準化後的加權平均)，並依分數高低排出 A/B/C/D... 等成效等級。
4. 結合統計顯著性與「難以放送」偵測，給出每檔廣告的建議動作與優化優先順序。
"""

from dataclasses import dataclass
from typing import List, Dict
import numpy as np

from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .models import Ad, AdStatus, AdAction
from .metrics import (
    compute_ad_metrics,
    build_feature_matrix,
    zscore_normalize,
    is_statistically_significant,
    is_delivery_impaired,
)

# 各指標在綜合分數中的權重，可依廣告主的 KPI 目標調整
DEFAULT_WEIGHTS = {
    "ctr": 0.15,
    "cvr": 0.20,
    "roas": 0.35,
    "cpa_inv": 0.20,
    "conv_efficiency": 0.10,
}

TIER_LABELS = ["A", "B", "C", "D", "E", "F"]


@dataclass
class ClusterSummary:
    cluster_id: int
    tier: str
    ad_count: int
    avg_roas: float
    avg_ctr: float
    avg_cvr: float
    composite_score: float
    recommended_action: AdAction


class AdClusterAnalyzer:
    """對一批已投放一段時間的廣告進行多維度分群與優化排序"""

    def __init__(self, weights: Dict[str, float] = None, k_range=(2, 6)):
        self.weights = weights or DEFAULT_WEIGHTS
        self.k_min, self.k_max = k_range

    # ------------------------------------------------------------------ #
    def analyze(self, ads: List[Ad]) -> List[Ad]:
        """主流程：計算指標 -> 建構特徵空間 -> 分群 -> 評分排序 -> 產出建議動作"""
        if not ads:
            return []

        for ad in ads:
            compute_ad_metrics(ad)

        # 樣本太少（<k_min）就不分群，直接進統一規則判斷
        eligible = [ad for ad in ads if is_statistically_significant(ad)]
        pending = [ad for ad in ads if ad not in eligible]

        if len(eligible) >= self.k_min:
            self._cluster_and_score(eligible)
        else:
            for ad in eligible:
                self._fallback_rule_based(ad)

        for ad in pending:
            self._handle_low_sample_ad(ad)

        # 依 composite_score 由高到低排出「優化先後順序」
        ads_sorted = sorted(
            ads,
            key=lambda a: (a.composite_score is None, -(a.composite_score or -999)),
        )
        return ads_sorted

    # ------------------------------------------------------------------ #
    def _cluster_and_score(self, ads: List[Ad]) -> None:
        raw_matrix = build_feature_matrix(ads)
        matrix = zscore_normalize(raw_matrix)

        k = self._choose_optimal_k(matrix)
        kmeans = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = kmeans.fit_predict(matrix)

        # 加權綜合分數（在標準化後的空間中，直接用權重線性組合當作分群品質分數）
        weight_vec = np.array(
            [
                self.weights["ctr"],
                self.weights["cvr"],
                self.weights["roas"],
                self.weights["cpa_inv"],
                self.weights["conv_efficiency"],
            ]
        )
        composite_scores = matrix @ weight_vec

        for ad, label, score in zip(ads, labels, composite_scores):
            ad.cluster_id = int(label)
            ad.composite_score = float(score)

        # 計算每個群集的平均分數，決定群集等級（分數越高 tier 越前面）
        cluster_ids = sorted(set(labels.tolist()))
        cluster_avg = {
            cid: np.mean([a.composite_score for a in ads if a.cluster_id == cid])
            for cid in cluster_ids
        }
        ranked_clusters = sorted(cluster_avg.keys(), key=lambda c: -cluster_avg[c])
        tier_map = {cid: TIER_LABELS[i] for i, cid in enumerate(ranked_clusters)}

        for ad in ads:
            ad.cluster_tier = tier_map[ad.cluster_id]
            self._assign_action(ad, ad.cluster_tier, len(ranked_clusters))

    def _choose_optimal_k(self, matrix: np.ndarray) -> int:
        n = matrix.shape[0]
        k_max = min(self.k_max, n - 1) if n > self.k_min else self.k_min
        if k_max < self.k_min:
            return max(2, n) if n >= 2 else 1

        best_k, best_score = self.k_min, -1.0
        for k in range(self.k_min, k_max + 1):
            try:
                km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(matrix)
                if len(set(km.labels_)) < 2:
                    continue
                score = silhouette_score(matrix, km.labels_)
                if score > best_score:
                    best_score, best_k = score, k
            except Exception:
                continue
        return best_k

    # ------------------------------------------------------------------ #
    def _assign_action(self, ad: Ad, tier: str, n_clusters: int) -> None:
        # 「難以放送」優先於單純成效判斷，因為問題根源不同（要調整投遞設定，不是關廣告）
        if is_delivery_impaired(ad):
            ad.suggested_action = AdAction.FIX_DELIVERY
            ad.action_reason = f"曝光頻率達 {ad.frequency:.1f}，疑似受眾疲乏 / 難以放送"
            return

        if tier == "A":
            ad.suggested_action = AdAction.SCALE_UP
            ad.action_reason = "成效群集中排名最優，建議加碼預算"
        elif tier in ("B",):
            ad.suggested_action = AdAction.KEEP_ON
            ad.action_reason = "成效穩定，維持現有預算與素材"
        elif tier in ("C",):
            ad.suggested_action = AdAction.OPTIMIZE
            ad.action_reason = "成效中後段，建議調整素材/受眾後觀察"
        else:
            ad.suggested_action = AdAction.PAUSE
            ad.action_reason = f"成效落於後段群集（{tier}級），建議關閉並釋出預算"

    def _fallback_rule_based(self, ad: Ad) -> None:
        """樣本數夠但不足以分群（例如只有1~2檔廣告）時，用簡單規則判斷"""
        if is_delivery_impaired(ad):
            ad.suggested_action = AdAction.FIX_DELIVERY
            ad.action_reason = "曝光頻率過高，疑似難以放送"
        elif ad.roas >= 2.0:
            ad.suggested_action = AdAction.SCALE_UP
            ad.action_reason = "ROAS表現優異"
        elif ad.roas >= 1.0:
            ad.suggested_action = AdAction.KEEP_ON
            ad.action_reason = "ROAS打平以上，維持現狀"
        else:
            ad.suggested_action = AdAction.OPTIMIZE
            ad.action_reason = "ROAS未達損益平衡，建議優化"
        ad.composite_score = ad.roas

    def _handle_low_sample_ad(self, ad: Ad) -> None:
        """曝光/點擊數太少，還在學習期，不該貿然關閉"""
        ad.status = AdStatus.LEARNING
        ad.suggested_action = AdAction.WATCH
        ad.action_reason = "曝光/點擊樣本數尚不足以判斷成效，建議繼續觀察學習期"
        ad.composite_score = -1.0  # 排序時放在最後面，避免蓋過已有結論的廣告


def summarize_clusters(ads: List[Ad]) -> List[ClusterSummary]:
    """把分群結果彙總成報表，方便輸出/呈現優化先後順序"""
    clustered = [a for a in ads if a.cluster_id is not None]
    if not clustered:
        return []

    summaries = []
    for cid in sorted(set(a.cluster_id for a in clustered)):
        group = [a for a in clustered if a.cluster_id == cid]
        summaries.append(
            ClusterSummary(
                cluster_id=cid,
                tier=group[0].cluster_tier,
                ad_count=len(group),
                avg_roas=float(np.mean([a.roas for a in group])),
                avg_ctr=float(np.mean([a.ctr for a in group])),
                avg_cvr=float(np.mean([a.cvr for a in group])),
                composite_score=float(np.mean([a.composite_score for a in group])),
                recommended_action=group[0].suggested_action,
            )
        )
    summaries.sort(key=lambda s: s.tier)
    return summaries
