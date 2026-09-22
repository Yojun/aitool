# AI 投手系統（廣告成效分群優化 + 受眾演化演算法）

自動化投放優化工具，分成兩大引擎：

1. **群集偵查者 (Cluster Scout)** — `core/clustering.py`
   偵測每檔廣告成效，用多維度幾何空間分群（K-Means + 輪廓係數自動選群數），
   把廣告分進不同成效等級的群集（A/B/C…），彙總得出優化的先後順序，並針對
   「難以放送」（頻率過高/疲乏）與「樣本不足」的廣告給出對應處理，而不是單純用
   單一指標粗暴判斷。

2. **受眾演化演算法 (Audience Evolution Engine)** — `core/audience_evolution.py`
   對正在曝光的受眾組合評分，並用遺傳演算法概念（選擇 / 交配 / 突變）演化出新的
   受眾組合候選，結合「大數據受眾資料庫」介面自動判斷廣告主所屬產業、找出與目標
   TA最相關的標籤，最後對受眾組合做汰弱留強，全自動 ENABLE / ADD_NEW / DISABLE。

兩者都透過 `core/platform_connectors.py` 的**可替換介接層**與 Facebook / Google
交換資料，開發時先用 `MockConnector` 模擬數據跑通全流程，正式上線只需要把
connector 換成帶有真實憑證的 `FacebookConnector` / `GoogleAdsConnector`，
上層演算法邏輯完全不用修改。

## 專案結構

```
ai_bidder/
├── core/
│   ├── models.py               # Ad / AudienceTag 資料結構
│   ├── metrics.py               # CTR/CVR/CPA/ROAS 計算、特徵正規化
│   ├── clustering.py            # 多維度幾何空間分群 + 優化優先順序（群集偵查者）
│   ├── audience_evolution.py    # 受眾評分 + 遺傳演算法式演化 + 汰弱留強
│   └── platform_connectors.py   # Facebook/Google API 介接層（含 Mock 版本）
├── main.py                      # 完整流程示範
└── requirements.txt
```

## 快速開始

```bash
pip install -r requirements.txt
python3 main.py
```

會依序跑：
1. 模擬拉取 2 個活動、共數檔廣告的成效數據
2. 分群並印出群集彙總 + 優化優先順序（前10筆）
3. 對達到「不佳/難放送」門檻的廣告自動呼叫 `push_ad_action`
4. 模擬產業辨識 + 3 代受眾演化，印出每代的最佳受眾組合
5. 印出最終汰弱留強決策，並對 ENABLE/ADD_NEW/DISABLE 的標籤呼叫 `push_audience_action`

## 串接真實 Facebook / Google API

`core/platform_connectors.py` 內的 `FacebookConnector` / `GoogleAdsConnector`
已經定義好方法簽名（`fetch_ad_performance` / `fetch_audience_candidates` /
`push_ad_action` / `push_audience_action`），只需要：

- **Facebook**：安裝 `facebook_business` SDK，提供具 `ads_management` 權限的
  System User Access Token 與廣告帳戶 ID，於 `fetch_ad_performance` 內改用
  `Campaign.get_insights()` 等端點取得成效資料，並用 `AdSet.remote_update()` /
  `Ad.remote_update()` 寫回開關動作。
- **Google**：安裝 `google-ads` SDK，提供 developer token + OAuth refresh token
  與 customer ID，於 `fetch_ad_performance` 內用 GAQL（`search_stream`）查詢
  `ad_group_ad` / `campaign` 成效，並用 `CampaignCriterionService` /
  `AdGroupAdService` 寫回受眾與廣告狀態。

## 可調整的關鍵參數

| 參數 | 位置 | 說明 |
|---|---|---|
| `DEFAULT_WEIGHTS` | `clustering.py` | 廣告綜合分數的各指標權重（CTR/CVR/ROAS/CPA/轉換效率） |
| `MIN_IMPRESSIONS_FOR_SIGNIFICANCE` / `MIN_CLICKS_FOR_SIGNIFICANCE` | `metrics.py` | 判斷廣告是否已有足夠樣本可下結論 |
| `FREQUENCY_FATIGUE_THRESHOLD` | `metrics.py` | 判斷「難以放送/受眾疲乏」的頻率門檻 |
| `DEFAULT_TAG_WEIGHTS` / `mutation_rate` / `elite_ratio` | `audience_evolution.py` | 受眾評分權重、演化的突變率與菁英保留比例 |

## 注意事項

- 統計顯著性門檻是為了避免在數據量太小時就誤殺剛起步的廣告/受眾，實務上建議
  依你的平均轉換率與可接受誤差重新校準這些門檻。
- K-Means 分群數是用輪廓係數自動挑選（2~6 群），廣告數過少（少於群數下限）時
  會自動退回規則式判斷，避免分群結果失真。
- 這是一套可運作的完整程式骨架與示範資料流程；正式上線前建議加上：交易記錄與
  操作留痕（audit log）、動作執行前的人工覆核開關、以及針對「新增」動作的
  每日預算上限保護機制。
