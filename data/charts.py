import csv
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

PROFILES    = ['baseline', 'latency', 'loss', 'congestion']
LABELS      = ['Baseline', 'High Latency\n(150ms)', 'Packet Loss\n(3%)', 'Congested\n(1.5 Mbps, 200ms±30ms)']
COLORS      = ['#4CAF50', '#2196F3', '#FF9800', '#F44336']
QUALITY_MAP = {'360p': 1, '720p': 2}
THRESHOLD   = 2500  # kbps minimum for 720p

# ── Load CSVs ──────────────────────────────────────────────────────────────
data = {}
for p in PROFILES:
    with open(f'{p}.csv') as f:
        data[p] = list(csv.DictReader(f))

avg_bw         = [sum(float(r['bw_kbps']) for r in data[p]) / 6 for p in PROFILES]
avg_quality    = [sum(QUALITY_MAP[r['quality']] for r in data[p]) / 6 for p in PROFILES]
total_switches = [max(int(r['switches']) for r in data[p]) for p in PROFILES]
bw_ratio       = [bw / THRESHOLD for bw in avg_bw]  # multiple of threshold

# ── Figure: 2×2 ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(2, 2, figsize=(15, 11))
fig.suptitle('How Network Conditions Affect HLS Adaptive Bitrate Streaming',
             fontsize=14, fontweight='bold')
ax1, ax2, ax3, ax4 = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

# ── Chart 1: Bandwidth estimate (log scale) ────────────────────────────────
bars1 = ax1.bar(LABELS, avg_bw, color=COLORS, width=0.5)
ax1.set_yscale('log')
ax1.set_title('Bandwidth Estimate per Profile', fontsize=11)
ax1.set_ylabel('Estimated Bandwidth (kbps, log scale)')
ax1.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{int(x):,}'))
ax1.axhline(THRESHOLD, color='black', linestyle='--', linewidth=1.2)
ax1.text(3.55, THRESHOLD * 1.5, '720p min\n(2,500 kbps)',
         fontsize=8, color='black', va='bottom', ha='right')
ax1.axhspan(0, THRESHOLD, alpha=0.06, color='red')
ax1.text(0.01, 0.06, 'Quality drop zone', transform=ax1.transAxes,
         fontsize=8, color='red', alpha=0.8)
for bar, val in zip(bars1, avg_bw):
    ax1.text(bar.get_x() + bar.get_width() / 2, val * 1.7,
             f'{int(val):,}', ha='center', fontsize=8.5)

# ── Chart 2: Quality outcome ───────────────────────────────────────────────
bars2 = ax2.bar(LABELS, avg_quality, color=COLORS, width=0.5)
ax2.set_title('Resulting Quality Level per Profile', fontsize=11)
ax2.set_ylabel('Quality')
ax2.set_ylim(0, 2.6)
ax2.set_yticks([1, 2])
ax2.set_yticklabels(['360p', '720p'], fontsize=10)
ax2.axhline(1.5, color='gray', linestyle='--', linewidth=0.8)
for bar, val in zip(bars2, avg_quality):
    label = '720p' if val == 2.0 else '360p'
    ax2.text(bar.get_x() + bar.get_width() / 2,
             bar.get_height() + 0.06, label,
             ha='center', fontsize=11, fontweight='bold')

# ── Chart 3: Quality switches ──────────────────────────────────────────────
bars3 = ax3.bar(LABELS, total_switches, color=COLORS, width=0.5)
ax3.set_title('Total Quality Switches over 3 Minutes', fontsize=11)
ax3.set_ylabel('Number of Quality Switches')
ax3.set_ylim(0, max(total_switches) * 1.4)
for bar, val in zip(bars3, total_switches):
    ax3.text(bar.get_x() + bar.get_width() / 2,
             bar.get_height() + 0.15, str(val),
             ha='center', fontsize=12, fontweight='bold')
ax3.text(0.5, 0.91,
         'Congested: 0 switches — locked to 360p immediately\n'
         'Others: hls.js actively probed available bandwidth',
         transform=ax3.transAxes, ha='center', fontsize=8.5, color='#444',
         bbox=dict(boxstyle='round,pad=0.35', facecolor='#f5f5f5', edgecolor='#bbb'))

# ── Chart 4: Bandwidth as multiple of 720p threshold ──────────────────────
bar_colors4 = ['#4CAF50' if r >= 1.0 else '#F44336' for r in bw_ratio]
bars4 = ax4.bar(LABELS, bw_ratio, color=bar_colors4, width=0.5)
ax4.set_yscale('log')
ax4.set_title('Bandwidth as Multiple of 720p Minimum', fontsize=11)
ax4.set_ylabel('× of 2,500 kbps required (log scale)')
ax4.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f'{x:.2f}×' if x < 1 else f'{x:.0f}×'))
ax4.axhline(1.0, color='black', linestyle='--', linewidth=1.2)
ax4.text(3.55, 1.5, '1× = exactly\nenough for 720p',
         fontsize=8, color='black', va='bottom', ha='right')
ax4.axhspan(0, 1.0, alpha=0.06, color='red')
ax4.text(0.01, 0.06, 'Below minimum', transform=ax4.transAxes,
         fontsize=8, color='red', alpha=0.8)
for bar, val in zip(bars4, bw_ratio):
    label = f'{val:.2f}×' if val < 1 else f'{val:.0f}×'
    ax4.text(bar.get_x() + bar.get_width() / 2, val * 1.7,
             label, ha='center', fontsize=8.5)

plt.tight_layout()
plt.savefig('charts.png', dpi=150, bbox_inches='tight')
print('Saved charts.png')
plt.show()
