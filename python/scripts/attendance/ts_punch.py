import os
import asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

async def punch(action="in"):
    async with async_playwright() as p:
        # ブラウザを起動 (headless=Falseにすると動きが見えます)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # ログインページへ
        print(f"Connecting to {os.getenv('TS_LOGIN_URL')}...")
        await page.goto(os.getenv('TS_LOGIN_URL'))

        # --- ここから環境に合わせたログイン処理 ---
        # 例: SSOのボタンをクリック、またはユーザー名/パスワード入力
        # await page.fill("#username", os.getenv("TS_USERNAME"))
        # await page.fill("#password", os.getenv("TS_PASSWORD"))
        # await page.click("#Login")
        
        # MFA待ちが必要な場合は、ここで一時停止させることも可能
        # await page.wait_for_timeout(30000) 

        # --- 打刻画面への移動と操作 ---
        print(f"Performing punch {action}...")
        # 勤務表タブや打刻ボタンを特定してクリック
        # if action == "in":
        #     await page.click("text=出社")
        # else:
        #     await page.click("text=退社")

        print(f"Punch {action} completed (please verify).")
        await asyncio.sleep(5)  # 結果確認のために少し待機
        await browser.close()

if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "in"
    asyncio.run(punch(action))
