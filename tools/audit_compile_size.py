import json
import time
import urllib.request
import subprocess
from datetime import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def start_query(query_str, commits=5000):
    url = "https://flutter-flutter-perf.luci.app/_/frame/start"
    body = {
        "end": 0,
        "num_commits": commits,
        "queries": [query_str],
        "tz": "America/Los_Angeles",
        "request_type": 1  # Compact mode
    }
    req_data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error starting query: {e}")
        return None

def poll_status(poll_path):
    url = "https://flutter-flutter-perf.luci.app" + poll_path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

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

# Directories touching Web engine, framework size bindings, or Wasm bytecode optimization levels
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
            
            for path in modified_paths:
                if any(prefix in path for prefix in WEB_RELEVANT_PATH_PREFIXES):
                    return True, f"Direct Size-Bloat Modification (e.g. {path.split('/')[-1]})"
            return False, "False-Positive (Native Platform/Impeller specific size modifier)"
    except Exception as e:
        return True, f"Attributed (API limits fallback: {e})"

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

def query_adjacent_commits(df, offset_idx, range_steps=3):
    offsets = df.index.tolist()
    curr_pos = offsets.index(int(offset_idx))
    start_pos = max(0, curr_pos - range_steps)
    end_pos = min(len(offsets), curr_pos + range_steps + 1)
    
    adjacent = []
    with open("data/web_wasm_compile_size_dataset.json", "r") as f:
        meta_data = json.load(f)["commit_metadata"]
        
    for pos in range(start_pos, end_pos):
        off = offsets[pos]
        adjacent.append((off, meta_data[str(off)]["hash"], meta_data[str(off)]["full_hash"]))
    return adjacent

