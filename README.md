# SF Express Tracker - 順豐快遞自動追蹤通知工具

自動追蹤順豐快遞運單狀態，包裹派送時發送 Windows 桌面通知。
內建 GeeTest v4 滑動驗證碼自動破解，全程無需手動操作。

---

## 快速開始

### 1. 安裝

雙擊 `install.bat`，自動安裝所有需要的東西：
- Python 3.11（如果電腦沒裝過）
- 所有 Python 套件
- Chromium 瀏覽器（給自動化用，不影響你的 Chrome）

> 如果是第一次安裝 Python，安裝完會提示你**關閉視窗再跑一次** install.bat。

### 2. 設定運單號碼

編輯 `waybills.txt`，每行一筆運單號碼：

```
SF1571837085485
SF1572950809952
SF0217110419688
```

- `#` 開頭的行會被忽略（註解）
- 已簽收的運單會自動加上 `#` 註解掉
- 程式執行中隨時可以編輯，下次查詢會自動讀取新的

### 3. 啟動追蹤

雙擊 `start.bat`。

程式會：
1. 開啟 Chromium 瀏覽器
2. 自動破解驗證碼
3. 查詢所有運單狀態
4. 在背景持續輪詢

### 4. 收到通知

當運單出現以下狀態時，會跳 Windows 桌面通知：

| 狀態 | 說明 |
|------|------|
| **派送途中** | 快件交給快遞員，正在配送 |
| **已簽收** | 包裹已送達簽收 |

其他狀態（收件、分揀、轉運、清關等）不會通知。

---

## 設定說明

### config.txt

```
# 查詢間隔（秒），預設 1800 = 30 分鐘
interval=1800
```

常用設定：
- `interval=600` → 每 10 分鐘查一次
- `interval=1800` → 每 30 分鐘查一次（預設）
- `interval=3600` → 每 1 小時查一次

> 注意：SF Express 限制同一運單每天最多查 5 次，不要設太短。

### waybills.txt

```
# 這是註解，不會被處理
SF1571837085485
SF0217110419688
# SF1572950809952  # 已簽收 2026-04-13 17:24:00
```

- 每行一筆運單號碼
- `#` 開頭 = 註解（忽略）
- 已簽收的運單會自動被程式加上 `#`
- 支援同時追蹤多筆（一次查詢最多 20 筆）
- 執行中可隨時編輯，不用重啟程式

---

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `install.bat` | 一鍵安裝（Python + 套件 + 瀏覽器）|
| `start.bat` | 啟動追蹤程式 |
| `sf_tracker.py` | 主程式 |
| `captcha_solver.py` | 驗證碼破解（SF Express 專用）|
| `geetest_slider.py` | GeeTest v4 滑動驗證碼破解（通用版）|
| `config.txt` | 查詢間隔設定 |
| `waybills.txt` | 運單號碼清單 |
| `tracker_data/` | 程式自動建立，存放查詢紀錄 |

---

## GeeTest Slider 通用版使用說明

`geetest_slider.py` 是獨立的 GeeTest v4 滑動驗證碼破解工具，可用在任何使用 GeeTest v4 的網站。

### 命令列用法

```bash
# 基本用法：開啟網頁並自動破解驗證碼
python geetest_slider.py https://目標網站.com

# 指定嘗試次數
python geetest_slider.py https://目標網站.com --attempts 15

# 調整拖曳精準度（預設 0.05，數字越大拼圖越往左）
python geetest_slider.py https://目標網站.com --correction 0.08

# 儲存偵測結果圖片（debug 用）
python geetest_slider.py https://目標網站.com --debug

# 無頭模式（不顯示瀏覽器）
python geetest_slider.py https://目標網站.com --headless

# 組合使用
python geetest_slider.py https://目標網站.com --attempts 20 --correction 0.03 --debug
```

### 嵌入你的程式

