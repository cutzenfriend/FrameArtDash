"""Turn a screenshot into a 4K "painting" and detect relevant changes."""

from __future__ import annotations

import io

import imagehash
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from frameartdash.config import Settings

HASH_SIZE = 16


def load(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGB")


def image_hash(image: Image.Image) -> str:
    return str(imagehash.phash(image, hash_size=HASH_SIZE))


def hash_distance(a: str | None, b: str | None) -> int | None:
    """Hamming distance between two stored hashes, None if not comparable."""
    if not a or not b or len(a) != len(b):
        return None
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def compose(dashboard: Image.Image, settings: Settings) -> Image.Image:
    size = settings.output_size
    canvas = _background(dashboard, settings)

    pad = settings.canvas_padding / 100
    box = (round(size[0] * (1 - 2 * pad)), round(size[1] * (1 - 2 * pad)))
    painting = ImageOps.contain(dashboard, box, Image.Resampling.LANCZOS)
    if settings.canvas_texture:
        painting = _texture(painting)
    x = (size[0] - painting.width) // 2
    y = (size[1] - painting.height) // 2

    if settings.canvas_shadow:
        _shadow(canvas, (x, y, x + painting.width, y + painting.height))
    canvas.paste(painting, (x, y))
    return canvas


def to_jpeg(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True, subsampling=0 if quality >= 90 else 2)
    return buf.getvalue()


def _background(dashboard: Image.Image, settings: Settings) -> Image.Image:
    size = settings.output_size
    if settings.style == "image":
        with Image.open(settings.bg_image) as bg:
            return ImageOps.fit(bg.convert("RGB"), size, Image.Resampling.LANCZOS)
    if settings.style == "gradient":
        return _gradient(size, *settings.bg_gradient)

    # Blur on a downscaled copy: visually identical and an order of magnitude faster.
    small = ImageOps.fit(dashboard, (size[0] // 8, size[1] // 8), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(max(settings.blur_radius / 8, 0.1)))
    small = ImageEnhance.Brightness(small).enhance(settings.blur_brightness)
    return small.resize(size, Image.Resampling.BICUBIC)


def _gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    start = ImageColor.getrgb(top)[:3]
    end = ImageColor.getrgb(bottom)[:3]
    column = Image.new("RGB", (1, 256))
    for i in range(256):
        t = i / 255
        column.putpixel((0, i), tuple(round(s + (e - s) * t) for s, e in zip(start, end, strict=True)))
    return column.resize(size, Image.Resampling.BICUBIC)


def _shadow(canvas: Image.Image, rect: tuple[int, int, int, int]) -> None:
    scale = canvas.width / 3840
    blur = max(round(40 * scale), 1)
    offset = round(18 * scale)
    mask = Image.new("L", canvas.size, 0)
    x0, y0, x1, y1 = rect
    ImageDraw.Draw(mask).rectangle((x0, y0 + offset, x1, y1 + offset), fill=150)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), mask)


def _texture(painting: Image.Image) -> Image.Image:
    """Subtle canvas grain: fine noise plus a faint woven pattern."""
    w, h = painting.size
    noise = Image.effect_noise((w, h), 24).convert("RGB")
    weave = Image.new("L", (w, h), 128)
    draw = ImageDraw.Draw(weave)
    for x in range(0, w, 3):
        draw.line((x, 0, x, h), fill=136)
    for y in range(0, h, 3):
        draw.line((0, y, w, y), fill=120)
    grain = Image.blend(noise, weave.convert("RGB"), 0.5)
    # Overlay-ish blend: brighten/darken around mid grey at low strength.
    return Image.blend(painting, Image.composite(painting, grain, Image.new("L", (w, h), 200)), 0.35)
