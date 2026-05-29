import json
import time
import urllib.request
import urllib.error

def fetch_perf_data():
    start_url = "https://flutter-flutter-perf.luci.app/_/frame/start"
    
    # Let's request the last 50 commits of complex_layout_scroll_perf__timeline_summary
    query = "test=complex_layout_scroll_perf__timeline_summary&sub_result=average_frame_build_time_millis"
    
    req_body = {
        "end": 0,
        "num_commits": 50,
        "queries": [query],
        "tz": "America/Los_Angeles",
        "request_type": 1  # REQUEST_COMPACT
    }
    
    print(f"1. Starting frame request for query: '{query}'...")
    req_data = json.dumps(req_body).encode("utf-8")
    req = urllib.request.Request(
        start_url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            prog = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error starting request: {e}")
        return
        
    print(f"Response: {json.dumps(prog)}")
    
    status = prog.get("status")
    poll_path = prog.get("url")
    
    if not poll_path:
        print("Error: No polling URL returned in response.")
        return
        
    poll_url = "https://flutter-flutter-perf.luci.app" + poll_path
    print(f"2. Polling status from: {poll_url}")
    
    while status == "Running":
        time.sleep(0.5)
        poll_req = urllib.request.Request(poll_url, method="GET")
        try:
            with urllib.request.urlopen(poll_req) as resp:
                prog = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"\nError polling status: {e}")
            return
            
        status = prog.get("status")
        messages = prog.get("messages", [])
        msg_str = ", ".join([f"{m.get('key')}: {m.get('value')}" for m in messages])
        print(f"\rStatus: {status} | Progress details: {msg_str}", end="", flush=True)
        
    print() # New line after finished polling
    
    if status == "Finished":
        print("3. Query finished successfully! Saving results...")
        output_file = "data/perf_results.json"
        with open(output_file, "w") as out:
            json.dump(prog, out, indent=2)
            
        print(f"Results successfully written to '{output_file}'!")
        
        # Print a quick summary of the returned dataframe
        results = prog.get("results", {})
        df = results.get("dataframe", {})
        header = df.get("header", [])
        traceset = df.get("traceset", {})
        
        print(f"\nDataFrame Summary:")
        print(f"  Number of columns (commits): {len(header)}")
        print(f"  Number of traces: {len(traceset)}")
        
        if len(traceset) > 0:
            print("  Trace IDs:")
            for tid in traceset.keys():
                print(f"    - {tid}")
                # Print first few non-null values
                vals = traceset[tid]
                non_null_vals = [v for v in vals if v is not None and v < 1e30]
                print(f"      First non-null values: {non_null_vals[:5]}")
        
        if len(header) > 0:
            print("  Commits sample (first 3 and last 3):")
            sample_indices = list(range(min(3, len(header))))
            if len(header) > 6:
                sample_indices += list(range(len(header) - 3, len(header)))
            else:
                sample_indices = list(range(len(header)))
                
            for idx in sorted(list(set(sample_indices))):
                col = header[idx]
                print(f"    Commit offset {col.get('offset')}: ts={col.get('timestamp')}, sha={col.get('sha')[:8] if col.get('sha') else 'N/A'}")
                
    else:
        print(f"Error: Job finished with status '{status}'. Details:")
        for m in prog.get("messages", []):
            print(f"  [{m.get('key')}]: {m.get('value')}")

if __name__ == "__main__":
    fetch_perf_data()
