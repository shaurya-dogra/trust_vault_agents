"""
TrustVault QA Agent — Playground URL Tester
Uses Playwright to quickly verify live web deployments.
"""

import asyncio

try:
    from playwright.async_api import async_playwright
    _PLAYWRIGHT_INSTALLED = True
except ImportError:
    _PLAYWRIGHT_INSTALLED = False

def check_live_url(url: str, is_mobile: bool = False, timeout_sec: int = 15) -> dict:
    """Wrapper to run async playwright synchronously for the graph."""
    if not _PLAYWRIGHT_INSTALLED:
        return {"tool_status": "tool_unavailable: playwright not installed"}
        
    return asyncio.run(_async_check_url(url, is_mobile, timeout_sec))


def check_mobile_viewport(url: str, timeout_sec: int = 15) -> dict:
    """Convenience wrapper for iPhone 12 viewport."""
    return check_live_url(url, is_mobile=True, timeout_sec=timeout_sec)


async def _async_check_url(url: str, is_mobile: bool, timeout_sec: int) -> dict:
    js_errors = []
    console_errors = []
    status = 0
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            context_args = {}
            if is_mobile:
                context_args = p.devices['iPhone 12']
                
            context = await browser.new_context(**context_args)
            page = await context.new_page()
            
            # Listeners
            page.on("pageerror", lambda err: js_errors.append(str(err)))
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                                
            response = await page.goto(url, timeout=timeout_sec * 1000, wait_until="networkidle")
            status = response.status if response else 0
            
            # Attempt a quick screenshot just to ensure rendering doesn't completely crash
            await page.screenshot(type="jpeg", quality=50)

            title = await page.title()
            
            await browser.close()
            
            return {
                "http_status": status,
                "title": title,
                "is_mobile_viewport": is_mobile,
                "js_exceptions_count": len(js_errors),
                "console_errors_count": len(console_errors),
                "errors": js_errors + console_errors,
                "tool_status": "ok"
            }
            
    except Exception as exc:
        return {
            "http_status": status,
            "error_msg": str(exc),
            "tool_status": f"error: {exc}"
        }
