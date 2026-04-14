"""
GeeTest v4 滑動驗證碼自動破解 - 通用獨立版本
適用於任何使用 GeeTest v4 滑動驗證碼的網站

使用方式:

    1. 當作模組引用:

        from playwright.sync_api import sync_playwright
        from geetest_slider import GeeTestSlider

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=False)
        page = browser.new_context().new_page()
        page.goto("https://some-website-with-geetest.com")

        solver = GeeTestSlider(page)
        success = solver.solve()  # 自動偵測 + 滑動，回傳 True/False

        browser.close()
        pw.stop()

    2. 命令列直接測試:

        python geetest_slider.py https://some-website-with-geetest.com

依賴: pip install playwright opencv-python-headless numpy requests
"""

import random
import sys
import cv2
import numpy as np
import requests
from datetime import datetime


def _log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


class GeeTestSlider:
    """
    GeeTest v4 滑動驗證碼自動破解

    參數:
        page: Playwright Page 物件
        correction: 拖曳距離修正比例（正值=往左修正，負值=往右）
                    預設 0.05 = 拼圖寬度的 5%
        debug: 是否儲存偵測結果圖片
        debug_dir: debug 圖片儲存目錄
    """

    # GeeTest v4 CSS 選擇器
    SEL_BG = "[class*='geetest_bg']"
    SEL_SLICE = "[class*='geetest_slice_bg']"
    SEL_BTN = "[class*='geetest_btn']"
    SEL_REFRESH = "[class*='geetest_refresh']"

    def __init__(self, page, correction=0.05, debug=False, debug_dir=None):
        self.page = page
        self.correction = correction
        self.debug = debug
        self.debug_dir = debug_dir

    # ── 公開方法 ──────────────────────────────────────

    def solve(self, max_attempts=5, wait_captcha_sec=10) -> bool:
        """
        自動偵測並解 GeeTest 滑動驗證碼

        參數:
            max_attempts: 最多嘗試幾次滑動
            wait_captcha_sec: 等驗證碼出現的最長秒數

        回傳:
            True = 已完成滑動（不保證通過，由呼叫方檢查業務結果）
            False = 完全失敗（找不到元素等）
        """
        for attempt in range(max_attempts):
            # 等驗證碼出現
            if not self._wait_for_captcha(wait_captcha_sec):
                _log("未偵測到驗證碼")
                return True  # 沒有驗證碼 = 不需要解

            _log(f"滑動嘗試 ({attempt + 1}/{max_attempts})...")
            self.page.wait_for_timeout(1500)

            try:
                success = self._do_slide()
                if success:
                    _log("滑動完成")
                    self.page.wait_for_timeout(3000)
                    return True
            except Exception as e:
                _log(f"  錯誤: {e}")

            self.page.wait_for_timeout(2000)

        _log("所有嘗試均失敗")
        return False

    def is_captcha_visible(self) -> bool:
        """檢查 GeeTest 驗證碼是否可見"""
        return self.page.locator(self.SEL_BG).count() > 0

    # ── 內部方法 ──────────────────────────────────────

    def _wait_for_captcha(self, timeout_sec: int) -> bool:
        """等驗證碼面板出現"""
        for _ in range(timeout_sec):
            if self.is_captcha_visible():
                return True
            self.page.wait_for_timeout(1000)
        return False

    def _get_images(self) -> tuple:
        """用 JS 取 CSS background-image URL 下載圖片（不截圖，避免畫面閃動）"""
        urls = self.page.evaluate("""() => {
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

        bg_bytes = self._download(urls.get("bg")) if urls.get("bg") else None
        slice_bytes = self._download(urls.get("slice")) if urls.get("slice") else None
        return bg_bytes, slice_bytes

    def _download(self, url: str) -> bytes | None:
        if not url:
            return None
        try:
            r = requests.get(url, timeout=10)
            return r.content if r.status_code == 200 else None
        except Exception:
            return None

    def _find_gap(self, bg_bytes: bytes, slice_bytes: bytes = None) -> int:
        """多策略偵測缺口 x 座標，回傳 -1 表示失敗"""
        # 策略 1: 模板匹配（需要背景圖 + 滑塊圖）
        if slice_bytes:
            x = self._find_by_template(bg_bytes, slice_bytes)
            if x > 0:
                _log(f"  [模板匹配] gap_x={x}")
                return x

        # 策略 2: 陰影偵測（只需要背景圖）
        x = self._find_by_shadow(bg_bytes)
        if x > 0:
            _log(f"  [陰影偵測] gap_x={x}")
            return x

        return -1

    def _find_by_template(self, bg_bytes: bytes, slice_bytes: bytes) -> int:
        """Canny 邊緣 + 模板匹配"""
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
        _log(f"    匹配信心: {max_val:.3f}")
        return max_loc[0] if max_val > 0.05 else -1

    def _find_by_shadow(self, bg_bytes: bytes) -> int:
        """在背景圖中找比周圍暗的集中區域（缺口陰影）"""
        bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
        if bg is None:
            return -1

        h, w = bg.shape[:2]
        hsv = cv2.cvtColor(bg, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2].astype(np.float64)

        blur = cv2.GaussianBlur(v, (31, 31), 0)
        diff = blur - v

        start_x = int(w * 0.25)
        end_x = int(w * 0.9)
        roi = diff[:, start_x:end_x]

        darkness = []
        for x in range(roi.shape[1]):
            col = roi[:, x]
            dark = col[col > 10]
            darkness.append(np.sum(dark) if len(dark) > 5 else 0)

        darkness = np.array(darkness, dtype=np.float64)
        if np.max(darkness) == 0:
            return -1

        smoothed = np.convolve(darkness, np.ones(15) / 15, mode='same')
        max_idx = np.argmax(smoothed)
        half_max = smoothed[max_idx] / 2
        left = max_idx
        while left > 0 and smoothed[left] > half_max:
            left -= 1

        return left + start_x

    def _calc_drag_distance(self, gap_x: int, bg_bytes: bytes,
                            bg_box: dict, slice_box: dict) -> int:
        """計算實際螢幕上的拖曳像素數"""
        bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
        img_w = bg_img.shape[1]
        scale = bg_box["width"] / img_w

        slice_w = slice_box["width"] / scale if slice_box else 80
        corrected = gap_x - slice_w * self.correction
        return max(int(corrected * scale), 10)

    def _generate_track(self, distance: int) -> list[tuple[float, int, int]]:
        """模擬人類拖曳軌跡：加速 → 勻速 → 慢速精準停"""
        track = []
        current = 0

        while current < distance:
            progress = current / distance if distance > 0 else 1

            if progress < 0.5:
                step = random.uniform(6, 14)
                delay = random.randint(8, 16)
            elif progress < 0.75:
                step = random.uniform(3, 7)
                delay = random.randint(15, 30)
            elif progress < 0.9:
                step = random.uniform(1.5, 4)
                delay = random.randint(30, 60)
            else:
                step = random.uniform(0.5, 2)
                delay = random.randint(50, 100)

            step = min(step, distance - current)
            current += step
            track.append((round(current, 1), random.randint(-1, 1), delay))

        track.append((float(distance), 0, random.randint(100, 200)))
        return track

    def _do_slide(self) -> bool:
        """執行一次完整的偵測 + 拖曳"""
        page = self.page

        # 取得元素位置
        bg_el = page.locator(self.SEL_BG).first
        btn_el = page.locator(self.SEL_BTN).first

        bg_box = bg_el.bounding_box()
        btn_box = btn_el.bounding_box()
        if not bg_box or not btn_box:
            _log("  找不到背景圖或滑塊按鈕")
            return False

        slice_box = None
        try:
            sl = page.locator(self.SEL_SLICE).first
            slice_box = sl.bounding_box()
        except Exception:
            pass

        # 下載圖片
        bg_bytes, slice_bytes = self._get_images()
        if not bg_bytes:
            _log("  無法取得背景圖")
            return False

        # 偵測缺口
        gap_x = self._find_gap(bg_bytes, slice_bytes)
        if gap_x <= 0:
            _log("  無法偵測缺口位置")
            self._try_refresh()
            return False

        # 計算拖曳距離
        drag = self._calc_drag_distance(gap_x, bg_bytes, bg_box, slice_box)
        _log(f"  拖曳距離: {drag}px")

        # 儲存 debug 圖
        if self.debug and self.debug_dir:
            try:
                img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
                cv2.line(img, (gap_x, 0), (gap_x, img.shape[0]), (0, 255, 255), 2)
                from pathlib import Path
                Path(self.debug_dir).mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(Path(self.debug_dir) / "geetest_detect.png"), img)
            except Exception:
                pass

        # 執行拖曳
        sx = btn_box["x"] + btn_box["width"] / 2
        sy = btn_box["y"] + btn_box["height"] / 2

        page.mouse.move(sx, sy)
        page.wait_for_timeout(random.randint(200, 400))
        page.mouse.down()
        page.wait_for_timeout(random.randint(100, 200))

        for x_off, y_off, delay in self._generate_track(drag):
            page.mouse.move(sx + x_off, sy + y_off)
            page.wait_for_timeout(delay)

        page.wait_for_timeout(random.randint(100, 300))
        page.mouse.up()
        return True

    def _try_refresh(self):
        """點重新整理按鈕換一張圖"""
        try:
            btn = self.page.locator(self.SEL_REFRESH).first
            if btn.count() > 0:
                btn.click()
                self.page.wait_for_timeout(2000)
        except Exception:
            pass


# ── 命令列測試 ────────────────────────────────────────

def main():
    """
    命令列用法:
        python geetest_slider.py <url> [--attempts 5] [--correction 0.05] [--debug]
    """
    import argparse
    from playwright.sync_api import sync_playwright

    parser = argparse.ArgumentParser(description="GeeTest v4 Slider Solver")
    parser.add_argument("url", help="Target URL with GeeTest captcha")
    parser.add_argument("--attempts", type=int, default=10, help="Max slide attempts (default 10)")
    parser.add_argument("--correction", type=float, default=0.05, help="Drag correction ratio (default 0.05)")
    parser.add_argument("--debug", action="store_true", help="Save detection result images")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=args.headless,
        args=["--lang=zh-TW", "--start-maximized"],
    )
    page = browser.new_context(no_viewport=True, locale="zh-TW").new_page()

    _log(f"Opening {args.url}")
    page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(8000)

    solver = GeeTestSlider(
        page,
        correction=args.correction,
        debug=args.debug,
        debug_dir=".",
    )

    _log("Starting captcha solver...")
    for i in range(args.attempts):
        if not solver.is_captcha_visible():
            _log("No captcha detected - done!")
            break
        _log(f"--- Attempt {i + 1}/{args.attempts} ---")
        solver.solve(max_attempts=1)
        page.wait_for_timeout(3000)

    _log("Keeping browser open for 30 seconds...")
    page.wait_for_timeout(30000)

    browser.close()
    pw.stop()
    _log("Done")


if __name__ == "__main__":
    main()
