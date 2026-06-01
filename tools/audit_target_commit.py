import json
import subprocess
import numpy as np
from scipy import stats
from datetime import datetime

TARGET_HASH = "eb9b7d079011cab9376ef03092577dd184bd3480"
TARGET_OFFSET = 2808107

def get_commit_details_via_gh(commit_hash):
    cmd = ["gh", "api", f"repos/flutter/flutter/commits/{commit_hash}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        msg = data.get("commit", {}).get("message", "N/A").split("\n")[0]
        author = data.get("commit", {}).get("author", {}).get("name", "Unknown")
        date_str = data.get("commit", {}).get("author", {}).get("date", "")
        files = [f.get("filename") for f in data.get("files", [])]
        
        if date_str:
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = dt.strftime("%Y-%m-%d %H:%M")
        else:
            formatted_date = "Unknown"
            
        return {
            "message": msg,
            "author": author,
            "date": formatted_date,
            "files": files
        }
    except Exception as e:
        return {
            "message": f"Error fetching via gh: {e}",
            "author": "N/A",
            "date": "N/A",
            "files": []
        }

def audit_target():
    print("============================================================")
    print(f"🔬 TARGETED AUDIT: SKWASM OPTIMIZATION COMMIT {TARGET_HASH[:8]}")
    print("============================================================\n")
    
    # 1. Fetch commit metadata via GitHub CLI
    print("1. Fetching commit details via GitHub CLI...")
    commit_info = get_commit_details_via_gh(TARGET_HASH)
    print(f"  • PR Message: {commit_info['message']}")
    print(f"  • Author:     {commit_info['author']}")
    print(f"  • Date/Time:  {commit_info['date']}")
    print(f"  • Files Mapped: {len(commit_info['files'])} files modified.")
    
    web_ui_files = [f for f in commit_info['files'] if "web_ui" in f]
    print(f"  • Web Engine Files Modified:")
    for f in web_ui_files[:5]:
        print(f"    - {f}")
    if len(web_ui_files) > 5:
        print(f"    - ... and {len(web_ui_files) - 5} more.")
    print()
    
    # 2. Load Datasets
    datasets = {
        "Simple Lazy Text Scroll": "data/web_wasm_text_scroll_dataset.json",
        "Card Infinite Scroll": "data/web_wasm_annual_dataset.json"
    }
    
    results_summary = {}
    
    for title, path in datasets.items():
        print('=' * 60)
        print(f"📊 ANALYZING METRIC: {title}")
        print('=' * 60)
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}\n")
            continue
            
        meta = data["commit_metadata"]
        series = data["series"]
        sorted_offsets = sorted([int(k) for k in meta.keys()])
        
        if TARGET_OFFSET not in sorted_offsets:
            print(f"Target offset {TARGET_OFFSET} not found in dataset.\n")
            continue
            
        idx = sorted_offsets.index(TARGET_OFFSET)
        
        # We take 20 commits before and 20 commits after (excluding target from 'before' and including in 'after')
        before_offsets = sorted_offsets[max(0, idx-20):idx]
        after_offsets = sorted_offsets[idx:idx+21]
        
        results_summary[title] = {}
        
        for name in ["CanvasKit", "SkWasm", "SkWasm ST"]:
            raw_before = [series[name].get(str(off)) for off in before_offsets]
            raw_after = [series[name].get(str(off)) for off in after_offsets]
            
            before = [v for v in raw_before if v is not None and v < 1e30]
            after = [v for v in raw_after if v is not None and v < 1e30]
            
            if not before or not after:
                print(f"  {name}: Missing performance points.")
                continue
                
            mean_b, std_b = np.mean(before), np.std(before)
            mean_a, std_a = np.mean(after), np.std(after)
            
            diff = mean_a - mean_b
            pct = (diff / mean_b) * 100
            
            t_stat, p_val = stats.ttest_ind(before, after, equal_var=False)
            
            print(f"  Renderer: {name:<12}")
            print(f"    • Pre-commit (N={len(before)}):  {mean_b:.2f} ± {std_b:.2f} ms")
            print(f"    • Post-commit (N={len(after)}): {mean_a:.2f} ± {std_a:.2f} ms")
            print(f"    • Delta:             {diff:+.2f} ms ({pct:+.2f}%)")
            print(f"    • t-statistic:        {t_stat:.4f}")
            print(f"    • p-value:            {p_val:.6f} (Significant: {p_val < 0.05})")
            
            results_summary[title][name] = {
                "before_mean": mean_b,
                "before_std": std_b,
                "after_mean": mean_a,
                "after_std": std_a,
                "pct": pct,
                "diff": diff,
                "p_val": p_val
            }
            print()
            
    # 3. Resolve Adjacent Commits Details
    print("=" * 60)
    print("🔗 INTER-COMMIT PIPELINE ARCHAEOLOGY (Post-Commit Sequence)")
    print("=" * 60)
    print("Let's examine the next 8 commits after the target to see what other changes occurred:")
    
    # Let's load one metadata map to get adjacent shas
    with open(datasets["Card Infinite Scroll"], "r") as f:
        card_data = json.load(f)
    meta = card_data["commit_metadata"]
    sorted_offsets = sorted([int(k) for k in meta.keys()])
    idx = sorted_offsets.index(TARGET_OFFSET)
    
    adjacent_offsets = sorted_offsets[idx+1 : idx+9]
    for off in adjacent_offsets:
        h = meta[str(off)]["full_hash"]
        sh = meta[str(off)]["hash"]
        adj_info = get_commit_details_via_gh(h)
        print(f"  [Offset {off} | {sh}] {adj_info['date']} | {adj_info['author']}")
        print(f"    • PR: {adj_info['message']}")
        # Check if any web files were modified
        adj_web = [f for f in adj_info['files'] if "web_ui" in f or "lib/web_ui" in f]
        if adj_web:
            print(f"    • ⚠️ Direct Web Files Mapped: {len(adj_web)} files (e.g., {adj_web[0].split('/')[-1]})")
        print()

if __name__ == "__main__":
    audit_target()
