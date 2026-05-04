#!/usr/bin/env python3
import json
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: score_gate.py <round_dir>")
        sys.exit(1)
    
    round_dir = Path(sys.argv[1])
    scores_file = round_dir / "scores.json"
    
    if not scores_file.exists():
        print(f"Error: {scores_file} not found")
        sys.exit(1)
    
    with open(scores_file) as f:
        scores = json.load(f)
    
    all_pass = True
    for dim, data in scores.items():
        score = data.get("score", 0)
        summary = data.get("summary", "")
        blockers = data.get("blockers", [])
        
        status = "PASS" if score >= 95 else "FAIL"
        if score < 95:
            all_pass = False
        
        print(f"{dim}: {score}/100 [{status}]")
        print(f"  {summary}")
        if blockers:
            for blocker in blockers:
                print(f"  - {blocker}")
    
    if all_pass:
        print("\n[PASS] All dimensions >= 95%")
        sys.exit(0)
    else:
        print("\n[FAIL] Some dimensions < 95%. Fix and re-review.")
        sys.exit(1)

if __name__ == "__main__":
    main()
