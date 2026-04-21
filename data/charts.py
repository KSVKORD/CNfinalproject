import csv
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

PROFILES    = ['baseline', 'latency', 'loss', 'congestion']
LABELS      = ['Baseline', 'High Latency\n(150ms)', 'Packet Loss\n(3%)', 'Congested\n(1.5 Mbps cap)']
COLORS      = ['#4CAF50', '#2196F3', '#FF9800', '#F44336']
QUALITY_MAP = {'360p': 1, '720p': 2}

# ── Load CSVs ──────────────────────────────────────────────────────────────
data = {}
for p in PROFILES:
    with open(f'{p}.csv') as f:
        data[p] = list(csv.DictReader(f))

avg_bw      = [sum(float(r['bw_kbps']) for r in data[p]) / 6 for p in PROFILES]
avg_quality = [sum(QUALITY_MAP[r['quality']] for r in data[p]) / 6 for p in PROFILES]

THRESHOLD = 2500  # kbps minimum for 720p

# ── Figure ─────────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
fig.suptitle('How Network Conditions Affect HLS Adaptive Bitrate Streaming',
             fontsize=13, fontweight='bold', y=1.01)

# ── Chart 1: Bandwidth estimate (log scale) ────────────────────────────────
bars = ax1.bar(LABELS, avg_bw, color=COLORS, width=0.5)
ax1.set_yscale('log')
ax1.set_title('Bandwidth Estimate per Profile', fontsize=11)
ax1.set_ylabel('Estimated Bandwidth (kbps, log scale)')
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))

# Threshold line
ax1.axhline(THRESHOLD, color='black', linestyle='--', linewidth=1.2)
ax1.text(3.55, THRESHOLD * 1.4, '720p min\n(2,500 kbps)',
         fontsize=8, color='black', va='bottom', ha='right')

# Value labels on bars
for bar, val in zip(bars, avg_bw):
    ax1.text(bar.get_x() + bar.get_width() / 2,
             val * 1.6,
             f'{int(val):,}', ha='center', fontsize=8.5)

# Shade the "danger zone" below threshold
ax1.axhspan(0, THRESHOLD, alpha=0.06, color='red')
ax1.text(0.01, 0.08, 'Quality drop zone', transform=ax1.transAxes,
         fontsize=8, color='red', alpha=0.7)

# ── Chart 2: Quality outcome ───────────────────────────────────────────────
bars2 = ax2.bar(LABELS, avg_quality, color=COLORS, width=0.5)
ax2.set_title('Resulting Quality Level per Profile', fontsize=11)
ax2.set_ylabel('Quality')
ax2.set_ylim(0, 2.6)
ax2.set_yticks([1, 2])
ax2.set_yticklabels(['360p', '720p'], fontsize=10)
ax2.axhline(1.5, color='gray', linestyle='--', linewidth=0.8)

for bar, p, val in zip(bars2, PROFILES, avg_quality):
    label = '720p' if val == 2.0 else '360p'
    ax2.text(bar.get_x() + bar.get_width() / 2,
             bar.get_height() + 0.06, label, ha='center', fontsize=10,
             fontweight='bold')

plt.tight_layout()
plt.savefig('charts.png', dpi=150, bbox_inches='tight')
print('Saved charts.png')
plt.show()
