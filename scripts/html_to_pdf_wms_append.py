"""
WMS 이슈 슬라이드 6장을 렌더링 후 SCM_presentation_2026-05_v2.pdf 뒤에 합쳐
SCM_presentation_2026-05_v2_wms.pdf 로 저장.
"""

import asyncio
import io
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright
import pypdf

SLIDES_DIR = Path(__file__).parent / "slides_html"
ORIGINAL   = Path(__file__).parent.parent / "SCM_presentation_2026-05_v2.pdf"
OUTPUT     = Path(__file__).parent.parent / "SCM_presentation_2026-05_v2_wms.pdf"
TMP_WMS    = Path(__file__).parent.parent / "_wms_slides_tmp.pdf"
VIEWPORT   = {"width": 1440, "height": 900}

WMS_SLIDES = [SLIDES_DIR / f"slide_wms_{n:02d}.html" for n in range(1, 7)]


async def screenshot_slide(page, html_file: Path) -> Image.Image:
    await page.goto(html_file.as_uri(), wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1500)
    png = await page.screenshot(full_page=False)
    return Image.open(io.BytesIO(png)).convert("RGB")


async def render_wms_slides() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page    = await context.new_page()

        images = []
        for slide_file in WMS_SLIDES:
            print(f"  rendering {slide_file.name} … ", end="", flush=True)
            img = await screenshot_slide(page, slide_file)
            images.append(img)
            print(f"{img.size[0]}x{img.size[1]}")

        await browser.close()

    print(f"\nSaving WMS slides → {TMP_WMS}")
    images[0].save(
        TMP_WMS,
        save_all=True,
        append_images=images[1:],
        resolution=150,
    )
    print(f"  WMS PDF: {TMP_WMS.stat().st_size / 1_048_576:.1f} MB")


def merge_pdfs() -> None:
    writer = pypdf.PdfWriter()

    with open(ORIGINAL, "rb") as f:
        reader = pypdf.PdfReader(f)
        for page in reader.pages:
            writer.add_page(page)
    orig_pages = len(writer.pages)
    print(f"  원본 PDF: {orig_pages}페이지")

    with open(TMP_WMS, "rb") as f:
        reader = pypdf.PdfReader(f)
        for page in reader.pages:
            writer.add_page(page)
    print(f"  WMS 슬라이드: {len(writer.pages) - orig_pages}페이지 추가")

    with open(OUTPUT, "wb") as f:
        writer.write(f)

    TMP_WMS.unlink()
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n완료: {OUTPUT}  ({size_mb:.1f} MB, 총 {len(writer.pages)}페이지)")


if __name__ == "__main__":
    print("=" * 60)
    print("WMS 슬라이드 렌더링 + SCM 발표자료 합치기")
    print("=" * 60)
    asyncio.run(render_wms_slides())
    merge_pdfs()
