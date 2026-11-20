"""The assistant's analysis file is the write-up, byte for byte."""

from __future__ import annotations

from pathlib import Path


def test_analysis_matches_the_writeup():
    root = Path(__file__).resolve().parents[2]
    writeup = (root / "writeups" / "pricing-summary.md").read_bytes()
    analysis = (root / "lorehaven_sim" / "knowledge" / "analysis.md").read_bytes()
    assert analysis == writeup
