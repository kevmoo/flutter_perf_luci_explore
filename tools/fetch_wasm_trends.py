import json
import time
import urllib.request
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def start_query(query_str, commits=250):
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
        print(f"Error starting query '{query_str}': {e}")
        return None

def poll_status(poll_path):
    url = "https://flutter-flutter-perf.luci.app" + poll_path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error polling status at {poll_path}: {e}")
        return None

def fetch_and_smooth():
    renderers = {
        "CanvasKit": "test=web_benchmarks_canvaskit&sub_result=bench_card_infinite_scroll.canvaskit.drawFrameDuration.average",
        "SkWasm (Multi-Threaded)": "test=web_benchmarks_skwasm&sub_result=bench_card_infinite_scroll.skwasm.drawFrameDuration.average",
        "SkWasm ST (Single-Threaded)": "test=web_benchmarks_skwasm_st&sub_result=bench_card_infinite_scroll.skwasm_st.drawFrameDuration.average"
    }
    
    jobs = {}
    print("1. Initiating parallel progressive trace requests (Scope: 250 commits):")
    for name, query_str in renderers.items():
        res = start_query(query_str, commits=250)
        if res:
            jobs[name] = {
                "status": res.get("status"),
                "poll_path": res.get("url"),
                "results": None
            }
            print(f"  [+] Started: {name}. Status Path: {res.get('url')}")
            
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
        
    print("\n\n3. All jobs resolved! Parsing and applying moving averages...")
    
    aligned_data = {}
    commit_metadata = {}
    
    for name, job in jobs.items():
        if job["status"] != "Finished":
            print(f"[!] Warning: Job {name} has no finished data series.")
            continue
            
        df = job["results"].get("dataframe", {})
        header = df.get("header", [])
        traceset = df.get("traceset", {})
        
        if not traceset or not header:
            continue
            
        for col in header:
            offset = col["offset"]
            if offset not in commit_metadata:
                commit_metadata[offset] = {
                    "hash": col["hash"][:8] if col.get("hash") else "N/A",
                    "timestamp": col["timestamp"],
                    "date": datetime.fromtimestamp(col["timestamp"]).strftime("%m-%d %H:%M")
                }
                
        trace_key = list(traceset.keys())[0]
        values = traceset[trace_key]
        offsets = [col["offset"] for col in header]
        
        for offset, val in zip(offsets, values):
            clean_val = val if val is not None and val < 1e30 else np.nan
            if name not in aligned_data:
                aligned_data[name] = {}
            aligned_data[name][offset] = clean_val
            
    # Cache raw matrix 
    with open("data/web_wasm_trends_dataset.json", "w") as out:
        json.dump({"commit_metadata": commit_metadata, "series": aligned_data}, out, indent=2)
    print("[✓] Raw trend dataset successfully saved to 'data/web_wasm_trends_dataset.json'!")
    
    # Construct clean aligned timeline DataFrame
    df = pd.DataFrame(aligned_data).sort_index()
    
    # Apply statistical smoothing: 15-commit Rolling Simple Moving Average (SMA)
    # Using min_periods=1 ensures we still get smoothed values at the boundaries
    smoothing_window = 15
    df_smoothed = df.rolling(window=smoothing_window, min_periods=3).mean()
    
    print(f"\nSmoothed Data Matrix Summary (First 5 records, rolling window={smoothing_window}):")
    print(df_smoothed.head(10))
    
    # ----------------- PLOTTING -----------------
    print("\n4. Generating premium comparative trends visualization dashboard...")
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(16, 9.5), dpi=200)
    
    fig.patch.set_facecolor('#0B0B0E')
    ax.set_facecolor('#111116')
    
    colors = {
        "CanvasKit": "#00E5FF",
        "SkWasm (Multi-Threaded)": "#E040FB",
        "SkWasm ST (Single-Threaded)": "#FF9100"
    }
    
    present_offsets = df.index.tolist()
    present_hashes = [commit_metadata[offset]["hash"] for offset in present_offsets]
    present_dates = [commit_metadata[offset]["date"] for offset in present_offsets]
    
    # Plot curves for each series
    for name in df.columns:
        color = colors.get(name, "#76FF03")
        
        # A. Plot raw dataset as ultra-light, semi-transparent background points
        ax.plot(df.index, df[name], color=color, alpha=0.15, linewidth=0.8)
        ax.scatter(df.index, df[name], color=color, alpha=0.18, s=8, edgecolors='none')
        
        # B. Plot the solid, thick, glowing rolling average curves (the primary focus)
        ax.plot(df_smoothed.index, df_smoothed[name], label=f"{name} ({smoothing_window}-Commit SMA)", 
                color=color, linewidth=3.0)
        
        # C. Soft glow shadow under the rolling curves
        ax.fill_between(df_smoothed.index, df_smoothed[name], alpha=0.05, color=color)
        
        # D. Horizontal dashed indicator for historical global average
        global_avg = df[name].mean()
        ax.axhline(global_avg, color=color, linestyle=':', alpha=0.25, linewidth=1.1)
        ax.text(df.index[-1] + 2, global_avg, f" Avg: {global_avg:.2f} ms", 
                color=color, fontsize=8, fontweight='semibold', va='center')
        
    # Grid lines & border styling
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='#252532', alpha=0.6)
    ax.set_axisbelow(True)
    
    ax.set_title(f"Flutter Web Rendering Performance Trends Over Time (Scope: 250 Commits)", 
                 fontsize=15, fontweight='bold', color='#FFFFFF', pad=25)
    ax.set_ylabel("Frame Draw Duration (milliseconds)", fontsize=11, fontweight='semibold', color='#B5B5C5', labelpad=15)
    ax.set_xlabel("Commit Pipeline Timeline (Offset / Git Hash / Date & Time)", fontsize=11, fontweight='semibold', color='#B5B5C5', labelpad=20)
    
    for spine in ax.spines.values():
        spine.set_color('#252532')
        spine.set_linewidth(1.0)
        
    # Beautiful tick formatting on X-axis (every 25 commits)
    tick_step = 25
    tick_indices = list(range(0, len(present_offsets), tick_step))
    if len(present_offsets) - 1 not in tick_indices:
        tick_indices.append(len(present_offsets) - 1)
        
    ax.set_xticks([present_offsets[idx] for idx in tick_indices])
    tick_labels = [f"Offset {present_offsets[idx]}\n[{present_hashes[idx]}]\n{present_dates[idx]}" for idx in tick_indices]
    ax.set_xticklabels(tick_labels, fontsize=8, color='#9C9CB0')
    
    ax.set_xlim(df.index[0] - 5, df.index[-1] + 25)
    
    # Legend
    legend = ax.legend(loc='upper left', frameon=True, facecolor='#191922', edgecolor='#252532', 
                       fontsize=10.5, shadow=False)
    plt.setp(legend.get_texts(), color='#FFFFFF', fontweight='medium')
    
    plt.tight_layout()
    
    # Save comparison charts locally and to the brain artifacts directory
    chart_dest = "charts/web_wasm_trends_chart.png"
    plt.savefig(chart_dest, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.savefig("/Users/kevmoo/.gemini/jetski/brain/53de17ee-4467-4d1e-9948-657e084ed2a6/web_wasm_trends_chart.png", 
                facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    
    print(f"\n[✓] Trend visualization saved locally to '{chart_dest}' and to brain!")
    
if __name__ == "__main__":
    fetch_and_smooth()
