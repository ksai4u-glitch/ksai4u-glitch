"""Turn a photo or drawing into the ASCII portrait on the left of the card.

    python scripts/ascii_portrait.py my_photo.jpg
    python scripts/ascii_portrait.py portrait.webp --invert --gamma 2 --thicken 3 --crop-top 0

Writes ascii.txt (used on both the dark and light card), then run build_card.py.
Runs on your own PC (not in the GitHub Action). Needs Pillow:  pip install pillow

The card scales the portrait to the height of the text column automatically,
so --rows/--cols only set the detail: 52x80 (default) is fine, 26x40 is chunky.

Knobs, in the order you'd reach for them:
  --invert      background lighter than you (most photos, all drawings)
  --gamma 2     skin/mid-tones go quiet, eyes, brows, beard and outlines stand out
  --thicken 3   thin lines (drawings, glasses) survive being shrunk
  --contrast    muddy overall? raise it (1.0 = unchanged)
  --crop-top    tall photo: 0 keeps the very top, 0.5 keeps the middle
"""

import argparse
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

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
    p.add_argument("--cols", type=int, default=80, help="portrait width in characters")
    p.add_argument("--rows", type=int, default=52, help="portrait height in characters")
    p.add_argument("--invert", action="store_true", help="background is lighter than you")
    p.add_argument("--gamma", type=float, default=1.0, help="2 = only strong features show")
    p.add_argument("--thicken", type=int, default=0, help="3 = keep thin lines (pixels)")
    p.add_argument("--contrast", type=float, default=1.3, help="1.0 = unchanged")
    p.add_argument("--crop-top", type=float, default=0.15,
                   help="for tall pictures: 0 keeps the very top, 0.5 keeps the middle")
    args = p.parse_args(argv)

    img = ImageOps.exif_transpose(Image.open(args.photo)).convert("L")   # greyscale
    img = crop_to_grid(img, args.cols, args.rows, args.crop_top)
    img = thicken(img, args.thicken, args.invert)
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Contrast(img).enhance(args.contrast)

    lines = to_ascii(img, args.cols, args.rows, args.invert, args.gamma)
    (ROOT / "ascii.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"wrote ascii.txt ({args.rows} rows x {args.cols} cols)")


if __name__ == "__main__":
    main()
