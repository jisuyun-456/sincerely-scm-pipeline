"""
WMS 유형별 상세 내역 5페이지를 렌더링 후
scm_재고관리_이슈취합_물류팀.pdf(2페이지) 뒤에 합쳐
scm_재고관리_이슈취합_물류팀_v2.pdf(7페이지) 저장.
"""

import asyncio
import io
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright
import pypdf

REPORT_DIR = Path(__file__).parent / "report_html"
ORIGINAL   = Path("C:/Users/yjisu/Desktop/scm_재고관리_이슈취합_물류팀.pdf")
OUTPUT     = Path("C:/Users/yjisu/Desktop/scm_재고관리_이슈취합_물류팀_v2.pdf")
TMP_DETAIL = Path(__file__).parent.parent / "_wms_detail_tmp.pdf"
VIEWPORT   = {"width": 794, "height": 1123}   # A4 portrait

DETAIL_FILES = [REPORT_DIR / f"wms_detail_{n:02d}.html" for n in range(1, 6)]


async def screenshot_page(page, html_file: Path) -> Image.Image:
    await page.goto(html_file.as_uri(), wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(1500)
    png = await page.screenshot(full_page=True)
    return Image.open(io.BytesIO(png)).convert("RGB")


async def render_detail_pages() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport=VIEWPORT, device_scale_factor=2)
        page    = await context.new_page()

        images = []
        for html_file in DETAIL_FILES:
            print(f"  rendering {html_file.name} … ", end="", flush=True)
            img = await screenshot_page(page, html_file)
            images.append(img)
            print(f"{img.size[0]}x{img.size[1]}")

        await browser.close()

    print(f"\nSaving detail pages → {TMP_DETAIL}")
    images[0].save(
        TMP_DETAIL,
        save_all=True,
        append_images=images[1:],
        resolution=150,
    )
    print(f"  Detail PDF: {TMP_DETAIL.stat().st_size / 1_048_576:.1f} MB")


def merge_pdfs() -> None:
    writer = pypdf.PdfWriter()

    with open(ORIGINAL, "rb") as f:
        reader = pypdf.PdfReader(f)
        for p in reader.pages:
            writer.add_page(p)
    orig_pages = len(writer.pages)
    print(f"  원본 PDF: {orig_pages}페이지")

    with open(TMP_DETAIL, "rb") as f:
        reader = pypdf.PdfReader(f)
        for p in reader.pages:
            writer.add_page(p)
    added = len(writer.pages) - orig_pages
    print(f"  상세 내역: {added}페이지 추가")

    with open(OUTPUT, "wb") as f:
        writer.write(f)

    TMP_DETAIL.unlink()
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"\n완료: {OUTPUT}")
    print(f"  {size_mb:.1f} MB | 총 {len(writer.pages)}페이지")


if __name__ == "__main__":
    print("=" * 60)
    print("WMS 상세 내역 렌더링 + 원본 리포트 합치기")
    print("=" * 60)
    asyncio.run(render_detail_pages())
    merge_pdfs()
