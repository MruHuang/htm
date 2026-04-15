"""
GeeTest v4 滑動驗證碼自動破解
- 攔截網路請求取得原始背景圖和滑塊圖
- OpenCV Canny + matchTemplate 偵測缺口
- 模擬人類拖曳（加速→減速→過頭修正）
"""

import random
import cv2
import numpy as np
import requests
from pathlib import Path
from datetime import datetime

DEBUG_DIR = Path(__file__).parent / "tracker_data"


def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── 攔截 GeeTest 圖片 URL ────────────────────────────

def setup_image_interceptor(page) -> dict:
    """監聽網路請求，攔截 GeeTest 背景圖和滑塊圖的 URL"""
    images = {"bg": None, "slice": None}

    def on_response(response):
        url = response.url
        # GeeTest v4 圖片 URL 特徵
        if "geetest.com" in url or "gt4" in url:
            if "/bg/" in url or "bg=" in url or "_bg" in url:
                try:
                    images["bg"] = response.body()
                except Exception:
                    images["bg_url"] = url
            elif "/slice/" in url or "slice=" in url or "_slice" in url:
                try:
                    images["slice"] = response.body()
                except Exception:
                    images["slice_url"] = url

    page.on("response", on_response)
    return images


def download_image(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


# ── 缺口偵測 ─────────────────────────────────────────

def find_gap_by_template(bg_bytes: bytes, slice_bytes: bytes) -> int:
    """Canny 邊緣 + 模板匹配（最通用的方法）"""
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    piece = cv2.imdecode(np.frombuffer(slice_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    if bg is None or piece is None:
        return -1
    if piece.shape[0] >= bg.shape[0] or piece.shape[1] >= bg.shape[1]:
        return -1

    bg_edge = cv2.Canny(bg, 100, 200)
    piece_edge = cv2.Canny(piece, 100, 200)

    result = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    log(f"    模板匹配: x={max_loc[0]}, 信心={max_val:.3f}")
    return max_loc[0] if max_val > 0.05 else -1


def find_gap_by_shadow(bg_bytes: bytes) -> int:
    """陰影偵測：找背景圖中比周圍暗的集中區域"""
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if bg is None:
        return -1

    h, w = bg.shape[:2]
    hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
    v_channel = hsv[:, :, 2].astype(np.float64)

    blur = cv2.GaussianBlur(v_channel, (31, 31), 0)
    local_diff = blur - v_channel  # 正值=比周圍暗

    start_x = int(w * 0.25)
    end_x = int(w * 0.9)
    roi = local_diff[:, start_x:end_x]

    col_darkness = []
    for x in range(roi.shape[1]):
        col = roi[:, x]
        dark_pixels = col[col > 10]
        col_darkness.append(np.sum(dark_pixels) if len(dark_pixels) > 5 else 0)

    col_darkness = np.array(col_darkness, dtype=np.float64)
    if np.max(col_darkness) == 0:
        return -1

    kernel = np.ones(15) / 15
    smoothed = np.convolve(col_darkness, kernel, mode='same')

    # 找峰值的左邊緣（不是中心）
    max_idx = np.argmax(smoothed)
    half_max = smoothed[max_idx] / 2
    left = max_idx
    while left > 0 and smoothed[left] > half_max:
        left -= 1

    return left + start_x


# ── 拖曳軌跡 ─────────────────────────────────────────

def generate_track(distance: int) -> list[tuple[float, int, int]]:
    """
    模擬人類拖曳：快速加速 → 中段勻速 → 接近目標大幅放慢
    不過頭，精準停在目標位置
    """
    track = []
    current = 0

    while current < distance:
        remaining = distance - current
        progress = current / distance if distance > 0 else 1

        if progress < 0.5:
            # 前半段：快速
            step = random.uniform(6, 14)
            delay = random.randint(8, 16)
        elif progress < 0.75:
            # 中段：中速
            step = random.uniform(3, 7)
            delay = random.randint(15, 30)
        elif progress < 0.9:
            # 接近：慢速
            step = random.uniform(1.5, 4)
            delay = random.randint(30, 60)
        else:
            # 最後 10%：非常慢，精準對位
            step = random.uniform(0.5, 2)
            delay = random.randint(50, 100)

        step = min(step, remaining)
        current += step
        y = random.randint(-1, 1)
        track.append((round(current, 1), y, delay))

    # 最後停頓一下（不過頭）
    track.append((float(distance), 0, random.randint(100, 200)))

    return track


# ── 主要解題 ─────────────────────────────────────────

def solve_captcha(page, max_attempts: int = 5) -> bool:
    """自動解 GeeTest v4 滑動驗證碼"""

    for attempt in range(max_attempts):
        # 檢查有沒有驗證碼
        # 等驗證碼出現（最多 10 秒）
        has_captcha = False
        for _ in range(10):
            if page.locator("[class*='geetest_bg']").count() > 0:
                has_captcha = True
                break
            page.wait_for_timeout(1000)

        if not has_captcha:
            return True  # 沒有驗證碼 = 不需要

        log(f"自動解驗證碼 (第 {attempt + 1}/{max_attempts} 次)...")
        page.wait_for_timeout(2000)

        try:
            # ── 取得圖片 ──
            bg_el = page.locator("[class*='geetest_bg']").first
            slice_el = page.locator("[class*='geetest_slice_bg']").first
            btn_el = page.locator("[class*='geetest_btn']").first

            bg_box = bg_el.bounding_box()
            slice_box = slice_el.bounding_box()
            btn_box = btn_el.bounding_box()

            if not bg_box or not btn_box:
                log("  找不到元素")
                continue

            # 用 JS 取 CSS background-image URL，直接下載（不截圖，避免畫面閃動）
            urls = page.evaluate("""() => {
                const getUrl = (sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return null;
                    const bg = window.getComputedStyle(el).backgroundImage;
                    const m = bg.match(/url\\(['"]?(.*?)['"]?\\)/);
                    return m ? m[1] : null;
                };
                return {
                    bg: getUrl("[class*='geetest_bg']"),
                    slice: getUrl("[class*='geetest_slice_bg']")
                };
            }""")

            bg_bytes = download_image(urls.get("bg", "")) if urls.get("bg") else None
            slice_bytes = download_image(urls.get("slice", "")) if urls.get("slice") else None

            if not bg_bytes:
                log("  無法下載背景圖")
                continue

            # ── 偵測缺口 ──
            gap_x = find_gap_by_template(bg_bytes, slice_bytes)
            method = "模板匹配"

            if gap_x <= 0:
                gap_x = find_gap_by_shadow(bg_bytes)
                method = "陰影偵測"

            if gap_x <= 0:
                log("  無法偵測缺口")
                try:
                    page.locator("[class*='geetest_refresh']").first.click()
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                continue

            # ── 計算拖曳距離 ──
            bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
            img_w = bg_img.shape[1]
            scale = bg_box["width"] / img_w

            # 修正：偵測位置略偏右，微調
            slice_w = slice_box["width"] / scale if slice_box else 80
            correction = slice_w * 0.05
            real_gap = (gap_x - correction) * scale
            drag_distance = max(int(real_gap), 10)

            log(f"  [{method}] gap_x={gap_x}, scale={scale:.3f}, drag={drag_distance}px")

            # 存偵測結果
            try:
                bg_debug = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
                cv2.line(bg_debug, (gap_x, 0), (gap_x, bg_debug.shape[0]), (0, 255, 255), 2)
                cv2.imwrite(str(DEBUG_DIR / f"captcha_detect_{attempt+1}.png"), bg_debug)
            except Exception:
                pass

            # ── 拖曳 ──
            start_x = btn_box["x"] + btn_box["width"] / 2
            start_y = btn_box["y"] + btn_box["height"] / 2

            page.mouse.move(start_x, start_y)
            page.wait_for_timeout(random.randint(200, 400))
            page.mouse.down()
            page.wait_for_timeout(random.randint(100, 200))

            track = generate_track(drag_distance)
            for x_off, y_off, delay in track:
                page.mouse.move(start_x + x_off, start_y + y_off)
                page.wait_for_timeout(delay)

            page.wait_for_timeout(random.randint(100, 300))
            page.mouse.up()
            page.wait_for_timeout(3000)

            # 滑動完成，等待 GeeTest 處理
            log("  滑動完成，等待結果...")
            page.wait_for_timeout(3000)
            return True  # 不判斷通過與否，由呼叫方檢查 API 回應
            page.wait_for_timeout(2000)

        except Exception as e:
            log(f"  錯誤: {e}")
            page.wait_for_timeout(1000)

    log("自動驗證碼失敗")
    return False