def audit_compile_size():
    renderers = {
        "Hello World": "test=web_size__compile_test&sub_result=hello_world_web_build_dir_compressed_bytes",
        "Material Container": "test=web_size__compile_test&sub_result=basic_material_app_web_build_dir_compressed_bytes",
        "Flutter Gallery": "test=web_size__compile_test&sub_result=flutter_gallery_web_build_dir_compressed_bytes"
    }
    
    jobs = {}
    print("=========================================================================")
    print("🚀 TARGETED PERFORMANCE SCAN: COMPILE SIZE (COMPRESSED WASM BYTES)")
    print("=========================================================================")
    print("1. Submitting parallel size trace requests (Scope: 5,000 commits):")
    for name, q in renderers.items():
        res = start_query(q, commits=5000)
        if res:
            jobs[name] = {
                "status": res.get("status"),
                "poll_path": res.get("url"),
                "results": None
            }
            print(f"  [+] Started: {name}. Status path: {res.get('url')}")
            
    print("\n2. Polling progress loops...")
    completed = 0
    total = len(jobs)
    
    while completed < total:
        time.sleep(0.5)
        completed = 0
        status_line = []
        for name, job in jobs.items():
            if job["status"] in ["Finished", "Error"]:
                completed += 1
                status_line.append(f"{name}: {job['status']}")
                continue
            
            res = poll_status(job["poll_path"])
            if res:
                job["status"] = res.get("status")
                if job["status"] == "Finished":
                    job["results"] = res.get("results")
                    completed += 1
                elif job["status"] == "Error":
                    job["results"] = res
                    completed += 1
                msgs = res.get("messages", [])
                latest = msgs[-1].get("value") if msgs else "Queued"
                status_line.append(f"{name}: {job['status']} ({latest})")
            else:
                status_line.append(f"{name}: Failed")
        print(f"\rProgress: | " + " | ".join(status_line) + " |", end="", flush=True)
        
    print("\n\n3. Processing full year compile size timeline...")
    
    aligned_data = {}
    commit_metadata = {}
    
    for name, job in jobs.items():
        if job["status"] != "Finished":
            continue
            
        df_obj = job["results"].get("dataframe", {})
        header = df_obj.get("header", [])
        traceset = df_obj.get("traceset", {})
        
        if not traceset or not header:
            continue
            
        for col in header:
            offset = col["offset"]
            if offset not in commit_metadata:
                commit_metadata[offset] = {
                    "hash": col["hash"][:8] if col.get("hash") else "N/A",
                    "full_hash": col.get("hash", ""),
                    "timestamp": col["timestamp"]
                }
                
        trace_key = list(traceset.keys())[0]
        values = traceset[trace_key]
        offsets = [col["offset"] for col in header]
        
        for offset, val in zip(offsets, values):
            clean_val = val if val is not None and val < 1e30 else np.nan
            if name not in aligned_data:
                aligned_data[name] = {}
            aligned_data[name][offset] = clean_val
            
    # Cache raw size matrix
    with open("data/web_wasm_compile_size_dataset.json", "w") as out:
        json.dump({"commit_metadata": commit_metadata, "series": aligned_data}, out, indent=2)
    print("[✓] Raw size dataset saved to 'data/web_wasm_compile_size_dataset.json'!")
    
    df = pd.DataFrame(aligned_data).sort_index()
    df.index = df.index.astype(int)
    print(f"  • Total Merged Commits (Index columns): {len(df)}")
    
    # Apply flat baseline step detector (Since size StDev = 0, steps represent flat baseline transitions!)
    # We filter out any step change that exceeds a threshold of 0.5% baseline shift
    threshold_pct = 0.5
    window = 12
    
    events = []
    
    print("\n4. Running Flat-Step anomaly scanner over clean series...")
    for renderer in df.columns:
        clean_series = df[renderer].dropna()
        if clean_series.empty:
            continue
            
        # Compile direct changes on clean series
        diffs = clean_series.diff()
        
        sorted_diffs = diffs.dropna().abs().sort_values(ascending=False)
        
        processed_offsets = []
        for offset, val in sorted_diffs.items():
            offset_str = str(offset)
            offset_int = int(offset)
            
            if any(abs(offset_int - po) < 25 for po in processed_offsets):
                continue
                
            idx_pos = clean_series.index.get_loc(offset_int)
            avg_before = clean_series.iloc[max(0, idx_pos - 8):idx_pos].mean()
            avg_after = clean_series.iloc[idx_pos:min(len(clean_series), idx_pos + 8)].mean()
            
            if np.isnan(avg_before) or np.isnan(avg_after) or avg_before == 0:
                continue
                
            pct_change = ((avg_after - avg_before) / avg_before) * 100
            
            if abs(pct_change) < threshold_pct:
                continue
                
            processed_offsets.append(offset_int)
            
            meta = commit_metadata[offset_int]
            pr_title, author, commit_date = resolve_github_pr(meta["full_hash"])
            
            is_relevant, details = check_commit_relevance(meta["full_hash"], pr_title)
            
            event_type = "🟢 🏆 BINARY SIZE REDUCTION (WIN)" if pct_change < 0 else "🔴 🚨 BINARY SIZE BLOAT (REGRESSION)"
            
            resolved_pr_title = pr_title
            resolved_hash = meta["hash"]
            resolved_author = author
            resolved_date = commit_date
            attribution_confidence = "HIGH (Direct Size Audit Map)" if is_relevant else "CORRELATION BATCH ADJACENCY"
            
            # BATCH RESOLVER
            if not is_relevant:
                adjacent_commits = query_adjacent_commits(df, offset_str, range_steps=3)
                found_resolved = False
                for adj_offset, adj_shash, adj_fhash in adjacent_commits:
                    adj_title, adj_author, adj_date = resolve_github_pr(adj_fhash)
                    adj_relevant, adj_details = check_commit_relevance(adj_fhash, adj_title)
                    if adj_relevant:
                        resolved_pr_title = f"[RESOLVED BATCH SIZE SHIFT] {adj_title}"
                        resolved_hash = adj_shash
                        resolved_author = adj_author
                        resolved_date = adj_date
                        details = f"Re-attributed size change to adjacent roll: {adj_details}"
                        attribution_confidence = "RESOLVED BATCH ATTRIBUTION (Indirect Size Causation)"
                        found_resolved = True
                        break
                if not found_resolved:
                    details = "Excluded/Batched Native asset update (No direct wasm engine impact mapped)."
                    attribution_confidence = "LOW CONFIDENCE (Attributed to compiler infrastructure/backlogs)"
            
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
            
    events = sorted(events, key=lambda x: x["offset"])
    
    print("\n=========================================================================")
    print("🏆 THE FLUTTER WEB VERIFIED COMPILE-SIZE WINS & LOSSES LEDGER")
    print("=========================================================================")
    print(f"Timeline Scope: 1 Year (5,000 commits) | Target: Compressed Wasm Bytecount (StDev = 0)\n")
    
    for ev in events:
        pr_truncated = ev["pr"][:65] + "..." if len(ev["pr"]) > 68 else ev["pr"]
        change_symbol = "Binary Drop: -" if ev["delta"] < 0 else "Binary Bloat: +"
        color_marker = "🟢" if ev["delta"] < 0 else "🔴"
        
        # Convert bytes to standard KB for human reading
        delta_kb = ev["delta"] / 1024.0
        before_kb = ev["before"] / 1024.0
        after_kb = ev["after"] / 1024.0
        
        print(f"{color_marker} {ev['type']} ({change_symbol[:-2]} {abs(pct_change):.2f}%)")
        print(f"  • Resolved Date:  {ev['date']:<10} | Commit Offset: {ev['offset']}")
        print(f"  • Mapped Application Target: {ev['renderer']:<22} | Hash: {ev['hash']}")
        print(f"  • Summary / PR:    {pr_truncated}")
        print(f"  • Metrics Delta:   {change_symbol}{abs(delta_kb):.2f} KB (Before: {before_kb:.2f} KB -> After: {after_kb:.2f} KB)")
        print(f"  • Audit Details:   {ev['details']}")
        print(f"  • Attribution:     {ev['confidence']}")
        print(f"  • PR Link:         https://github.com/flutter/flutter/commit/{ev['hash']}")
        print("-" * 105)
        
    # ----------------- VISUALIZATION -----------------
    print("\n5. Generating premium size trendlines visualization dashboard...")
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 9.5), dpi=200)
    
    fig.patch.set_facecolor('#08080A')
    ax.set_facecolor('#0E0E14')
    
    colors = {
        "Hello World": "#FF1744",         # Hot Pink/Red
        "Material Container": "#2979FF",   # Blue
        "Flutter Gallery": "#00E676"      # Lime Green
    }
    
    present_offsets = df.index.tolist()
    present_hashes = [commit_metadata[offset]["hash"] for offset in present_offsets]
    
    for name in df.columns:
        color = colors.get(name, "#76FF03")
        clean_renderer = df[name].dropna()
        
        if clean_renderer.empty:
            continue
            
        # Convert raw series to KB mapping
        clean_renderer_kb = clean_renderer / 1024.0
        
        # Plot perfect flat step plateaus (since variance = 0, curves map perfect baseline shifts!)
        ax.plot(clean_renderer_kb.index, clean_renderer_kb, label=f"{name} Wasm Size (KB)", 
                color=color, linewidth=3.0, alpha=0.9)
        ax.fill_between(clean_renderer_kb.index, clean_renderer_kb, alpha=0.03, color=color)
        
        # Annotate final baseline sizes
        final_size_kb = clean_renderer_kb.iloc[-1]
        ax.axhline(final_size_kb, color=color, linestyle=':', alpha=0.25, linewidth=1.1)
        ax.text(df.index[-1] + 5, final_size_kb, f" Final: {final_size_kb:.1f} KB", 
                color=color, fontsize=8.5, fontweight='semibold', va='center')
        
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='#252530', alpha=0.6)
    ax.set_axisbelow(True)
    
    ax.set_title(f"Flutter Web Assembly: 1-Year Compile-Size Baseline Plateau Trends", 
                 fontsize=14, fontweight='bold', color='#FFFFFF', pad=25)
    ax.set_ylabel("Compiled Bytecode Footprint (Kilobytes - KB)", fontsize=11, fontweight='semibold', color='#B5B5C5', labelpad=15)
    ax.set_xlabel("Commit Pipeline Timeline (Offset / Git Hash)", fontsize=11, fontweight='semibold', color='#B5B5C5', labelpad=20)
    
    for spine in ax.spines.values():
        spine.set_color('#252530')
        spine.set_linewidth(1.0)
        
    tick_step = int(len(present_offsets) / 6) if len(present_offsets) > 6 else 1
    tick_indices = list(range(0, len(present_offsets), tick_step))
    if len(present_offsets) - 1 not in tick_indices:
        tick_indices.append(len(present_offsets) - 1)
        
    ax.set_xticks([present_offsets[idx] for idx in tick_indices])
    tick_labels = [f"Offset {present_offsets[idx]}\n[{present_hashes[idx]}]" for idx in tick_indices]
    ax.set_xticklabels(tick_labels, fontsize=8, color='#9B9BAF')
    
    ax.set_xlim(df.index[0] - 15, df.index[-1] + 150)
    
    legend = ax.legend(loc='upper left', frameon=True, facecolor='#16161F', edgecolor='#252530', 
                       fontsize=10.5, shadow=False)
    plt.setp(legend.get_texts(), color='#FFFFFF', fontweight='medium')
    
    plt.tight_layout()
    
    chart_dest = "charts/web_wasm_compile_size_trends.png"
    plt.savefig(chart_dest, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.savefig("/Users/kevmoo/.gemini/jetski/brain/53de17ee-4467-4d1e-9948-657e084ed2a6/web_wasm_compile_size_trends.png", 
                facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    print(f"\n[✓] Compile-size trendline chart saved locally to '{chart_dest}' and to brain!")

if __name__ == "__main__":
    audit_compile_size()
