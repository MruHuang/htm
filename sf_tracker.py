"""
順豐快遞自動追蹤通知工具
- 追蹤多筆運單（從 waybills.txt 讀取）
- 只在「正在派送途中」或「已簽收」時發送 Windows 桌面通知
- 瀏覽器只開一次，驗證碼只需滑動一次
- 後續查詢在同一頁面操作，不重新載入頁面
"""

import json
import sys
import os
import time
import argparse
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from winotify import Notification, audio
from captcha_solver import solve_captcha

# 修正 Windows 終端編碼
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── 路徑 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "tracker_data"
DATA_DIR.mkdir(exist_ok=True)
WAYBILLS_FILE = BASE_DIR / "waybills.txt"
CONFIG_FILE = BASE_DIR / "config.txt"
BROWSER_DATA = DATA_DIR / "browser_profile"

TRACKING_PAGE = "https://htm.sf-express.com/tw/tc/dynamic_function/waybill/"
DEFAULT_INTERVAL = 1800

# 派送中的 opCode
DELIVERY_OPCODES = {"204", "44", "34"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}")


# ── 設定 ──────────────────────────────────────────────
def load_config() -> dict:
    config = {"interval": DEFAULT_INTERVAL}
    if not CONFIG_FILE.exists():
        return config
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if key == "interval":
                try:
                    config["interval"] = int(val)
                except ValueError:
                    pass
    return config


# ── 運單清單管理 ──────────────────────────────────────
def load_waybills() -> list[str]:
    if not WAYBILLS_FILE.exists():
        WAYBILLS_FILE.write_text(
            "# 每行一筆運單號碼，# 開頭為註解\n"
            "# 已簽收的運單會自動加上 # 註解掉\n",
            encoding="utf-8",
        )
        return []
    waybills = []
    for line in WAYBILLS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            waybills.append(line)
    return waybills


def mark_signed(waybill: str):
    if not WAYBILLS_FILE.exists():
        return
    lines = WAYBILLS_FILE.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        if line.strip() == waybill:
            new_lines.append(f"# {waybill}  # 已簽收 {now()}")
        else:
            new_lines.append(line)
    WAYBILLS_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── 狀態儲存 ──────────────────────────────────────────
def state_file(waybill: str) -> Path:
    return DATA_DIR / f"{waybill}.json"


def load_state(waybill: str) -> dict:
    f = state_file(waybill)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def save_state(waybill: str, data: dict):
    state_file(waybill).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 通知 ──────────────────────────────────────────────
def send_notification(waybill: str, message: str):
    log(f">>> 通知: [{waybill}] {message}")
    try:
        toast = Notification(
            app_id="順豐追蹤",
            title=f"順豐派送通知 {waybill}",
            msg=message[:200],
            duration="long",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        time.sleep(1)
    except Exception as e:
        log(f"[通知失敗] {e}")


# ── 核心：檢查派送狀態 ────────────────────────────────
def check_delivery(waybill: str, bill: dict) -> bool:
    route_list = bill.get("routes", [])
    status_msg = bill.get("waybillStatusMessage", "")
    is_signed = bill.get("signed", False)

    old_state = load_state(waybill)
    notified_keys = set(old_state.get("notified_times", []))

    # 只看最新一筆路由，最新狀態是派送中或已簽收才通知
    if route_list:
        latest = route_list[-1]
        op_code = latest.get("opCode", "")
        scan_time = latest.get("scanDateTime", "")
        remark = latest.get("remark", "")
        unique_key = f"{op_code}_{scan_time}"

        if op_code in DELIVERY_OPCODES and unique_key not in notified_keys:
            send_notification(waybill, remark[:200])
            notified_keys.add(unique_key)

        if (is_signed or status_msg == "已簽收") and unique_key not in notified_keys:
            send_notification(waybill, f"[已簽收] {remark[:180]}")
            notified_keys.add(unique_key)

    save_state(waybill, {
        "waybill": waybill,
        "route_count": len(route_list),
        "status": status_msg,
        "signed": is_signed,
        "last_check": now(),
        "notified_times": list(notified_keys),
        "routes": route_list,
    })

    return is_signed


# ── 查詢（每次都導航 + 自動解驗證碼）──────────────────
def do_query(page, waybills: list[str]) -> dict[str, dict]:
    """導航到追蹤頁面，自動解驗證碼，攔截 API 回應"""
    combined = ",".join(waybills)
    url = TRACKING_PAGE + f"#search/bill-number/{combined}"
    captured = []

    def on_response(response):
        if "routes" in response.url and "bills" in response.url:
            try:
                data = response.json()
                if isinstance(data, dict) and data.get("result"):
                    results = data["result"]
                    if isinstance(results, list):
                        captured.extend(results)
            except Exception:
                pass

    # 掛監聽
    page.on("response", on_response)

    # 只載入一次頁面
    log("  載入頁面...")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"  頁面載入失敗: {e}")

    # 等頁面穩定 + 驗證碼圖片載入
    page.wait_for_timeout(8000)

    # 持續滑動直到 API 回應（最多 25 次嘗試）
    for attempt in range(1, 26):
        if captured:
            break

        has_bg = page.locator("[class*='geetest_bg']").count() > 0
        if has_bg:
            log(f"  滑動 #{attempt}...")
            solve_captcha(page, max_attempts=1)

        # 等 API 回應
        for _ in range(10):
            if captured:
                break
            page.wait_for_timeout(1000)

    page.remove_listener("response", on_response)

    if captured:
        log("  取得資料！")

    result = {}
    for bill in captured:
        bill_id = bill.get("id", "")
        if bill_id:
            result[bill_id] = bill
    return result


