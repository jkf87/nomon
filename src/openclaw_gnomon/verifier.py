"""
Gnomon verifier module — quantitative and qualitative evaluation signals.

These are building blocks for rubric.yaml evaluation items.
Each function returns True (PASS) or False (FAIL).
"""

from __future__ import annotations

import re
from typing import Optional
from pathlib import Path
import requests
from html.parser import HTMLParser


def check_font_size(html_content: str, min_pt: int = 24) -> bool:
    """Check if all text nodes have font-size >= min_pt.

    Args:
        html_content: HTML/SVG string to check
        min_pt: Minimum font size in points (default 24pt for WCAG AA compliance)

    Returns:
        True if all text is >= min_pt, False otherwise.
    """
    # Extract font-size declarations from style attributes and <style> tags
    font_sizes = re.findall(r'font-size\s*:\s*(\d+)(?:pt|px|em)?', html_content, re.IGNORECASE)
    if not font_sizes:
        # No explicit font-size found; assume browser default (12-16pt) — FAIL for safety
        return False

    for size_str in font_sizes:
        try:
            size = int(size_str)
            if size < min_pt:
                return False
        except ValueError:
            continue

    return True


def check_wcag_contrast(fg_hex: str, bg_hex: str, level: str = "AA") -> bool:
    """Check WCAG color contrast ratio.

    Args:
        fg_hex: Foreground color in hex (#RRGGBB)
        bg_hex: Background color in hex (#RRGGBB)
        level: 'AA' (4.5:1) or 'AAA' (7:1)

    Returns:
        True if contrast meets or exceeds the specified level, False otherwise.
    """
    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def relative_luminance(r: int, g: int, b: int) -> float:
        # Convert 0-255 to 0-1
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        # Apply sRGB gamma
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    try:
        fg_rgb = hex_to_rgb(fg_hex)
        bg_rgb = hex_to_rgb(bg_hex)
    except (ValueError, IndexError):
        return False

    fg_lum = relative_luminance(*fg_rgb)
    bg_lum = relative_luminance(*bg_rgb)

    lighter = max(fg_lum, bg_lum)
    darker = min(fg_lum, bg_lum)

    contrast_ratio = (lighter + 0.05) / (darker + 0.05)

    threshold = 7.0 if level == "AAA" else 4.5
    return contrast_ratio >= threshold


def check_image_alt(html_content: str) -> bool:
    """Check that all <img> tags have non-empty alt attributes.

    Args:
        html_content: HTML string to check

    Returns:
        True if all img tags have alt attributes, False otherwise.
    """
    class ImgParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.missing_alt = False

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag.lower() == 'img':
                attr_dict = dict(attrs)
                if 'alt' not in attr_dict or not attr_dict['alt'].strip():
                    self.missing_alt = True

    parser = ImgParser()
    try:
        parser.feed(html_content)
    except Exception:
        return False

    return not parser.missing_alt


def check_text_length(text: str, max_chars: int = 280) -> bool:
    """Check if text length does not exceed max_chars.

    Args:
        text: Text to check
        max_chars: Maximum allowed characters (default 280)

    Returns:
        True if len(text) <= max_chars, False otherwise.
    """
    return len(text.strip()) <= max_chars


def check_link_liveness(url: str, timeout: int = 5) -> bool:
    """Check if a URL returns a 2xx HTTP status code.

    Args:
        url: URL to check
        timeout: Request timeout in seconds (default 5)

    Returns:
        True if HEAD request returns 200-299, False otherwise.
    """
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return 200 <= response.status_code < 300
    except Exception:
        return False


def check_file_exists(file_path: str) -> bool:
    """Check if a file exists at the given path.

    Args:
        file_path: Path to check

    Returns:
        True if file exists, False otherwise.
    """
    return Path(file_path).exists()


if __name__ == "__main__":
    # Example usage
    print("Font size check (24pt minimum):", check_font_size("<p style='font-size: 24pt'>Text</p>"))
    print("WCAG AA contrast (#000 on #FFF):", check_wcag_contrast("#000000", "#FFFFFF", "AA"))
    print("Image alt check:", check_image_alt("<img src='test.jpg' alt='Test image'>"))
    print("Text length check (<=280):", check_text_length("This is a short text"))
