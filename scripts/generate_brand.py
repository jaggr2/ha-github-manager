"""Generate the brand assets (icon/logo) for the GitHub Manager integration.

Run from the repository root:  python scripts/generate_brand.py

Design: dark GitHub-ish tile with a white "main branch" and an accent
pull-request branch — the integration manages workflows, issues and PRs.
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "custom_components" / "github_manager" / "brand"

DARK = (22, 27, 34, 255)
WHITE = (240, 246, 252, 255)
ACCENT = (137, 87, 229, 255)


def draw(size: int, with_background: bool) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw_ctx = ImageDraw.Draw(img)

    if with_background:
        margin = size * 0.05
        draw_ctx.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=size * 0.22,
            fill=DARK,
        )

    line_width = max(2, int(size * 0.055))
    radius = size * 0.085
    x_main, x_pr = size * 0.36, size * 0.66
    y_top, y_mid, y_bot = size * 0.28, size * 0.5, size * 0.72

    # main branch: straight vertical line with two nodes
    draw_ctx.line([x_main, y_top, x_main, y_bot], fill=WHITE, width=line_width)
    # PR branch: fork at the middle node, merges back at the bottom
    draw_ctx.line([x_main, y_mid, x_pr, y_mid], fill=ACCENT, width=line_width)
    draw_ctx.line([x_pr, y_mid, x_pr, y_bot], fill=ACCENT, width=line_width)

    for x, y, color in (
        (x_main, y_top, WHITE),
        (x_main, y_bot, WHITE),
        (x_pr, y_mid, ACCENT),
    ):
        draw_ctx.ellipse(
            [x - radius, y - radius, x + radius, y + radius], fill=color
        )
    return img


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    draw(256, with_background=True).save(BRAND_DIR / "icon.png")
    draw(512, with_background=False).save(BRAND_DIR / "logo.png")
    print(f"wrote {(BRAND_DIR / 'icon.png')} and {(BRAND_DIR / 'logo.png')}")


if __name__ == "__main__":
    main()
