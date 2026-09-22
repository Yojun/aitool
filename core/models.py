# -*- coding: utf-8 -*-
"""
core/models.py
定義「廣告」與「受眾標籤」的資料結構，是整個 AI 投手系統的基本單位。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AdStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    LEARNING = "LEARNING"       # 學習期／樣本數不足，尚不足以判斷
    PENDING_REVIEW = "PENDING_REVIEW"


class AdAction(str, Enum):
    """群集偵查者針對每檔廣告給出的建議動作"""
    SCALE_UP = "SCALE_UP"       # 表現優異，加碼預算
    KEEP_ON = "KEEP_ON"         # 表現穩定，維持現狀
    WATCH = "WATCH"             # 表現普通或樣本不足，觀察中
    OPTIMIZE = "OPTIMIZE"       # 表現不佳但有救，建議調整素材/受眾後續跑
    PAUSE = "PAUSE"             # 表現不佳，建議關閉
    FIX_DELIVERY = "FIX_DELIVERY"  # 難以放送（曝光量/頻率異常），非單純成效問題


class TagAction(str, Enum):
    ENABLE = "ENABLE"
    ADD_NEW = "ADD_NEW"
    KEEP = "KEEP"
    DISABLE = "DISABLE"


@dataclass
class Ad:
    """一檔廣告的原始成效數據（由 Facebook/Google Ads API 拉取後組成）"""
    ad_id: str
    name: str
    platform: str = "facebook"          # facebook / google
    campaign_id: str = ""
    adset_id: str = ""

    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    conversions: int = 0
    revenue: float = 0.0
    frequency: float = 0.0              # 平均曝光頻率，用來偵測「難以放送」
    days_running: int = 1
    status: AdStatus = AdStatus.ACTIVE

    # ---- 由 metrics.py 計算後填入 ----
    ctr: float = 0.0
    cvr: float = 0.0
    cpc: float = 0.0
    cpa: Optional[float] = None
    roas: float = 0.0

    # ---- 由 clustering.py 填入 ----
    cluster_id: Optional[int] = None
    cluster_tier: Optional[str] = None   # A / B / C / D ...
    composite_score: Optional[float] = None
    suggested_action: Optional[AdAction] = None
    action_reason: str = ""

    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class AudienceTag:
    """一個受眾標籤／受眾組合（可以是單一興趣標籤，也可以是多標籤組合）"""
    tag_id: str
    name: str
    platform: str = "facebook"
    category: str = ""                  # 例如：興趣、行為、相似受眾、自訂受眾
    industry_relevance: float = 0.0     # 與廣告主產業的相關度評分 0~1

    reach: int = 0
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    conversions: int = 0
    revenue: float = 0.0

    ctr: float = 0.0
    cvr: float = 0.0
    cpa: Optional[float] = None
    roas: float = 0.0

    generation: int = 0                 # 屬於演化的第幾代
    parent_tags: tuple = field(default_factory=tuple)
    match_score: float = 0.0            # 與目標TA的相關度評分（演化後計算）
    status: str = "ACTIVE"
    suggested_action: Optional[TagAction] = None
    action_reason: str = ""
