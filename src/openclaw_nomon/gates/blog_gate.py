"""
BlogGate — link liveness, image alt, optional spelling for blog content.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from openclaw_nomon.gates.base import GateResult
from openclaw_nomon.verifier import check_image_alt, check_link_liveness


_LINK_RE = re.compile(r"(?:\[[^\]]*\]\(([^)]+)\))|(<a[^>]+href=\"([^\"]+)\")")


def _read_blog_files(path: Path) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if p.is_dir():
        return [
            f
            for f in sorted(p.rglob("*"))
            if f.is_file() and f.suffix.lower() in {".md", ".html", ".htm", ".mdx"}
        ]
    return []


def _extract_links(text: str) -> List[str]:
    links = []
    for match in _LINK_RE.finditer(text):
        url = match.group(1) or match.group(3)
        if url and (url.startswith("http://") or url.startswith("https://")):
            links.append(url)
    return links


class BlogGate:
    name = "blog"

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult:
        out = Path(output_dir)
        if not out.exists():
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": f"output dir missing: {out}"},
            )

        content_root = Path(getattr(task_spec, "content_path", "")) or out
        if not content_root.is_absolute():
            candidate = out / content_root
            if candidate.exists():
                content_root = candidate
        files = _read_blog_files(content_root) or _read_blog_files(out)

        details: Dict[str, Any] = {"file_count": len(files)}
        scores: List[float] = []

        if not files:
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": "no blog files found", **details},
            )

        # Image alt check
        if getattr(task_spec, "check_image_alt", True):
            html_chunks = []
            for f in files:
                if f.suffix.lower() in {".html", ".htm"}:
                    html_chunks.append(f.read_text(encoding="utf-8", errors="replace"))
            joined = "\n".join(html_chunks)
            alt_pass = check_image_alt(joined) if joined else True
            details["image_alt"] = {"passed": alt_pass, "html_chars": len(joined)}
            scores.append(100.0 if alt_pass else 0.0)

        # Link liveness check
        if getattr(task_spec, "check_links", True):
            links: List[str] = []
            for f in files:
                links.extend(_extract_links(f.read_text(encoding="utf-8", errors="replace")))
            unique_links = list(dict.fromkeys(links))
            checked = 0
            alive = 0
            dead: List[str] = []
            for link in unique_links[:20]:  # cap to avoid hammering external hosts
                checked += 1
                if check_link_liveness(link, timeout=5):
                    alive += 1
                else:
                    dead.append(link)
            link_score = (alive / checked) * 100.0 if checked else 100.0
            details["links"] = {
                "checked": checked,
                "alive": alive,
                "dead": dead,
                "total_found": len(unique_links),
            }
            scores.append(link_score)

        # Spelling: optional, simple length-based heuristic
        if getattr(task_spec, "check_spelling", False):
            text = "\n".join(
                f.read_text(encoding="utf-8", errors="replace") for f in files
            )
            words = re.findall(r"[A-Za-z]{3,}", text)
            unique_words = set(w.lower() for w in words)
            ratio = (len(unique_words) / max(1, len(words))) * 100.0
            details["spelling"] = {
                "unique_word_ratio": ratio,
                "total_words": len(words),
            }
            scores.append(min(100.0, ratio * 2))  # crude — just flags repetition

        avg = sum(scores) / len(scores) if scores else 0.0
        passed = avg >= 70.0
        return GateResult(name=self.name, passed=passed, score=avg, details=details)
