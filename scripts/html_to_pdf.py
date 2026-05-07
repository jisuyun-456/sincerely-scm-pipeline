"""
Render 11 HTML slide files to a single PDF using Playwright.
Each slide is captured at 1440x900 (16:9-ish) then combined with Pillow.
"""

import asyncio
import io
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

SLIDES_DIR = Path(__file__).parent / "slides_html"
OUTPUT = Path(__file__).parent.parent / "SCM_presentation_2026-05_v2.pdf"
VIEWPORT = {"width": 1440, "height": 900}

SLIDE_FILES = (
    [SLIDES_DIR / f"slide_{n:02d}.html" for n in range(1, 7)]
    + [SLIDES_DIR / "slide_06_5.html"]
    + [SLIDES_DIR / f"slide_{n:02d}.html" for n in range(7, 12)]
)


async def screenshot_slide(page, html_file: Path) -> Image.Image:
    await page.goto(html_file.as_uri(), wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1500)  # let fonts/tailwind finish rendering
    png = await page.screenshot(full_page=False)
    return Image.open(io.BytesIO(png)).convert("RGB")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page = await context.new_page()

        images = []
        for slide_file in SLIDE_FILES:
            print(f"  rendering {slide_file.name} … ", end="", flush=True)
            img = await screenshot_slide(page, slide_file)
            images.append(img)
            print(f"{img.size[0]}x{img.size[1]}")

        await browser.close()

    print(f"\nSaving {len(images)}-page PDF → {OUTPUT}")
    images[0].save(
        OUTPUT,
        save_all=True,
        append_images=images[1:],
        resolution=150,
    )
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"Done. {size_mb:.1f} MB")


if __name__ == "__main__":
    asyncio.run(main())
