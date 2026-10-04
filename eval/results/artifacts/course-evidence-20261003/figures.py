"""Render measured benchmark results with separate evidence scopes."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent
DATA = json.loads((BASE / 'figure-data.json').read_text())
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'pdf.fonttype': 42, 'svg.fonttype': 'none'})
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), gridspec_kw={'width_ratios': [1.55, 1]})
ax = axes[0]
labels = ['Tool-enabled\nOriginal gold', 'Tool-enabled\nPost-hoc gold', 'No-tool\nOriginal gold']
counts = DATA['language_task_passes']
values = [100 * n / DATA['language_task_denominator'] for n in counts]
bars = ax.bar(labels, values, color=['#5B7894', '#236B65', '#ADB8C2'], width=0.62)
ax.axhline(90, color='#A45C41', linestyle='--', linewidth=1.3)
ax.text(2.42, 92, '90% task target', ha='right', color='#873F2A', fontsize=9)
for bar, count, value in zip(bars, counts, values, strict=True):
    ax.text(bar.get_x() + bar.get_width()/2, value + 3, f'{count}/33\n{value:.1f}%', ha='center', fontsize=10)
ax.set_ylim(0, 108);ax.set_ylabel('Applicable language tasks passed (%)');ax.set_title('Task quality: saved live observations', loc='left', fontsize=12, weight='bold')
ax=axes[1]
ax.barh(['Public-output claims'], [98], color='#236B65', label='Supported: 98')
ax.barh(['Public-output claims'], [2], left=[98], color='#D9A45B', label='Unknown: 2')
ax.axvline(95, color='#A45C41', linestyle='--', linewidth=1.3)
ax.set_xlim(0, 105);ax.set_xlabel('Conservative claim denominator (100)');ax.set_title('Bounded claim support', loc='left', fontsize=12, weight='bold')
ax.text(49, 0, '98 supported', color='white', ha='center', va='center', weight='bold');ax.set_yticks([])
ax.legend(loc='lower left', bbox_to_anchor=(-0.02, -0.52), frameon=False, fontsize=9)
fig.suptitle('FEWIA benchmark · 3 October 2026', x=0.08, ha='left', fontsize=15, weight='bold')
fig.text(0.08, 0.02, 'Same saved observations for original and post-hoc tool scores; no new inference. Claims exclude 10 supported refusals.\nThe 95% claim target applies only to the bounded public-output extractor. Task target fails under both gold versions.', fontsize=8.5, color='#45515C')
fig.subplots_adjust(left=0.08,right=0.98,top=0.80,bottom=0.38,wspace=0.35)
for extension in ['png','svg','pdf']:
    fig.savefig(BASE / ('benchmark-quality.' + extension), dpi=180)
plt.close(fig)
