# -*- coding: utf-8 -*-
"""
core/platform_connectors.py

與 Facebook Marketing API / Google Ads API 交換資料的介接層。

★ 重要說明 ★
這裡提供的是「可替換的介面骨架」，方法簽名對應到真實 API 需要的操作。
要串接正式環境，需要：
  - Facebook: 一組具備 ads_management 權限的 System User Access Token，
    以及 facebook_business SDK (pip install facebook_business)。
    主要會用到 AdSet.get_targeting_sentence_lines() / Campaign.get_insights() 等端點，
    來讀取現有廣告組合的曝光/成效數據，並用 AdSet.remote_update() 開關受眾組合。
  - Google: 一組 Google Ads API 的 developer token + OAuth refresh token，
    以及 google-ads SDK (pip install google-ads)。
    主要會用到 GoogleAdsService.search_stream (GAQL) 讀取 campaign/ad_group/audience 成效，
    以及 AudienceService / CampaignCriterionService 開關受眾條件。

在拿到正式憑證前，可以先用下方的 Stub 版本開發與測試整體演算法邏輯，
之後只需要把 fetch_* / push_* 方法內部換成真實 API 呼叫即可，上層演算法完全不用改。
"""

from abc import ABC, abstractmethod
from typing import List
import random

from .models import Ad, AudienceTag, TagAction


class PlatformConnector(ABC):
    """所有廣告平台介接器共用的介面"""

    platform_name: str = "base"

    @abstractmethod
    def fetch_ad_performance(self, campaign_ids: List[str], lookback_days: int = 7) -> List[Ad]:
        """拉取指定期間內各廣告的成效數據"""
        raise NotImplementedError

    @abstractmethod
    def fetch_audience_candidates(self, target_description: str, n: int = 20) -> List[AudienceTag]:
        """依行銷活動目標TA描述，向平台受眾資料庫查詢候選受眾標籤"""
        raise NotImplementedError

    @abstractmethod
    def push_ad_action(self, ad: Ad) -> bool:
        """把廣告的建議動作（開啟/關閉/調整預算）寫回平台"""
        raise NotImplementedError

    @abstractmethod
    def push_audience_action(self, tag: AudienceTag) -> bool:
        """把受眾組合的建議動作（開啟/新增/關閉）寫回平台"""
        raise NotImplementedError


class FacebookConnector(PlatformConnector):
    platform_name = "facebook"

    def __init__(self, access_token: str = None, ad_account_id: str = None):
        # 正式環境：在此用 facebook_business SDK 初始化 FacebookAdsApi.init(...)
        self.access_token = access_token
        self.ad_account_id = ad_account_id

    def fetch_ad_performance(self, campaign_ids, lookback_days=7) -> List[Ad]:
        # TODO(正式串接): 呼叫 Campaign.get_insights(fields=[...], params={"date_preset": ...})
        raise NotImplementedError(
            "尚未設定 Facebook Marketing API 憑證，請改用 MockConnector 進行開發測試，"
            "或提供 access_token / ad_account_id 後在此串接 facebook_business SDK。"
        )

    def fetch_audience_candidates(self, target_description, n=20) -> List[AudienceTag]:
        raise NotImplementedError("需串接 Facebook Interest/Behavior Targeting Search API")

    def push_ad_action(self, ad: Ad) -> bool:
        raise NotImplementedError("需串接 Ad.remote_update(params={'status': ...})")

    def push_audience_action(self, tag: AudienceTag) -> bool:
        raise NotImplementedError("需串接 AdSet.remote_update() 調整 targeting")


class GoogleAdsConnector(PlatformConnector):
    platform_name = "google"

    def __init__(self, developer_token: str = None, customer_id: str = None):
        # 正式環境：在此用 google-ads SDK 建立 GoogleAdsClient
        self.developer_token = developer_token
        self.customer_id = customer_id

    def fetch_ad_performance(self, campaign_ids, lookback_days=7) -> List[Ad]:
        # TODO(正式串接): 用 GAQL 查詢 ad_group_ad / metrics
        raise NotImplementedError(
            "尚未設定 Google Ads API 憑證，請改用 MockConnector 進行開發測試，"
            "或提供 developer_token / customer_id 後在此串接 google-ads SDK。"
        )

    def fetch_audience_candidates(self, target_description, n=20) -> List[AudienceTag]:
        raise NotImplementedError("需串接 Google Ads audience_insights / keyword_plan_idea_service")

    def push_ad_action(self, ad: Ad) -> bool:
        raise NotImplementedError("需串接 AdGroupAdService.MutateAdGroupAds")

    def push_audience_action(self, tag: AudienceTag) -> bool:
        raise NotImplementedError("需串接 CampaignCriterionService 開關受眾條件")


class MockConnector(PlatformConnector):
    """
    開發/展示用的模擬介接器：產生隨機但合理的成效資料，
    讓整個分群 + 受眾演化流程可以在沒有真實 API 憑證的情況下完整跑通。
    """

    platform_name = "mock"

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def fetch_ad_performance(self, campaign_ids, lookback_days=7) -> List[Ad]:
        ads = []
        for cid in campaign_ids:
            for i in range(random.randint(4, 8)):
                impressions = random.randint(200, 50000)
                ctr = random.uniform(0.005, 0.06)
                clicks = int(impressions * ctr)
                cvr = random.uniform(0.01, 0.15)
                conversions = int(clicks * cvr)
                spend = round(clicks * random.uniform(3, 15), 2)
                revenue = round(conversions * random.uniform(200, 1500), 2)
                ads.append(
                    Ad(
                        ad_id=f"{cid}-ad{i}",
                        name=f"{cid} 廣告素材 {i}",
                        platform="facebook" if i % 2 == 0 else "google",
                        campaign_id=cid,
                        impressions=impressions,
                        clicks=clicks,
                        spend=spend,
                        conversions=conversions,
                        revenue=revenue,
                        frequency=round(random.uniform(1.0, 4.5), 2),
                        days_running=random.randint(1, 30),
                    )
                )
        return ads

    def fetch_audience_candidates(self, target_description, n=20) -> List[AudienceTag]:
        categories = ["興趣", "行為", "相似受眾", "自訂受眾", "人口統計"]
        tags = []
        for i in range(n):
            impressions = random.randint(0, 20000)
            clicks = int(impressions * random.uniform(0.005, 0.05))
            conversions = int(clicks * random.uniform(0.01, 0.12))
            spend = round(clicks * random.uniform(3, 12), 2)
            revenue = round(conversions * random.uniform(200, 1200), 2)
            tags.append(
                AudienceTag(
                    tag_id=f"tag-{i}",
                    name=f"{target_description}-受眾{i}",
                    category=random.choice(categories),
                    industry_relevance=round(random.uniform(0.2, 1.0), 2),
                    reach=random.randint(10000, 2_000_000),
                    impressions=impressions,
                    clicks=clicks,
                    spend=spend,
                    conversions=conversions,
                    revenue=revenue,
                )
            )
        return tags

    def push_ad_action(self, ad: Ad) -> bool:
        print(f"[MockConnector] 廣告 {ad.ad_id} -> 動作: {ad.suggested_action}（{ad.action_reason}）")
        return True

    def push_audience_action(self, tag: AudienceTag) -> bool:
        print(f"[MockConnector] 受眾 {tag.tag_id} -> 動作: {tag.suggested_action}（{tag.action_reason}）")
        return True
