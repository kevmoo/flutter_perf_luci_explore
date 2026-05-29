import json
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Load results
with open("data/perf_results.json", "r") as f:
    prog_data = json.load(f)

df_data = prog_data["results"]["dataframe"]
traceset = df_data["traceset"]
header = df_data["header"]

# Construct clean lists
commit_offsets = [col["offset"] for col in header]
commit_hashes = [col["hash"][:8] for col in header]
commit_dates = [datetime.fromtimestamp(col["timestamp"]).strftime("%Y-%m-%d\n%H:%M") for col in header]
commit_messages = [col["message"] for col in header]

# Build a clean pandas DataFrame for traces
clean_traces = {}
for trace_id, values in traceset.items():
    # Parse human-readable name from trace ID key
    # e.g., ",arch=intel,branch=master,config=default,device_type=Pixel_7_Pro..."
    params = dict(item.split("=") for item in trace_id.strip(",").split(",") if "=" in item)
    dev_type = params.get("device_type", "Unknown Device")
    clean_traces[dev_type] = values

df = pd.DataFrame(clean_traces, index=commit_offsets)

# ----------------- PLOTTING -----------------
# Establish a premium, ultra-modern dark theme
plt.style.use('dark_background')

fig, ax = plt.subplots(figsize=(14, 8), dpi=200)

# Set deep custom charcoal background color for the figure and axis
fig.patch.set_facecolor('#111116')
ax.set_facecolor('#16161E')

# Sleek and vibrant neon curated palette
colors = {
    "Pixel_7_Pro": "#00E5FF", # Neon Electric Cyan
    "mokey": "#D500F9"        # Neon Vivid Purple/Magenta
}

# Plot the traces
for col_name in df.columns:
    color = colors.get(col_name, "#76FF03") # Light green fallback
    
    # Plot line with a glowing hover aesthetic
    ax.plot(df.index, df[col_name], label=f"Device: {col_name}", color=color, 
            linewidth=2.5, marker='o', markersize=6, 
            markeredgecolor=color, markerfacecolor='#16161E', markeredgewidth=1.5)
    
    # Add a soft shaded area beneath the line for high-premium touch
    ax.fill_between(df.index, df[col_name], alpha=0.08, color=color)

# Customizing the grid
ax.grid(True, which='both', linestyle='--', linewidth=0.6, color='#2E2E3C', alpha=0.7)
ax.set_axisbelow(True) # Ensure grids remain underneath data points

# Set titles with clean modern spacing and hierarchy
ax.set_title("Flutter LUCI Perf: complex_layout_scroll_perf average_frame_build_time_millis", 
             fontsize=15, fontweight='bold', color='#FFFFFF', pad=25)
ax.set_ylabel("Frame Build Time (milliseconds)", fontsize=11, fontweight='semibold', color='#B0B0C5', labelpad=15)
ax.set_xlabel("Commit Offset / Date & Time", fontsize=11, fontweight='semibold', color='#B0B0C5', labelpad=20)

# Elegant X-Axis tick labeling
# We will show a tick for every 5th commit to prevent crowding
tick_indices = list(range(0, len(commit_offsets), 5))
if len(commit_offsets) - 1 not in tick_indices:
    tick_indices.append(len(commit_offsets) - 1)

ax.set_xticks([commit_offsets[i] for i in tick_indices])

# Combine offset, hash, and date for beautiful multi-line tick label
tick_labels = []
for idx in tick_indices:
    label = f"Offset {commit_offsets[idx]}\n[{commit_hashes[idx]}]\n{commit_dates[idx]}"
    tick_labels.append(label)
ax.set_xticklabels(tick_labels, fontsize=8.5, color='#A0A0B5')

# Make borders (spines) ultra clean
for spine in ax.spines.values():
    spine.set_color('#2E2E3C')
    spine.set_linewidth(1.0)

# Configure elegant custom legend with rounded corners and translucent backdrop
legend = ax.legend(loc='upper right', frameon=True, facecolor='#1E1E2A', edgecolor='#2E2E3C', 
                   fontsize=10.5, shadow=False)
plt.setp(legend.get_texts(), color='#FFFFFF', fontweight='medium')

# Annotate some premium data details directly on the chart (e.g. min/max points)
for col_name in df.columns:
    y_vals = df[col_name].dropna()
    if not y_vals.empty:
        mean_val = y_vals.mean()
        # Find index and offset of maximum point
        max_idx = y_vals.idxmax()
        max_val = y_vals.max()
        # Draw dotted horizontal average line
        ax.axhline(mean_val, color=colors.get(col_name), linestyle=':', alpha=0.4, linewidth=1.2)
        
        # Max value text callout
        ax.annotate(f"Avg: {mean_val:.2f} ms\nMax: {max_val:.2f} ms", 
                    xy=(max_idx, max_val),
                    xytext=(15, -15), textcoords='offset points',
                    fontsize=8.5, color='#E0E0F0', fontweight='bold',
                    arrowprops=dict(arrowstyle="->", color=colors.get(col_name), alpha=0.6, lw=1.2),
                    bbox=dict(boxstyle="round,pad=0.3", fc="#1E1E2A", ec="#2E2E3C", alpha=0.9))

plt.tight_layout()

# Save image directly to the brain artifacts directory!
chart_local = "charts/complex_layout_scroll_perf_chart.png"
chart_path = "/Users/kevmoo/.gemini/jetski/brain/53de17ee-4467-4d1e-9948-657e084ed2a6/complex_layout_scroll_perf_chart.png"
plt.savefig(chart_local, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
plt.savefig(chart_path, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
print(f"Chart successfully visualised locally to '{chart_local}' and written to brain: {chart_path}!")
