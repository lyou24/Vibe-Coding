import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating to localhost:8000...")
        await page.goto("http://localhost:8000")
        
        print("Waiting for network idle...")
        await page.wait_for_load_state("networkidle")
        
        # Check buttons
        print("Checking update buttons...")
        buttons = await page.locator("button").all_inner_texts()
        print(f"Buttons found: {buttons}")
        
        # Check select options
        print("Checking select options...")
        options = await page.locator("select option").all_inner_texts()
        print(f"Select options found: {options}")
        
        # Check dialog
        print("Clicking update button to check dialog...")
        dialog_message = ""
        async def handle_dialog(dialog):
            nonlocal dialog_message
            dialog_message = dialog.message
            print(f"Dialog appeared: {dialog.message}")
            await dialog.dismiss()
            
        page.on("dialog", handle_dialog)
        
        # click the 19.0 button
        update_btns = await page.locator("button:has-text('19.0')").all()
        if update_btns:
            await update_btns[0].click()
            await page.wait_for_timeout(1000)
        
        await browser.close()
        
        return "Test Complete"

if __name__ == "__main__":
    asyncio.run(run())
