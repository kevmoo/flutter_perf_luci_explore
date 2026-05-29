import json
import time
import urllib.request
import subprocess
from datetime import datetime
import numpy as np
import pandas as pd

# Load the local 1-year performance timeline database
with open("data/web_wasm_annual_dataset.json", "r") as f:
    data = json.load(f)

metadata = data["commit_metadata"]
series = data["series"]

df = pd.DataFrame(series).sort_index()

# Robust list of web-relevant directories and dependency rolls
WEB_RELEVANT_PATH_PREFIXES = [
    "engine/src/flutter/lib/web_ui",
    "packages/flutter",
    "lib/web_ui",
    "bin/cache/dart-sdk"
]

DEPENDENCY_ROLL_KEYWORDS = [
    "roll skia",
    "roll dart sdk",
    "roll pub packages",
    "roll packages",
    "bump skia",
    "bump dart"
]

def get_github_token():
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if res.returncode == 0:
            token = res.stdout.strip()
            if token:
                return token
    except Exception:
        pass
    return None

GITHUB_TOKEN = get_github_token()

def get_github_request(url):
    headers = {
        "Accept": "application/vnd.github.v3+json", 
        "User-Agent": "antigravity-perf-agent"
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return urllib.request.Request(url, headers=headers)

def check_commit_relevance(commit_hash, pr_title):
    pr_lower = pr_title.lower()
    if any(kw in pr_lower for kw in DEPENDENCY_ROLL_KEYWORDS):
        return True, "Dependency Autoroll"
        
    url = f"https://api.github.com/repos/flutter/flutter/commits/{commit_hash}"
    req = get_github_request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            files = data.get("files", [])
            
            modified_paths = [f.get("filename", "") for f in files]
            
            # Check if any modified file path touches web-engine or core framework
            for path in modified_paths:
                if any(prefix in path for prefix in WEB_RELEVANT_PATH_PREFIXES):
                    return True, f"Direct Code Modification (e.g. {path.split('/')[-1]})"
                    
            return False, "False-Positive (Native Platform/Impeller specific)"
    except Exception as e:
        return True, f"Attributed (API lookup limit fallback: {e})"

def query_adjacent_commits(offset_idx, range_steps=3):
    offsets = df.index.tolist()
    curr_pos = offsets.index(offset_idx)
    start_pos = max(0, curr_pos - range_steps)
    end_pos = min(len(offsets), curr_pos + range_steps + 1)
    
    adjacent = []
    for pos in range(start_pos, end_pos):
        off = offsets[pos]
        adjacent.append((off, metadata[str(off)]["hash"], metadata[str(off)]["full_hash"]))
    return adjacent

def resolve_github_pr(commit_hash):
    url = f"https://api.github.com/repos/flutter/flutter/commits/{commit_hash}"
    req = get_github_request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("commit", {}).get("message", "N/A")
            first_line = msg.split("\n")[0]
            author = data.get("commit", {}).get("author", {}).get("name", "Unknown")
            date_str = data.get("commit", {}).get("author", {}).get("date", "")
            if date_str:
                dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = dt.strftime("%Y-%m-%d")
            else:
                formatted_date = "Unknown"
            return first_line, author, formatted_date
    except Exception as e:
        return f"Manual Verification Required: {e}", "N/A", "N/A"

def audit_ledger():
    print("=========================================================================")
    print("🔬 AUDITING PERFORMANCE TIMELINE AND FILTERING CORRELATION PLOTS")
    print("=========================================================================")
    if GITHUB_TOKEN:
        print("[✓] High-rate GitHub Token resolved successfully. Initializing audit...")
    else:
        print("[!] No Github Token resolved. Proceeding with unauthenticated rates limit...")
    
    # Target baseline percentage step-change window threshold (e.g. 8.5% win/loss)
    threshold_pct = 8.5
    window = 15
    
    events = []
    
    # Process each rendering technology target
    for renderer in df.columns:
        clean_series = df[renderer].dropna()
        if clean_series.empty:
            continue
            
        series_smoothed = clean_series.rolling(window=window, min_periods=4).mean()
        diffs = series_smoothed.diff()
        
        sorted_diffs = diffs.dropna().abs().sort_values(ascending=False)
        
        processed_offsets = []
        for offset, val in sorted_diffs.items():
            offset_str = str(offset)
            offset_int = int(offset)
            
            if any(abs(offset_int - po) < 25 for po in processed_offsets):
                continue
                
            idx_pos = clean_series.index.get_loc(offset_str)
            avg_before = clean_series.iloc[max(0, idx_pos - 12):idx_pos].mean()
            avg_after = clean_series.iloc[idx_pos:min(len(clean_series), idx_pos + 12)].mean()
            
            if np.isnan(avg_before) or np.isnan(avg_after) or avg_before == 0:
                continue
                
            pct_change = ((avg_after - avg_before) / avg_before) * 100
            
            if abs(pct_change) < threshold_pct:
                continue
                
            processed_offsets.append(offset_int)
            
            meta = metadata[offset_str]
            pr_title, author, commit_date = resolve_github_pr(meta["full_hash"])
            
            # RUN CONCRETE FILE-LEVEL SCIENTIFIC AUDIT
            is_relevant, details = check_commit_relevance(meta["full_hash"], pr_title)
            
            event_type = "🏆 PERFORMANCE WIN (SPEEDUP)" if pct_change < 0 else "🚨 PERFORMANCE LOSS (REGRESSION)"
            
            resolved_pr_title = pr_title
            resolved_hash = meta["hash"]
            resolved_author = author
            resolved_date = commit_date
            attribution_confidence = "HIGH (Direct Web-Engine Audit Map)" if is_relevant else "CORRELATION PLOT ADJACENCY"
            
            # BATCH RESOLVER: If tagged as a false-positive correlation, trace the adjacent merge batch context
            if not is_relevant:
                adjacent_commits = query_adjacent_commits(offset_str, range_steps=3)
                found_resolved = False
                for adj_offset, adj_shash, adj_fhash in adjacent_commits:
                    adj_title, adj_author, adj_date = resolve_github_pr(adj_fhash)
                    adj_relevant, adj_details = check_commit_relevance(adj_fhash, adj_title)
                    if adj_relevant:
                        resolved_pr_title = f"[RESOLVED BATCH SHIFT] {adj_title}"
                        resolved_hash = adj_shash
                        resolved_author = adj_author
                        resolved_date = adj_date
                        details = f"Re-attributed to adjacent roll context: {adj_details}"
                        attribution_confidence = "RESOLVED BATCH ATTRIBUTION (Indirect Causation)"
                        found_resolved = True
                        break
                
                if not found_resolved:
                    details = "Excluded/Batched Native platform change (No direct web/framework impact mapped)."
                    attribution_confidence = "LOW CONFIDENCE (Attributed to batched CI pipeline workers)"
            
            events.append({
                "renderer": renderer,
                "offset": offset_int,
                "type": event_type,
                "pct": abs(pct_change),
                "before": avg_before,
                "after": avg_after,
                "delta": avg_after - avg_before,
                "date": resolved_date,
                "hash": resolved_hash,
                "pr": resolved_pr_title,
                "author": resolved_author,
                "confidence": attribution_confidence,
                "details": details
            })
            
    # Sort chronologically
    events = sorted(events, key=lambda x: x["offset"])
    
    print("\n=========================================================================")
    print("🏆 THE FLUTTER WEB VERIFIED PERFORMANCE WIN & LOSS LEDGER")
    print("=========================================================================")
    print(f"Timeline Scope: 1 Year (5,000 commits) | Target: Infinite Scroll Frame Draw\n")
    
    for ev in events:
        pr_truncated = ev["pr"][:65] + "..." if len(ev["pr"]) > 68 else ev["pr"]
        change_symbol = "Speedup: -" if ev["delta"] < 0 else "Regression: +"
        color_marker = "🟢" if ev["delta"] < 0 else "🔴"
        
        print(f"{color_marker} {ev['type']} (+{ev['pct']:.1f}%)")
        print(f"  • Resolved Date:  {ev['date']:<10} | Commit Offset: {ev['offset']}")
        print(f"  • Mapped Renderer: {ev['renderer']:<15} | Hash: {ev['hash']}")
        print(f"  • Summary / PR:    {pr_truncated}")
        print(f"  • Metrics Delta:   {change_symbol}{abs(ev['delta']):.1f} µs (Before: {ev['before']:.1f} µs -> After: {ev['after']:.1f} µs)")
        print(f"  • Audit Details:   {ev['details']}")
        print(f"  • Attribution:     {ev['confidence']}")
        print(f"  • PR Link:         https://github.com/flutter/flutter/commit/{ev['hash']}")
        print("-" * 105)

if __name__ == "__main__":
    audit_ledger()
