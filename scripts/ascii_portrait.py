"""Turn a photo or drawing into the ASCII portraits on the left of the card.

The card uses two portraits, because the same characters can't look right on
both backgrounds:

  ascii.txt        light card: dark parts of you = dense characters (a pencil sketch)
  ascii_dark.txt   dark card:  bright parts of you = dense characters (lit, like a photo)

If ascii_dark.txt is missing, the dark card falls back to ascii.txt.

Your current portraits were made with:

    python scripts/ascii_portrait.py portrait.webp --invert --gamma 2 --thicken 3 --contrast 1.1 --crop-top 0
    python scripts/ascii_portrait.py portrait.webp --remove-background --contrast 1.3 --crop-top 0 --out ascii_dark.txt

Runs on your own PC (not in the GitHub Action). Needs Pillow:  pip install pillow

The card scales the portrait to the height of the text column automatically,
so --rows/--cols only set the detail: 52x80 (default) is fine, 26x40 is chunky.

Knobs, in the order you'd reach for them:
  --invert             dense characters where you are DARK (use for the light card)
  --remove-background  blank out a light background so it doesn't fill with @@@
                       (use for the dark card; needs an outline or dark edge around you)
  --gamma 2            mid-tones go quiet, so eyes, brows, beard and outlines stand out
  --thicken 3          thin lines (drawings, glasses) survive being shrunk
  --contrast           muddy overall? raise it (1.0 = unchanged)
  --crop-top           tall photo: 0 keeps the very top, 0.5 keeps the middle
"""

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent

# Characters from emptiest to fullest. "Ink" (the parts of the picture that
# matter) gets the full ones; the background becomes spaces.
RAMP = " .'`:;!|il1jtfxnmwkM%W@"

# A character cell on the card is 9.7 wide x 20 tall (see build_card.py).
# The ratio is the same at any font size, so this holds when the card scales.
CELL_ASPECT = 9.7 / 20


def crop_to_grid(img, cols, rows, crop_top):
    """Crop the picture to the same shape as the character grid."""
    target = cols * CELL_ASPECT / rows          # width / height the portrait will have
    w, h = img.size
    if w / h > target:                          # too wide: trim both sides equally
        new_w = round(h * target)
        left = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))
    new_h = round(w / target)                   # too tall: trim from the top/bottom
    top = round((h - new_h) * crop_top)
    return img.crop((0, top, w, top + new_h))


def background_mask(img, threshold=200, work_width=320):
    """Find the light background by flooding in from the picture's edges.

    Works like a paint-bucket fill: start at every edge pixel that is lighter
    than `threshold` and spread to light neighbours. Your outline (or any dark
    edge around you) stops the spread, so everything inside it is kept.
    Returns a mask: 255 = you, 0 = background. Done on a small copy for speed.
    """
    small = img.resize((work_width, round(img.height * work_width / img.width)))
    w, h = small.size
    px = small.load()
    is_bg = bytearray(w * h)
    queue = deque([(x, y) for x in range(w) for y in (0, h - 1)] +
                  [(x, y) for y in range(h) for x in (0, w - 1)])
    while queue:
        x, y = queue.popleft()
        if is_bg[y * w + x] or px[x, y] <= threshold:
            continue
        is_bg[y * w + x] = 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                queue.append((nx, ny))
    mask = Image.frombytes("L", (w, h), bytes(0 if b else 255 for b in is_bg))
    return mask.resize(img.size, Image.Resampling.BILINEAR)


def thicken(img, size, invert):
    """Widen the ink before shrinking, so thin lines don't average away to grey.
    Ink is dark when inverted (MinFilter spreads dark), bright otherwise."""
    if size < 2:
        return img
    size += 1 - size % 2                        # Pillow wants an odd filter size
    return img.filter(ImageFilter.MinFilter(size) if invert else ImageFilter.MaxFilter(size))


def to_ascii(img, cols, rows, invert, gamma=1.0):
    small = img.resize((cols, rows), Image.Resampling.BOX)
    lines = []
    for y in range(rows):
        chars = []
        for x in range(cols):
            ink = small.getpixel((x, y)) / 255  # 0..1
            if invert:
                ink = 1 - ink
            ink = ink ** gamma                  # >1 pushes mid-tones towards blank
            chars.append(RAMP[round(ink * (len(RAMP) - 1))])
        lines.append("".join(chars).rstrip())
    return lines


def main(argv=None):
    p = argparse.ArgumentParser(description="Picture -> ASCII portrait for the profile card")
    p.add_argument("photo", type=Path)
    p.add_argument("--out", default="ascii.txt", help="ascii.txt (light card) or ascii_dark.txt")
    p.add_argument("--cols", type=int, default=80, help="portrait width in characters")
    p.add_argument("--rows", type=int, default=52, help="portrait height in characters")
    p.add_argument("--invert", action="store_true", help="dense characters where you are dark")
    p.add_argument("--remove-background", action="store_true",
                   help="blank out a light background (flood fill from the edges)")
    p.add_argument("--bg-threshold", type=int, default=200,
                   help="how light counts as background, 0-255 (lower it if bits of you vanish)")
    p.add_argument("--gamma", type=float, default=1.0, help="2 = only strong features show")
    p.add_argument("--thicken", type=int, default=0, help="3 = keep thin lines (pixels)")
    p.add_argument("--contrast", type=float, default=1.3, help="1.0 = unchanged")
    p.add_argument("--crop-top", type=float, default=0.15,
                   help="for tall pictures: 0 keeps the very top, 0.5 keeps the middle")
    args = p.parse_args(argv)

    img = ImageOps.exif_transpose(Image.open(args.photo)).convert("L")   # greyscale
    img = crop_to_grid(img, args.cols, args.rows, args.crop_top)
    mask = background_mask(img, args.bg_threshold) if args.remove_background else None
    img = thicken(img, args.thicken, args.invert)
    # Stretch the contrast using only your pixels, not the background's.
    img = ImageOps.autocontrast(img, cutoff=2,
                                mask=mask.point(lambda v: 255 if v > 127 else 0) if mask else None)
    img = ImageEnhance.Contrast(img).enhance(args.contrast)
    if mask:
        # Paint the background whatever shade turns into blank characters.
        blank = Image.new("L", img.size, 255 if args.invert else 0)
        img = Image.composite(img, blank, mask)

    lines = to_ascii(img, args.cols, args.rows, args.invert, args.gamma)
    (ROOT / args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote {args.out} ({args.rows} rows x {args.cols} cols)")


if __name__ == "__main__":
    main()
