# -*- coding: utf-8 -*-
"""
core/metrics.py
計算廣告／受眾標籤的衍生成效指標，並提供多維度特徵正規化（給幾何空間演算法使用）。
"""

from typing import List
import numpy as np

from .models import Ad, AudienceTag

MIN_IMPRESSIONS_FOR_SIGNIFICANCE = 1000   # 判斷「統計顯著」所需的最低曝光數
MIN_CLICKS_FOR_SIGNIFICANCE = 30          # 判斷「統計顯著」所需的最低點擊數
FREQUENCY_FATIGUE_THRESHOLD = 4.0         # 頻率超過此值視為「難以放送/受眾疲乏」


def compute_ad_metrics(ad: Ad) -> Ad:
    """由原始數據（曝光、點擊、花費、轉換、營收）計算 CTR / CVR / CPC / CPA / ROAS"""
    ad.ctr = _safe_div(ad.clicks, ad.impressions)
    ad.cvr = _safe_div(ad.conversions, ad.clicks)
    ad.cpc = _safe_div(ad.spend, ad.clicks)
    ad.cpa = _safe_div(ad.spend, ad.conversions) if ad.conversions > 0 else None
    ad.roas = _safe_div(ad.revenue, ad.spend)
    return ad


def compute_tag_metrics(tag: AudienceTag) -> AudienceTag:
    tag.ctr = _safe_div(tag.clicks, tag.impressions)
    tag.cvr = _safe_div(tag.conversions, tag.clicks)
    tag.cpa = _safe_div(tag.spend, tag.conversions) if tag.conversions > 0 else None
    tag.roas = _safe_div(tag.revenue, tag.spend)
    return tag


def is_statistically_significant(ad: Ad) -> bool:
    """樣本數是否足夠支撐判斷（避免因數據量太小就誤殺廣告）"""
    return (
        ad.impressions >= MIN_IMPRESSIONS_FOR_SIGNIFICANCE
        or ad.clicks >= MIN_CLICKS_FOR_SIGNIFICANCE
    )


def is_delivery_impaired(ad: Ad) -> bool:
    """偵測「難以放送」：頻率過高但曝光成長停滯、或花費遠低於設定預算節奏"""
    return ad.frequency >= FREQUENCY_FATIGUE_THRESHOLD and ad.days_running >= 3


def build_feature_matrix(ads: List[Ad]) -> np.ndarray:
    """
    將每檔廣告轉成多維度特徵向量，供幾何空間分群（K-Means等）使用。
    維度：CTR、CVR、ROAS、CPA(反向，用倒數避免除以0)、花費效率(轉換/花費)
    所有維度先做 log1p 壓縮離群值，再交給呼叫端做 z-score 標準化。
    """
    features = []
    for ad in ads:
        cpa_inv = 1.0 / ad.cpa if ad.cpa and ad.cpa > 0 else 0.0
        conv_efficiency = _safe_div(ad.conversions, ad.spend)
        vec = [
            ad.ctr,
            ad.cvr,
            ad.roas,
            cpa_inv,
            conv_efficiency,
        ]
        vec = [np.log1p(max(v, 0)) for v in vec]
        features.append(vec)
    return np.array(features, dtype=float)


def zscore_normalize(matrix: np.ndarray) -> np.ndarray:
    """對特徵矩陣做 z-score 標準化，避免不同量級指標互相蓋過（例如 ROAS vs CTR）"""
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std[std == 0] = 1.0  # 避免除以0
    return (matrix - mean) / std


def _safe_div(a, b):
    return (a / b) if b else 0.0
