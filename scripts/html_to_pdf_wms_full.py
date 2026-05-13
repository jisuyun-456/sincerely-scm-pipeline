"""
wms_issue_report_full.html → PDF
출력: C:/Users/yjisu/Desktop/wms_issue_report_full.pdf
"""

import asyncio
import io
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

import os
import time

HTML_FILE = Path(__file__).parent / "report_html" / "wms_issue_report_full.html"
OUTPUT    = Path("C:/Users/yjisu/Desktop/wms_issue_report_full.pdf")
VIEWPORT  = {"width": 794, "height": 1123}


async def render() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page    = await context.new_page()

        print(f"  loading {HTML_FILE.name} …")
        await page.goto(HTML_FILE.as_uri(), wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        png = await page.screenshot(full_page=True)
        full_img = Image.open(io.BytesIO(png)).convert("RGB")
        w, h = full_img.size
        print(f"  full screenshot: {w}x{h}px")

        PAGE_H = 1123 * 2  # device_scale_factor=2
        images = []
        y = 0
        page_num = 1
        while y < h:
            crop_h = min(PAGE_H, h - y)
            chunk = full_img.crop((0, y, w, y + crop_h))
            if chunk.size[1] < PAGE_H:
                padded = Image.new("RGB", (w, PAGE_H), (255, 255, 255))
                padded.paste(chunk, (0, 0))
                chunk = padded
            images.append(chunk)
            print(f"  page {page_num}: {chunk.size[0]}x{chunk.size[1]}")
            y += PAGE_H
            page_num += 1

        await browser.close()

    # Drop trailing pages that are mostly white (caused by fractional pixel overflow)
    def is_mostly_white(img, threshold=0.99):
        gray = img.convert("L")
        pixels = list(gray.getdata())
        white_count = sum(1 for p in pixels if p > 240)
        return white_count / len(pixels) > threshold

    while len(images) > 1 and is_mostly_white(images[-1]):
        print(f"  dropping blank trailing page")
        images.pop()

    # Save to temp file first to bypass file lock on existing output
    tmp = OUTPUT.with_name(OUTPUT.stem + ".tmp.pdf")
    if tmp.exists():
        tmp.unlink()
    print(f"\n  saving {len(images)} pages -> {tmp.name}")
    images[0].save(
        tmp,
        save_all=True,
        append_images=images[1:],
        resolution=150,
    )
    # Atomic replace; retry if user has the destination open
    for attempt in range(5):
        try:
            os.replace(str(tmp), str(OUTPUT))
            break
        except PermissionError:
            print(f"  [LOCKED] {OUTPUT.name} (PDF viewer open). Retry in 1s... ({attempt + 1}/5)")
            time.sleep(1)
    else:
        print(f"  [FAIL] Could not replace {OUTPUT}. Temp file preserved at: {tmp}")
        return
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"  done: {OUTPUT}")
    print(f"  {size_mb:.1f} MB | {len(images)} pages")


if __name__ == "__main__":
    asyncio.run(render())
