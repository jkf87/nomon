"""
UIGate — WCAG contrast, screenshot diff, DOM structure check for UI outputs.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openclaw_gnomon.gates.base import GateResult
from openclaw_gnomon.verifier import check_image_alt, check_wcag_contrast


_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def _read_html(target: Path) -> str:
    if target.is_file():
        return target.read_text(encoding="utf-8", errors="replace")
    if target.is_dir():
        chunks = []
        for f in sorted(target.rglob("*")):
            if f.is_file() and f.suffix.lower() in {".html", ".htm"}:
                chunks.append(f.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks)
    return ""


def _extract_dom_text(html: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", no_tags).strip()


def _color_pairs(html: str) -> List[Tuple[str, str]]:
    """Best-effort: find adjacent color/background-color declarations within the same block."""
    pairs: List[Tuple[str, str]] = []
    for block in re.findall(r"\{[^}]*\}", html):
        fg = re.search(r"(?<!background-)color\s*:\s*(#[0-9a-fA-F]{3,6})", block)
        bg = re.search(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", block)
        if fg and bg:
            pairs.append((fg.group(1), bg.group(1)))
    for style in re.findall(r"style\s*=\s*\"([^\"]+)\"", html):
        fg = re.search(r"(?<!background-)color\s*:\s*(#[0-9a-fA-F]{3,6})", style)
        bg = re.search(r"background(?:-color)?\s*:\s*(#[0-9a-fA-F]{3,6})", style)
        if fg and bg:
            pairs.append((fg.group(1), bg.group(1)))
    return pairs


def _screenshot_diff(before: Path, after: Path) -> Tuple[bool, Dict[str, Any]]:
    """Return (changed, details). Uses PIL if available; otherwise compares bytes."""
    if not before.exists() or not after.exists():
        return False, {"reason": "screenshot files missing"}

    try:
        from PIL import Image, ImageChops  # type: ignore

        img_a = Image.open(before).convert("RGB")
        img_b = Image.open(after).convert("RGB")
        if img_a.size != img_b.size:
            return True, {"size_a": img_a.size, "size_b": img_b.size, "method": "size"}
        diff = ImageChops.difference(img_a, img_b)
        bbox = diff.getbbox()
        return bool(bbox), {"bbox": bbox, "method": "PIL"}
    except Exception:
        a_bytes = before.read_bytes()
        b_bytes = after.read_bytes()
        return a_bytes != b_bytes, {"method": "byte-compare"}


class UIGate:
    name = "ui"

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult:
        out = Path(output_dir)
        if not out.exists():
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": f"output dir missing: {out}"},
            )

        target = None
        html_path = getattr(task_spec, "html_path", None)
        if html_path:
            candidate = Path(html_path)
            if not candidate.is_absolute():
                candidate = out / candidate
            target = candidate
        if target is None or not target.exists():
            target = out

        html = _read_html(target)

        details: Dict[str, Any] = {"target": str(target), "html_chars": len(html)}
        scores: List[float] = []

        level = getattr(task_spec, "wcag_level", "AA")
        pairs = _color_pairs(html)
        if pairs:
            passed_pairs = sum(1 for fg, bg in pairs if check_wcag_contrast(fg, bg, level))
            score = (passed_pairs / len(pairs)) * 100.0
            details["wcag"] = {
                "level": level,
                "checked_pairs": len(pairs),
                "passed_pairs": passed_pairs,
                "score": score,
            }
            scores.append(score)
        else:
            details["wcag"] = {"level": level, "checked_pairs": 0, "score": None}

        alt_pass = check_image_alt(html) if html else True
        details["image_alt"] = {"passed": alt_pass}
        scores.append(100.0 if alt_pass else 0.0)

        screenshot_before = getattr(task_spec, "screenshot_before", None)
        if screenshot_before:
            before = Path(screenshot_before)
            after_candidates = list(out.rglob("*.png")) + list(out.rglob("*.jpg"))
            if after_candidates:
                changed, diff_details = _screenshot_diff(before, after_candidates[0])
                details["screenshot_diff"] = {"changed": changed, **diff_details}
                scores.append(60.0 if changed else 100.0)
            else:
                details["screenshot_diff"] = {"reason": "no after-screenshot found"}

        text_chars = len(_extract_dom_text(html))
        details["dom_text_chars"] = text_chars
        if text_chars > 0:
            scores.append(100.0)

        avg = sum(scores) / len(scores) if scores else 0.0
        passed = avg >= 70.0 and alt_pass
        return GateResult(name=self.name, passed=passed, score=avg, details=details)
