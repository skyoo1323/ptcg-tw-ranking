import os
import re
import time
import requests
from playwright.sync_api import sync_playwright

# 從 GitHub Secrets 讀取敏感資訊
GAS_API_URL = os.environ.get("GAS_API_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "8888")

# Pokémon Asia 台灣官方訓練家網站積分榜網址
OFFICIAL_URL = "https://asia.pokemon-card.com/tw/archive/special/card/ranking/"

DIVISIONS = [
    {"code": "Junior", "label": "孩童組"},
    {"code": "Senior", "label": "少年組"},
    {"code": "Master", "label": "大師組"},
]

def scrape_official_rankings():
    all_players = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            locale="zh-TW"
        )
        page = context.new_page()
        print(f"正在開啟官方積分榜: {OFFICIAL_URL}")
        page.goto(OFFICIAL_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        for div in DIVISIONS:
            print(f"--- 開始抓取 {div['label']} ({div['code']}) ---")
            # 嘗試點擊對應組別頁籤
            tab = page.locator(f"text={div['label']}").first
            if tab.is_visible():
                tab.click()
                page.wait_for_timeout(2000)

            page_num = 1
            while True:
                # 讀取表格列（支援標準 table tr 或列表項目結構）
                rows = page.locator("table tbody tr").all()
                if not rows:
                    rows = page.locator(".rankingList li, .ranking-item").all()

                extracted_in_page = 0
                for row in rows:
                    text = row.inner_text().strip()
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if len(lines) < 3:
                        continue

                    # 智慧解析：尋找 PTCG ID（純數字 5~10 碼）與積分（帶有 pts 或純數字）
                    ptcg_id = ""
                    pts = 0
                    name = ""

                    for item in lines:
                        # 匹配 PTCG ID (例如 8829104 或 ID: 8829104)
                        id_match = re.search(r"(?:ID[:：\s]*)?(\d{6,10})$", item)
                        pts_match = re.search(r"(\d+)\s*(?:pts|分)?$", item, re.IGNORECASE)

                        if id_match and not ptcg_id:
                            ptcg_id = id_match.group(1)
                        elif pts_match and item != lines[0]:  # 排除第一欄名次
                            pts = int(pts_match.group(1))
                        elif not re.match(r"^#?\d+位?$", item) and not name:
                            name = item

                    if ptcg_id and name:
                        all_players.append({
                            "division": div["code"],
                            "ptcgId": ptcg_id,
                            "name": name,
                            "officialPts": pts
                        })
                        extracted_in_page += 1

                print(f"第 {page_num} 頁擷取了 {extracted_in_page} 筆資料")

                # 檢查是否有「下一頁」按鈕並可點擊
                next_btn = page.locator("a:has-text('下一頁'), button:has-text('下一頁'), .next:not(.disabled)").first
                if next_btn.is_visible() and next_btn.is_enabled():
                    next_btn.click()
                    page.wait_for_timeout(2000)
                    page_num += 1
                    if page_num > 30:  # 安全上限防止無窮迴圈
                        break
                else:
                    break

        browser.close()
    return all_players

def push_to_google_sheets(players):
    if not GAS_API_URL:
        raise ValueError("未設定 GAS_API_URL 環境變數")

    print(f"準備將共 {len(players)} 筆官方數據同步至 Google Sheets...")
    payload = {
        "action": "batch_sync",
        "password": ADMIN_PASSWORD,
        "players": players
    }
    res = requests.post(GAS_API_URL, json=payload, timeout=30)
    print("Google Sheets 回應:", res.text)

if __name__ == "__main__":
    scraped_data = scrape_official_rankings()
    if scraped_data:
        push_to_google_sheets(scraped_data)
    else:
        print("本次未擷取到資料，請確認官方網頁結構或網址是否變更。")
