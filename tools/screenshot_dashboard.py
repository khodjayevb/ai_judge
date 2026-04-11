#!/usr/bin/env python3
"""
Take screenshots of the dashboard in every tab + modal state.
Usage: python tools/screenshot_dashboard.py
Output: /tmp/dashboard_shots/*.png
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/tmp/dashboard_shots")
OUT.mkdir(parents=True, exist_ok=True)

TABS = ["eval", "compare", "redteam", "generate", "calibrate", "manage", "docs"]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
}


def shoot(theme: str = "dark"):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_name, vp in VIEWPORTS.items():
            ctx = browser.new_context(viewport=vp, device_scale_factor=1)
            page = ctx.new_page()
            page.goto("http://localhost:5000/", wait_until="networkidle")
            # Set theme via localStorage and reload
            page.evaluate(f"localStorage.setItem('theme', '{theme}')")
            page.reload(wait_until="networkidle")

            for tab in TABS:
                # Click the tab instead of calling switchTab (it relies on event.target)
                page.locator(f".tab[onclick*=\"switchTab('{tab}')\"]").first.click()
                page.wait_for_timeout(250)
                out = OUT / f"{theme}_{vp_name}_tab-{tab}.png"
                page.screenshot(path=str(out), full_page=True)
                print(f"  wrote {out}")

            # Settings modal (open from eval tab)
            page.locator(".tab[onclick*=\"switchTab('eval')\"]").first.click()
            page.wait_for_timeout(100)
            page.locator("button[onclick='toggleSettings()']").first.click()
            page.wait_for_timeout(300)
            out = OUT / f"{theme}_{vp_name}_modal-settings.png"
            page.screenshot(path=str(out), full_page=True)
            print(f"  wrote {out}")

            ctx.close()
        browser.close()


if __name__ == "__main__":
    themes = sys.argv[1:] if len(sys.argv) > 1 else ["dark"]
    for t in themes:
        print(f"Theme: {t}")
        shoot(t)
    print("Done.")
