"""Test captcha slider popup on login page."""
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    
    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
    
    print("1. Opening login page...")
    page.goto("https://anki.3mudi.com/login", wait_until="networkidle")
    time.sleep(2)
    
    # Switch to SMS tab
    print("2. Switching to SMS tab...")
    page.locator('text=验证码登录').click()
    time.sleep(1)
    
    # Click on verification code input
    print("3. Clicking verification code input...")
    code_input = page.locator('input[placeholder="请输入验证码"]')
    if code_input.count() > 0:
        code_input.first.click()
        time.sleep(3)
    
    # Check for modal
    n_modal = page.locator('.n-modal')
    print(f"4. n-modal count: {n_modal.count()}")
    
    if n_modal.count() > 0:
        print(f"   Modal visible: {n_modal.first.is_visible()}")
        modal_text = n_modal.first.inner_text()
        print(f"   Modal text: {modal_text[:200]}")
        page.screenshot(path="d:/00_dev/anki-app/test_success.png")
        print("   SUCCESS: Captcha dialog appeared!")
    else:
        print("   FAIL: No modal appeared")
        page.screenshot(path="d:/00_dev/anki-app/test_fail.png")
    
    # Check console errors
    print(f"\n5. Console errors ({len(console_errors)}):")
    for err in console_errors:
        print(f"   {err[:200]}")
    
    browser.close()
    print("\nDone!")
