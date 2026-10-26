import io

import pytest
from PIL import Image, ImageDraw

from frameartdash import compose
from frameartdash.config import Settings


def _dashboard(text: str = "21.4") -> Image.Image:
    image = Image.new("RGB", (960, 540), (30, 34, 40))
    ImageDraw.Draw(image).text((100, 100), text, fill=(255, 255, 255), font_size=200)
    return image


@pytest.mark.parametrize("style", ["blur", "gradient"])
def test_compose_output_size(style):
    s = Settings.from_env({"TARGET_URL": "http://x", "STYLE": style, "CANVAS_TEXTURE": "true"})
    out = compose.compose(_dashboard(), s)
    assert out.size == (3840, 2160)
    jpeg = compose.to_jpeg(out, 90)
    assert Image.open(io.BytesIO(jpeg)).format == "JPEG"


def test_compose_image_background(tmp_path):
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (800, 800), (200, 0, 0)).save(bg)
    s = Settings.from_env({"TARGET_URL": "http://x", "STYLE": "image", "BG_IMAGE": str(bg)})
    out = compose.compose(_dashboard(), s)
    assert out.size == (3840, 2160)
    r, g, b = out.getpixel((5, 5))
    assert r > 150 and g < 50


def test_hash_distance():
    a = compose.image_hash(_dashboard("21.4"))
    assert compose.hash_distance(a, a) == 0
    assert compose.hash_distance(None, a) is None
    b = compose.image_hash(_dashboard("88.8"))
    assert compose.hash_distance(a, b) > 0


def test_hash_ignores_old_format():
    a = compose.image_hash(_dashboard("21.4"))
    assert a.startswith("d") and len(a) == 65
    # A perceptual hash from an earlier version is not comparable: upload once.
    assert compose.hash_distance("f" * 64, a) is None


def test_hash_sees_small_number_change():
    a = compose.image_hash(_dashboard("21.4"))
    b = compose.image_hash(_dashboard("21.7"))
    assert compose.hash_distance(a, b) > 0
