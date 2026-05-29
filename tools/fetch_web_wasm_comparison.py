import json
import time
import urllib.request
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def start_query(query_str, commits=50):
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
            data = json.loads(resp.read().decode("utf-8"))
            return data
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

def fetch_comparison():
    renderers = {
        "CanvasKit": "test=web_benchmarks_canvaskit&sub_result=bench_card_infinite_scroll.canvaskit.drawFrameDuration.average",
        "SkWasm (Multi-Threaded)": "test=web_benchmarks_skwasm&sub_result=bench_card_infinite_scroll.skwasm.drawFrameDuration.average",
        "SkWasm ST (Single-Threaded)": "test=web_benchmarks_skwasm_st&sub_result=bench_card_infinite_scroll.skwasm_st.drawFrameDuration.average"
    }
    
    jobs = {}
    print("1. Launching parallel progressive query jobs on LUCI Perf:")
    for name, query_str in renderers.items():
        res = start_query(query_str, commits=50)
        if res:
            jobs[name] = {
                "status": res.get("status"),
                "poll_path": res.get("url"),
                "results": None
            }
            print(f"  [+] Job started for {name}. Status URL: {res.get('url')}")
            
    if len(jobs) != len(renderers):
        print("[!] Error: Not all jobs could be started successfully. Aborting.")
        return
        
    print("\n2. Polling progress of active queries concurrently...")
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
            
            # Poll status
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
                latest_step = msgs[-1].get("value") if msgs else "Queued"
                status_line.append(f"{name}: {job['status']} ({latest_step})")
            else:
                status_line.append(f"{name}: Poll Failed")
                
        print(f"\rProgress: | " + " | ".join(status_line) + " |", end="", flush=True)
        
    print("\n\n3. All queries resolved! Processing and aligning datasets...")
    
    # Extract data series
    aligned_data = {}
    commit_metadata = {} # mapping offset -> metadata dict
    
    for name, job in jobs.items():
        if job["status"] != "Finished":
            print(f"[!] Warning: Job {name} finished with status '{job['status']}' and failed to return data.")
            continue
            
        df = job["results"].get("dataframe", {})
        header = df.get("header", [])
        traceset = df.get("traceset", {})
        
        if not traceset or not header:
            print(f"[!] Warning: No traceset or header returned for {name}.")
            continue
            
        # Store metadata for headers mapping offsets
        for col in header:
            offset = col["offset"]
            if offset not in commit_metadata:
                commit_metadata[offset] = {
                    "hash": col["hash"][:8] if col.get("hash") else "N/A",
                    "timestamp": col["timestamp"],
                    "date": datetime.fromtimestamp(col["timestamp"]).strftime("%Y-%m-%d\n%H:%M")
                }
                
        # There should be exactly 1 trace in the traceset
        trace_key = list(traceset.keys())[0]
        values = traceset[trace_key]
        
        offsets = [col["offset"] for col in header]
        
        # Build series
        for offset, val in zip(offsets, values):
            # Clean out missing data points sentinels (like 1e32 or similar)
            clean_val = val if val is not None and val < 1e30 else np.nan
            if name not in aligned_data:
                aligned_data[name] = {}
            aligned_data[name][offset] = clean_val
            
    # Write raw comparison to a local json file for history reference
    comparison_dataset = {
        "commit_metadata": commit_metadata,
        "series": aligned_data
    }
    with open("data/web_wasm_comparison.json", "w") as out:
        json.dump(comparison_dataset, out, indent=2)
    print("[✓] Raw comparison dataset cached successfully in 'data/web_wasm_comparison.json'!")
    
    # Load into Pandas
    df = pd.DataFrame(aligned_data)
    # Sort indices so offsets increase linearly
    df = df.sort_index()
    
    # Filter metadata for tick labels matching df indices
    present_offsets = df.index.tolist()
    present_hashes = [commit_metadata[offset]["hash"] for offset in present_offsets]
    present_dates = [commit_metadata[offset]["date"] for offset in present_offsets]
    
    print(f"\nAligned Data Matrix Summary (First 5 commits):")
    print(df.head())
    
    # ----------------- VISUALIZATION -----------------
    print("\n4. Generating comparative high-end data visualization...")
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(15, 8.5), dpi=200)
    
    fig.patch.set_facecolor('#0D0D11')
    ax.set_facecolor('#13131A')
    
    # Define design tokens - curated premium palette
    colors = {
        "CanvasKit": "#00E5FF",                 # Vibrant Electric Neon Cyan
        "SkWasm (Multi-Threaded)": "#E040FB",   # Neon Royal Magenta/Purple
        "SkWasm ST (Single-Threaded)": "#FF9100" # Neon Electric Gold/Orange
    }
    
    for name in df.columns:
        color = colors.get(name, "#76FF03")
        # Plot curves
        ax.plot(df.index, df[name], label=name, color=color, 
                linewidth=2.5, marker='o', markersize=5.5,
                markeredgecolor=color, markerfacecolor='#13131A', markeredgewidth=1.2)
        # Gradient backdrop glow
        ax.fill_between(df.index, df[name], alpha=0.06, color=color)
        
        # Plot dotted average indicator line
        mean_val = df[name].mean()
        ax.axhline(mean_val, color=color, linestyle=':', alpha=0.35, linewidth=1.2)
        # Add side marker text for average line
        ax.text(df.index[-1] + 1.5, mean_val, f" {mean_val:.2f} ms", 
                color=color, fontsize=8.5, fontweight='bold', va='center')
        
    # Grid lines
    ax.grid(True, which='both', linestyle='--', linewidth=0.5, color='#282835', alpha=0.7)
    ax.set_axisbelow(True)
    
    # Labels
    ax.set_title("Flutter Web Rendering Comparison: Card Infinite Scroll drawFrameDuration", 
                 fontsize=15, fontweight='bold', color='#FFFFFF', pad=25)
    ax.set_ylabel("Frame Draw Duration (milliseconds)", fontsize=11, fontweight='semibold', color='#B5B5C9', labelpad=15)
    ax.set_xlabel("Commit Offset / Date & Time", fontsize=11, fontweight='semibold', color='#B5B5C9', labelpad=20)
    
    # Spines
    for spine in ax.spines.values():
        spine.set_color('#2E2E3C')
        spine.set_linewidth(1.0)
        
    # Set X-axis ticks (showing every 5th tick to prevent overlapping)
    tick_step = 5
    tick_indices = list(range(0, len(present_offsets), tick_step))
    if len(present_offsets) - 1 not in tick_indices:
        tick_indices.append(len(present_offsets) - 1)
        
    ax.set_xticks([present_offsets[idx] for idx in tick_indices])
    
    tick_labels = []
    for idx in tick_indices:
        lbl = f"Offset {present_offsets[idx]}\n[{present_hashes[idx]}]\n{present_dates[idx]}"
        tick_labels.append(lbl)
    ax.set_xticklabels(tick_labels, fontsize=8.5, color='#A5A5BC')
    
    # Padding on X-axis right side to prevent cutting off text markers
    ax.set_xlim(df.index[0] - 2, df.index[-1] + 6)
    
    # Legend
    legend = ax.legend(loc='upper left', frameon=True, facecolor='#1D1D27', edgecolor='#2E2E3C', 
                       fontsize=10.5, shadow=False)
    plt.setp(legend.get_texts(), color='#FFFFFF', fontweight='medium')
    
    plt.tight_layout()
    
    # Save the rendered premium comparative visualization directly to the brain directory
    chart_local = "charts/web_wasm_comparison_chart.png"
    chart_dest = "/Users/kevmoo/.gemini/jetski/brain/53de17ee-4467-4d1e-9948-657e084ed2a6/web_wasm_comparison_chart.png"
    plt.savefig(chart_local, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    plt.savefig(chart_dest, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
    print(f"\n[✓] Comparative chart successfully written locally to '{chart_local}' and to brain: {chart_dest}")

if __name__ == "__main__":
    fetch_comparison()
