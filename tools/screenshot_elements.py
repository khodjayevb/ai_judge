#!/usr/bin/env python3
"""
Take focused element screenshots of the dashboard — form rows, panels, modal, docs layout.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("C:/tmp/dashboard_shots/focus")
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto("http://localhost:5000/", wait_until="networkidle")

    # Header + tab bar (full viewport, top only)
    page.screenshot(path=str(OUT / "01_header_tabs.png"), clip={"x": 0, "y": 0, "width": 1600, "height": 220})
    print("wrote 01_header_tabs.png")

    # Eval panel (clip just the eval tab panel)
    panel = page.locator("#tab-eval .panel").first
    panel.screenshot(path=str(OUT / "02_eval_panel.png"))
    print("wrote 02_eval_panel.png")

    # Compare panel
    page.locator(".tab[onclick*=\"switchTab('compare')\"]").click()
    page.wait_for_timeout(150)
    page.locator("#tab-compare .panel").first.screenshot(path=str(OUT / "03_compare_panel.png"))
    print("wrote 03_compare_panel.png")

    # Red team
    page.locator(".tab[onclick*=\"switchTab('redteam')\"]").click()
    page.wait_for_timeout(150)
    page.locator("#tab-redteam .panel").first.screenshot(path=str(OUT / "04_redteam_panel.png"))
    print("wrote 04_redteam_panel.png")

    # Generate
    page.locator(".tab[onclick*=\"switchTab('generate')\"]").click()
    page.wait_for_timeout(150)
    page.locator("#tab-generate .panel").first.screenshot(path=str(OUT / "05_generate_panel.png"))
    print("wrote 05_generate_panel.png")

    # Calibrate
    page.locator(".tab[onclick*=\"switchTab('calibrate')\"]").click()
    page.wait_for_timeout(150)
    page.locator("#tab-calibrate .panel").first.screenshot(path=str(OUT / "06_calibrate_panel.png"))
    print("wrote 06_calibrate_panel.png")

    # Manage
    page.locator(".tab[onclick*=\"switchTab('manage')\"]").click()
    page.wait_for_timeout(150)
    page.locator("#tab-manage .panel").first.screenshot(path=str(OUT / "07_manage_panel.png"))
    print("wrote 07_manage_panel.png")

    # Docs — full layout (we expect 220 sidebar + content)
    page.locator(".tab[onclick*=\"switchTab('docs')\"]").click()
    page.wait_for_timeout(200)
    # Scroll to top of docs first
    page.evaluate("window.scrollTo(0, 0)")
    # Viewport shot to see the docs layout as the user sees it
    page.screenshot(path=str(OUT / "08_docs_viewport.png"), full_page=False)
    print("wrote 08_docs_viewport.png")
    # And the docs-layout element specifically
    try:
        page.locator(".docs-layout").first.screenshot(path=str(OUT / "08b_docs_layout_elem.png"))
        print("wrote 08b_docs_layout_elem.png")
    except Exception as e:
        print("docs-layout not found:", e)

    # Settings modal
    page.locator(".tab[onclick*=\"switchTab('eval')\"]").click()
    page.wait_for_timeout(100)
    page.locator("button[onclick='toggleSettings()']").first.click()
    page.wait_for_timeout(300)
    page.locator(".modal-content").first.screenshot(path=str(OUT / "09_settings_modal.png"))
    print("wrote 09_settings_modal.png")

    browser.close()
    print("Done.")
