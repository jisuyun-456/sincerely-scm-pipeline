"""
Export the 12 final Stitch presentation slides to a single PDF.
Screenshots fetched fresh from Stitch API — ordered 01 through 11 (with 06.5).
"""

import io
import sys
from pathlib import Path

import requests
from PIL import Image

OUTPUT = Path(__file__).parent.parent / "SCM_presentation_2026-05.pdf"

# 12 slides in order: (label, screen_id, screenshot_url)
SLIDES = [
    ("01", "223a4a395fb843398e51eda3f00ecf60",
     "https://lh3.googleusercontent.com/aida/ADBb0uiTo6oJgcjqO69mpE6A13d9BZd-JjK5hm-d8Zr88gntYZ7QyU92UAes0XjYX-lQZcaTHYN2RI_43Leo4L2-3v9OGQBw0RzCl74Z1qxCECOzwmmj8D95PDpHQI_dmNo2t69zc7_X-IDKNlX6JMOYUYNpJ6jB4SNleHb-cEhajXSZi2UFAVsJhyLjJVumIr9UEHsuX1PjUaCnZbZXoo1_u6BnK0RPFUEpJKUP_t46ziSEDxyEUhyAnoox60A"),
    ("02", "35b149f6c75d4db8955a17a0e3a5fc82",
     "https://lh3.googleusercontent.com/aida/ADBb0ugY21dbnD0w2pXadH1eFt7lA4BZ7qs_6rGanobVVJnHw_9Oh7uOThV-To37BRYvfo_jQFbAtj7FUuXDDXM0tvZ2TTjQts7k7aB46nSQ_9TqSotLbtuFc98w0Du0RgPFMEeTuP0aDWKErYBxGgpDnqyIuLH11-HwkZ7qPsQegXNWWYW_FpgGRk02qpIZ6nr6xOhTxvkN4_chhvkDYAd3l_nYO-i0647G2vjLf6yQUlm1QfIyTInpV8z6Cm64"),
    ("03", "7384790180234b6195cbbaac34a52076",
     "https://lh3.googleusercontent.com/aida/ADBb0uhw-iKNo51EWuwHZUDhUeHV6xL8KAsfaSwY7N2jiHZanJiRQbmOsB-MDUpD265ieJVasbtPxsl9Rv-btksjeVXMdPnQF7CrmoVN-GLr0ZEcnZ7US2J5Y_pq0ng13i8Hy7-YSEjPoQ4P3kZ0QMU-8fYqp-OwVW9NGdtNduorOR3UbtFyEDBgSpskCSkbip2oZZ3bPHcdUQsZNU-cz7q3KP3trjKVAQN-xwt_IytoXpnI2_5yXPtOA_dgFGc"),
    ("04", "489a59c2ee65446e8499ace63a3f1d9a",
     "https://lh3.googleusercontent.com/aida/ADBb0uiH0bZkPMMmrZ_uEzdB3adgycHxv9dXzgny8rPO1RNyZkRpNSHLmr0oIQPoOkM62ACoxuyovGivpjZkhx-mI3iQoR3Wp5nKLRyNZll19Ek0A6VbnvejsRAHyj12NTency8gJwYWusluYi8UOPP-5baQ5xUUjPXA6CbPYOXkGwrkKJniHr2msWMQMUYw1uqcyTgptIR4pq6_od4zLSyl98f8FJt5Yj7k4lGzduV7h7BwXN8UaDvPWf5avi0Y"),
    ("05", "1bc3a94a102e4d04bbbb7d8dbab01630",
     "https://lh3.googleusercontent.com/aida/ADBb0uiL-vIZt-OEFcpohImnyvdoCEAsdiio95P3Yn242EOL2C13JkaieAHz8eDg8ijXgEcD9sp2__orCQGhx2t6vJuj3rN9gLwXjZP_vjC02QCfL75JuhlwKsyvU0GlmufHuNkMZLrNVZ1OpwQOs4_nakF_W8Kgm7Q-M5tD_rdPBKyAH4mUJN6ugLQOVkWgA2saDuxHtNg1abof2UllBBKGwhgOrrCuMVVjXZ0NRhL897EytgKe_6GyRT8GY-VJ"),
    ("06", "616535fbf18a4a11b59ac0d48fc4db57",
     "https://lh3.googleusercontent.com/aida/ADBb0ui-Ind-eC3vSCdUnX8AYqNyt2Msww_qXzqTF4D21vEwq7RDgMtSYEepCDUlmeSL73KUD20yGtQpIoTKSlWJyoSrR21MsniuhqqSaFVqvtjN2zUQFxvBotfuq8cLuhEzCZOhwBoAxuJN4nvQXGcGQgktth9Q_7v_TWof9W7C1Bs7ACinQzXxCh7h1iq2U_33U0cpk-XQtJa8XhgpEEnMM_TGaWu5l7vf90RHs4L-xeeCnvpLLQ-TqG4e-YU"),
    ("06.5", "baa825450c8d4a2c875d3ed070320781",
     "https://lh3.googleusercontent.com/aida/ADBb0uildTjeHtC-EJHzrFJa08EOcOFwK3FLHtHDki_FcbfE9sRnoQjhnI_Vjx73nGWZfPIyg5fwsmTPwehqs1Wf5RCZCcAjkIjafGzuCHvGw2am1Kz378MsND2ybIA09dQrUORnh91v_6hys9qXb7_nJTaYuGY6o9mRorAAAj0UAuGdpjLEpOrz11vGiUIqtJAg9ZYlYZ8Q9yd6CCnTa7edjqRDSXso7xkZLWeV7KoVL3FvpNdn1HXfV07QMBn0"),
    ("07", "6b05ce69839847cb8da5fccfc4ab164c",
     "https://lh3.googleusercontent.com/aida/ADBb0uj_cocthc134texDqOrReBg28xxPM4lcxf88Z1eVHX--1J5rDYAfL3GrhyynohmcwjP8jc2CPVBdBByw35DTmvEgG0LMwp1bwt3jhFtVc3txJbyr-wY3pfL8dXqa0Kmu9ygxBpeZ_0NHYdlGGUkNsUu2g9mHWZVRzhzCGKS2pbP0mdElc3H_DqFRHMNxgrsAPtn7uDJ7S8BSCq84mPpk8wtb3hdpZGKWL6vebaisna6xKl_R87zRSwqQVdT"),
    ("08", "3f989adee78b4e669dbd784b489888d5",
     "https://lh3.googleusercontent.com/aida/ADBb0ujPFrpSgd4KSw3MI0gVPEvnNfwJWw8PzTjYDeraTr9NnLuaFXADgPLEXnQjij_GGiBOy0pBMVvgkzTRNFrrKL9uM3nQ2XvTed5NyShq-IIgL5AMP0vzIwh0iQgvMwXV_ff3rT980JRvPIJ-ylJsTefN-xrwicFhZczZcw4RNdYX3RCUDyfRqHi4Qasz1gk2YGiw7bAiIUNGPkX57awgvIGy1hLjWMEo-BQYfvbyDlwfWwo5vWZnic6h5nI_"),
    ("09", "8055620f32364760a12887871ea58ba9",
     "https://lh3.googleusercontent.com/aida/ADBb0uj5o-j8OoVxfNfuW_IacfINr3xFHiMSOxcFxPUtde6PIuG_vwxHQJTDTREcyMwr0mjyTqM9inPzcyxN9R33J0p868MAvY83iq_KMhp7j92rGPKbrV4UEi92izEPbtE7KhliU5Ism9NSzEgh9_Km_sYYNzlIpUEyrVZsHYemQMVbPyUYX9ubAJKNuWybjolCX6bcKqVX8d_rMJp7kBlqFAxdygSEkVpyuG8fDpT80nlOP_WGghkI0kuHyg5X"),
    ("10", "89d2b047921845f09c251d1dfa9339a3",
     "https://lh3.googleusercontent.com/aida/ADBb0ugEUHMuwGqFEt1fM5pTRcC4Zsp2p4781ghUaHh5nyzym2FliveoOXROBJfTGqp-7KUU744JqzZXNU6CG5SO_kPZiKwyAI6-IXbbWD4ajaJFKvkkX8h_Uh81mJcI0dilnBLvwIZc6vmNTGtCO81tjHW52nUaVZvLPRs20fxVR6Dcr_gumyrkTRQBHs3ahDWrS7_qMOg6tuDNqP9DO4IR7Mhbn7Fw0Ej7u4Jqt9PrdAFhER05aYWFvl2zmGw"),
    ("11", "04ec2704b79b4895a3ca18374f85b2f2",
     "https://lh3.googleusercontent.com/aida/ADBb0uhollauM8VUvABQv3TbGmdhw5gouVwpd8ipfalNijKrA9yzcrDb0XNaZe7mElMxDlp-am-vGHhrpaLzIkgzePjX7qB-xOWj1pZ9bYUCLM90RD4q-mbBwHIvJf845aBDppxb8sej1i58Qv5Kca8jjcWH31a0vjP2Jn7dRcNlyCgl192QVceQ7OkpGWDckySiL7KG4xeyb0ejag9-2S3wBouTv6PoqIPx4FZfrHILa6-X4xbgzVuUg7eVzdy-"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://stitch.withgoogle.com/",
}


def download_image(url: str) -> Image.Image:
    # =s0 requests the original full-resolution image from Google CDN
    full_url = url + "=s0"
    r = requests.get(full_url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def main():
    images = []
    for label, screen_id, url in SLIDES:
        print(f"  [{label}] {screen_id[:8]}… ", end="", flush=True)
        img = download_image(url)
        images.append(img)
        print(f"{img.size[0]}x{img.size[1]}")

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
    main()
