import json
import time
import urllib.request
import numpy as np

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
        print(f"Error starting query '{query_str}': {e}")
        return None

def poll_status(poll_path):
    url = "https://flutter-flutter-perf.luci.app" + poll_path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def fetch_annual_dataset():
    renderers = {
        "CanvasKit": "test=web_benchmarks_canvaskit&sub_result=bench_card_infinite_scroll.canvaskit.drawFrameDuration.average",
        "SkWasm": "test=web_benchmarks_skwasm&sub_result=bench_card_infinite_scroll.skwasm.drawFrameDuration.average",
        "SkWasm ST": "test=web_benchmarks_skwasm_st&sub_result=bench_card_infinite_scroll.skwasm_st.drawFrameDuration.average"
    }
    
    jobs = {}
    print("=========================================================================")
    print("🚀 FETCHING NEW ANNUAL PERFORMANCE DATASET (Scope: 5,000 commits)")
    print("=========================================================================")
    print("1. Submitting parallel trace requests for Card Infinite Scroll...")
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
        time.sleep(1.0)
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
        
    print("\n\n3. Aligning datasets and formatting metadata...")
    
    aligned_data = {}
    commit_metadata = {}
    
    for name, job in jobs.items():
        if job["status"] != "Finished":
            print(f"[!] Warning: Job for {name} finished with status '{job['status']}' (no data).")
            continue
            
        df_obj = job["results"].get("dataframe", {})
        header = df_obj.get("header", [])
        traceset = df_obj.get("traceset", {})
        
        if not traceset or not header:
            print(f"[!] Warning: Traceset or header empty for {name}.")
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
            clean_val = val if val is not None and val < 1e30 else None
            if name not in aligned_data:
                aligned_data[name] = {}
            aligned_data[name][offset] = clean_val
            
    # Cache raw matrix 
    output_file = "data/web_wasm_annual_dataset.json"
    with open(output_file, "w") as out:
        json.dump({"commit_metadata": commit_metadata, "series": aligned_data}, out, indent=2)
    print(f"\n[✓] Raw annual dataset successfully saved to '{output_file}'!")
    
    # Print a brief summary
    total_offsets = len(commit_metadata)
    sorted_offsets = sorted(list(commit_metadata.keys()))
    print(f"  • Total commits mapped: {total_offsets}")
    if total_offsets > 0:
        last_offset = sorted_offsets[-1]
        print(f"  • Latest offset: {last_offset} (hash: {commit_metadata[last_offset]['hash']})")

if __name__ == "__main__":
    fetch_annual_dataset()
