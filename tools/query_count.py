import json
import urllib.request

def check_count(query_str):
    url = "https://flutter-flutter-perf.luci.app/_/count"
    req_body = {
        "q": query_str,
        "begin": 0,
        "end": 0
    }
    req_data = json.dumps(req_body).encode("utf-8")
    req = urllib.request.Request(
        url, 
        data=req_data, 
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            count = resp_data.get("count", 0)
            ps_keys = sorted(resp_data.get("paramset", {}).keys())
            print(f"Query: '{query_str}' -> Match Count: {count}")
            if count > 0:
                print("Matching keys:")
                for k in ps_keys:
                    vals = resp_data["paramset"][k]
                    print(f"  {k} ({len(vals)} values): {vals[:10]}...")
            else:
                print("No matches found.")
    except Exception as e:
        print(f"Error checking count for query '{query_str}': {e}")

check_count("test=complex_layout_scroll_perf__timeline_summary&sub_result=average_frame_build_time_millis")
check_count("test=complex_layout_scroll_perf__timeline_summary")
