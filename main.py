# -*- coding: utf-8 -*-
"""
main.py
AI 投手主流程示範：

  1. 拉取廣告成效數據 -> 多維度幾何空間分群 (群集偵查者) -> 產出優化優先順序
  2. 拉取/演化受眾標籤 -> 受眾評分 -> 遺傳演算法式演化 -> 汰弱留強決定開關

實際上線時，把 MockConnector 換成 FacebookConnector / GoogleAdsConnector 並帶入正式憑證即可，
上層的 AdClusterAnalyzer / AudienceEvolutionEngine 完全不需要修改。
"""

from core.platform_connectors import MockConnector
from core.clustering import AdClusterAnalyzer, summarize_clusters
from core.audience_evolution import AudienceEvolutionEngine, AudienceDataWarehouse
from core.models import AdAction, TagAction


def run_ad_optimization(connector, campaign_ids):
    print("=" * 70)
    print("Step 1. 拉取廣告成效數據")
    print("=" * 70)
    ads = connector.fetch_ad_performance(campaign_ids, lookback_days=7)
    print(f"共取得 {len(ads)} 檔廣告的成效數據\n")

    print("=" * 70)
    print("Step 2. 多維度幾何空間分群（群集偵查者）")
    print("=" * 70)
    analyzer = AdClusterAnalyzer(k_range=(2, 5))
    ranked_ads = analyzer.analyze(ads)

    print("\n--- 群集彙總 ---")
    for s in summarize_clusters(ranked_ads):
        print(
            f"群集 {s.cluster_id} [{s.tier}級] 廣告數={s.ad_count:2d} "
            f"平均ROAS={s.avg_roas:5.2f} 平均CTR={s.avg_ctr:.2%} 平均CVR={s.avg_cvr:.2%} "
            f"綜合分數={s.composite_score:6.3f} 建議={s.recommended_action.value}"
        )

    print("\n--- 優化優先順序（前10筆）---")
    for ad in ranked_ads[:10]:
        score_display = f"{ad.composite_score:6.3f}" if ad.composite_score is not None else "  N/A "
        print(
            f"[{ad.cluster_tier or '-'}] {ad.name:14s} score={score_display} "
            f"ROAS={ad.roas:5.2f} -> {ad.suggested_action.value:12s} | {ad.action_reason}"
        )

    # 全自動開啟/關閉：實際上線時取消下方註解，把建議動作寫回平台
    for ad in ranked_ads:
        if ad.suggested_action in (AdAction.PAUSE, AdAction.SCALE_UP, AdAction.FIX_DELIVERY):
            connector.push_ad_action(ad)

    return ranked_ads


def run_audience_evolution(connector, target_description, generations=3):
    print("\n" + "=" * 70)
    print("Step 3. 受眾演化演算法")
    print("=" * 70)
    tags = connector.fetch_audience_candidates(target_description, n=15)

    warehouse = AudienceDataWarehouse(candidate_pool=connector.fetch_audience_candidates(
        target_description, n=30
    ))
    engine = AudienceEvolutionEngine(warehouse=warehouse)

    industry = engine.identify_industry(tags)
    print(f"辨識出的受眾產業輪廓：類別={industry.top_categories} 關鍵字={industry.keyword_signature[:5]}...")

    current_generation = engine.score_tags(tags)
    for gen in range(1, generations + 1):
        print(f"\n--- 第 {gen} 代受眾演化 ---")
        current_generation = engine.evolve(current_generation, generation=gen)
        current_generation = engine.score_tags(current_generation)
        top = sorted(current_generation, key=lambda t: -t.match_score)[:5]
        for t in top:
            print(f"  {t.name:20s} 評分={t.match_score:.3f} 類別={t.category} (gen{t.generation})")

    print("\n--- 汰弱留強：全自動開啟/新增/關閉 ---")
    final_tags = engine.decide_actions(current_generation)
    for t in sorted(final_tags, key=lambda x: -x.match_score):
        print(f"{t.name:20s} 評分={t.match_score:.3f} -> {t.suggested_action.value:8s} | {t.action_reason}")

    for t in final_tags:
        if t.suggested_action in (TagAction.ENABLE, TagAction.DISABLE, TagAction.ADD_NEW):
            connector.push_audience_action(t)

    return final_tags


if __name__ == "__main__":
    connector = MockConnector(seed=7)

    ranked_ads = run_ad_optimization(connector, campaign_ids=["CMP_001", "CMP_002"])
    final_tags = run_audience_evolution(connector, target_description="運動保健品")