# ── 主迴圈 ────────────────────────────────────────────
def run_tracker():
    config = load_config()
    interval = config["interval"]

    waybills = load_waybills()
    if not waybills:
        log(f"waybills.txt 是空的，請加入運單號碼: {WAYBILLS_FILE}")
        return

    print("=" * 60)
    print("  順豐快遞派送通知工具")
    print(f"  追蹤 {len(waybills)} 筆運單: {', '.join(waybills)}")
    print(f"  查詢間隔: {interval} 秒 ({interval // 60} 分鐘)")
    print(f"  只通知: 派送途中 / 已簽收")
    print()
    print("  驗證碼自動處理，瀏覽器會自動最小化")
    print("=" * 60)
    print()

    pw = sync_playwright().start()

    query_count = 0

    def one_query(waybills):
        """開瀏覽器 → 查詢 → 關瀏覽器，每次都是全新的"""
        nonlocal query_count
        query_count += 1

        # 第一次正常顯示，第二次起移到畫面外
        if query_count == 1:
            args = ["--lang=zh-TW", "--start-maximized"]
        else:
            args = ["--lang=zh-TW", "--window-position=-9999,-9999", "--window-size=800,600"]

        browser = pw.chromium.launch(
            headless=False,
            args=args,
        )
        context = browser.new_context(
            no_viewport=True,
            locale="zh-TW",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        try:
            results = do_query(page, waybills)
            return results
        finally:
            try:
                browser.close()
            except Exception:
                pass

    try:
        iteration = 0

        while True:
            config = load_config()
            interval = config["interval"]
            waybills = load_waybills()

            if not waybills:
                log("目前沒有追蹤中的運單，等待下次檢查...")
                time.sleep(interval)
                continue

            iteration += 1
            log(f"--- 第 {iteration} 次查詢 ({len(waybills)} 筆) ---")

            try:
                results = one_query(waybills)
            except Exception as e:
                log(f"查詢失敗: {e}")
                time.sleep(interval)
                continue

            if not results:
                log("未取得資料")
                time.sleep(interval)
                continue

            signed_list = []
            for wb in waybills:
                bill = results.get(wb)
                if bill:
                    route_count = len(bill.get("routes", []))
                    status = bill.get("waybillStatusMessage", "")
                    log(f"  {wb}: {status} ({route_count} 筆紀錄)")
                    if check_delivery(wb, bill):
                        signed_list.append(wb)
                else:
                    log(f"  {wb}: 查無資料")

            for wb in signed_list:
                mark_signed(wb)
                log(f"  {wb} 已簽收，從追蹤清單移除")

            remaining = [w for w in waybills if w not in signed_list]
            if not remaining:
                log("所有運單皆已簽收，追蹤結束。")
                return

            log(f"追蹤中: {len(remaining)} 筆，下次查詢: {interval} 秒後\n")
            time.sleep(interval)

    finally:
        pw.stop()


def main():
    parser = argparse.ArgumentParser(description="順豐快遞派送通知工具")
    parser.add_argument(
        "-a", "--add",
        nargs="+",
        help="新增運單號碼到追蹤清單",
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="顯示目前追蹤清單",
    )
    args = parser.parse_args()

    if args.add:
        existing = load_waybills()
        with open(WAYBILLS_FILE, "a", encoding="utf-8") as f:
            for wb in args.add:
                wb = wb.strip()
                if wb and wb not in existing:
                    f.write(f"{wb}\n")
                    print(f"  + {wb}")
                    existing.append(wb)
                else:
                    print(f"  (已存在) {wb}")
        print(f"\n目前追蹤 {len(existing)} 筆運單")
        if not args.list:
            return

    if args.list:
        waybills = load_waybills()
        if waybills:
            print(f"追蹤中 ({len(waybills)} 筆):")
            for wb in waybills:
                state = load_state(wb)
                status = state.get("status", "未查詢")
                last = state.get("last_check", "-")
                print(f"  {wb}  {status}  (上次: {last})")
        else:
            print("目前沒有追蹤中的運單")
        return

    try:
        run_tracker()
    except KeyboardInterrupt:
        print(f"\n[{now()}] 使用者中斷，結束追蹤。")


if __name__ == "__main__":
    main()