```python
from playwright.sync_api import sync_playwright
from geetest_slider import GeeTestSlider

# 開啟瀏覽器
pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False)
page = browser.new_context().new_page()

# 導航到目標網頁
page.goto("https://目標網站.com")

# 建立 solver
solver = GeeTestSlider(page)

# 自動解驗證碼（最多嘗試 5 次）
solver.solve()

# 或者自訂參數
solver = GeeTestSlider(
    page,
    correction=0.05,     # 拖曳修正比例，微調用
    debug=True,          # 儲存偵測結果圖片
    debug_dir="./debug"  # 圖片存放目錄
)
solver.solve(max_attempts=10, wait_captcha_sec=15)

# 檢查驗證碼是否還在（判斷是否通過）
if not solver.is_captcha_visible():
    print("驗證碼已通過！")

# 持續嘗試直到業務結果出現
my_data = None
for i in range(20):
    if my_data:
        break
    solver.solve(max_attempts=1)
    page.wait_for_timeout(5000)
    # 檢查你的業務邏輯...
    # my_data = check_my_result()

browser.close()
pw.stop()
```

### GeeTestSlider 參數說明

| 參數 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `page` | Page | (必填) | Playwright Page 物件 |
| `correction` | float | 0.05 | 拖曳修正比例。正值=往左修正，負值=往右。從 0.05 開始，如果拼圖偏右就加大，偏左就減小 |
| `debug` | bool | False | 是否儲存偵測結果圖片 |
| `debug_dir` | str | None | debug 圖片存放路徑 |

### solve() 參數說明

| 參數 | 類型 | 預設 | 說明 |
|------|------|------|------|
| `max_attempts` | int | 5 | 最多滑動幾次 |
| `wait_captcha_sec` | int | 10 | 等驗證碼出現的秒數 |

### 精準度調校

如果滑動位置不準：

1. 加上 `--debug` 看偵測結果圖片（黃線 = 偵測位置）
2. 拼圖停太右邊 → 加大 `correction`（例如 0.08）
3. 拼圖停太左邊 → 減小 `correction`（例如 0.02 或 0）
4. 每個網站的 GeeTest 實作可能略有不同，需要微調

### 注意事項

- 不保證 100% 成功率，GeeTest 會持續更新偵測機制
- 建議搭配重試機制使用
- 不要用 `element.screenshot()` 取驗證碼圖片，會造成畫面閃動
- 驗證碼是否真正通過，需由呼叫方檢查業務結果（例如 API 回應），不能只看驗證碼面板是否消失

---

## 常見問題

### install.bat 執行失敗

**Python was not found**
→ install.bat 會自動下載安裝 Python。安裝完後關閉視窗，再跑一次 install.bat。

**Download failed**
→ 網路問題。手動到 https://www.python.org/downloads/ 下載安裝。
→ 安裝時務必勾選 **Add Python to PATH**。

### 驗證碼一直失敗

- 檢查網路是否正常
- 嘗試調整 `correction` 參數
- 加上 `--debug` 看偵測結果是否正確
- GeeTest 可能更新了，偵測演算法需要調整

### 沒有收到通知

- 檢查 Windows 通知設定是否開啟
- 確認 waybills.txt 裡有正確的運單號碼
- 運單可能還在運送中，尚未進入派送階段

### 程式關閉後瀏覽器還在

- 正常情況下程式會自動關閉瀏覽器
- 如果異常關閉，手動關掉 Chromium 視窗即可
- 不會影響你正在使用的 Chrome 瀏覽器

---

## 技術架構

```
start.bat
  └─ sf_tracker.py（主程式）
       ├─ captcha_solver.py（驗證碼破解）
       │    └─ OpenCV: Canny 邊緣偵測 + 模板匹配
       │    └─ Playwright: 模擬人類拖曳
       ├─ Playwright: 瀏覽器自動化、API 回應攔截
       ├─ winotify: Windows 桌面通知
       └─ config.txt / waybills.txt（設定檔）
```

### 依賴套件

| 套件 | 用途 |
|------|------|
| playwright | 瀏覽器自動化 |
| winotify | Windows 桌面通知 |
| opencv-python-headless | 驗證碼圖片分析 |
| numpy | 數值計算 |
| requests | HTTP 下載圖片 |
