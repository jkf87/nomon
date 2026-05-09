"""
TranslationGate — scores translation outputs by length ratio, proper-noun
preservation, and (optional) BLEU against a reference.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openclaw_gnomon.gates.base import GateResult


_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _read_text_corpus(path: Path) -> str:
    """Return concatenated text from a file or every file in a directory."""
    p = Path(path)
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    if p.is_dir():
        chunks = []
        for child in sorted(p.rglob("*")):
            if child.is_file() and child.suffix.lower() in {
                ".md",
                ".txt",
                ".rst",
                ".html",
                ".srt",
                ".json",
            }:
                chunks.append(child.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(chunks)
    return ""


def _tokenize(text: str) -> List[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text)]


def _ngrams(tokens: List[str], n: int) -> Counter:
    if len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def simple_bleu(reference: str, hypothesis: str, max_n: int = 4) -> float:
    """Lightweight BLEU implementation (no external deps)."""
    ref_tokens = _tokenize(reference)
    hyp_tokens = _tokenize(hypothesis)

    if not hyp_tokens:
        return 0.0

    precisions: List[float] = []
    for n in range(1, max_n + 1):
        ref_ngrams = _ngrams(ref_tokens, n)
        hyp_ngrams = _ngrams(hyp_tokens, n)
        if not hyp_ngrams:
            precisions.append(0.0)
            continue
        overlap = 0
        for ngram, count in hyp_ngrams.items():
            overlap += min(count, ref_ngrams.get(ngram, 0))
        precisions.append(overlap / max(1, sum(hyp_ngrams.values())))

    if min(precisions) == 0:
        # Smooth with epsilon to avoid log(0); produces a small but non-zero score
        precisions = [max(p, 1e-9) for p in precisions]

    log_avg = sum(math.log(p) for p in precisions) / len(precisions)
    geom_mean = math.exp(log_avg)

    ref_len = len(ref_tokens)
    hyp_len = len(hyp_tokens)
    if hyp_len == 0:
        bp = 0.0
    elif hyp_len > ref_len:
        bp = 1.0
    else:
        bp = math.exp(1 - ref_len / max(1, hyp_len))

    return bp * geom_mean


def _length_ratio_score(
    src_chars: int, tgt_chars: int, lo: float, hi: float
) -> Tuple[float, float]:
    if src_chars == 0:
        return 0.0, 0.0
    ratio = tgt_chars / src_chars
    if lo <= ratio <= hi:
        return 100.0, ratio
    if ratio < lo:
        deficit = (lo - ratio) / lo
    else:
        deficit = (ratio - hi) / hi
    return max(0.0, 100.0 - deficit * 100.0), ratio


def _proper_noun_score(text: str, nouns: List[str]) -> Tuple[float, List[str]]:
    if not nouns:
        return 100.0, []
    missing = [n for n in nouns if n and n not in text]
    kept = len(nouns) - len(missing)
    return (kept / len(nouns)) * 100.0, missing


class TranslationGate:
    name = "translation"

    def evaluate(self, output_dir: Path, task_spec: Any) -> GateResult:
        out = Path(output_dir)
        if not out.exists():
            return GateResult(
                name=self.name,
                passed=False,
                score=0.0,
                details={"error": f"output dir missing: {out}"},
            )

        translated = _read_text_corpus(out)
        source_path = Path(getattr(task_spec, "source_path", ""))
        source_text = _read_text_corpus(source_path) if source_path else ""

        details: Dict[str, Any] = {}
        scores: List[float] = []

        lo = float(getattr(task_spec, "length_ratio_min", 0.8))
        hi = float(getattr(task_spec, "length_ratio_max", 1.3))
        len_score, ratio = _length_ratio_score(
            len(source_text), len(translated), lo, hi
        )
        details["length_ratio"] = {"ratio": ratio, "score": len_score, "lo": lo, "hi": hi}
        scores.append(len_score)

        nouns = list(getattr(task_spec, "proper_nouns", []) or [])
        pn_score, missing = _proper_noun_score(translated, nouns)
        details["proper_nouns"] = {
            "score": pn_score,
            "expected": nouns,
            "missing": missing,
        }
        scores.append(pn_score)

        ref_path = getattr(task_spec, "reference_path", None)
        if ref_path:
            ref_text = _read_text_corpus(Path(ref_path))
            bleu = simple_bleu(ref_text, translated)
            bleu_score = bleu * 100.0
            details["bleu"] = {"score": bleu_score, "raw": bleu}
            scores.append(bleu_score)

        avg = sum(scores) / len(scores) if scores else 0.0
        passed = (
            len_score >= 70.0
            and pn_score >= 80.0
            and (("bleu" not in details) or details["bleu"]["score"] >= 20.0)
        )
        return GateResult(name=self.name, passed=passed, score=avg, details=details)
