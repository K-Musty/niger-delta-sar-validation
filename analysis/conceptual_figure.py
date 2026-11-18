#!/usr/bin/env python3
"""
Generate the conceptual diagram of spatial mismatch.
No title, just the visual model.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path

# Setup output path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PNG = OUT_DIR / "figure_5_conceptual.png"

def main():
    fig, ax = plt.subplots(figsize=(8, 8))
    
    # Set limits (representing 5x5 km AOI, centered at 5,5)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect('equal')
    ax.axis('off') # Hide axes

    # 1. Background (Water/Ocean)
    ax.add_patch(patches.Rectangle((0, 0), 10, 10, color='#e0f2f7', zorder=0))
    
    # 2. AOI Box
    aoi = patches.Rectangle((0, 0), 10, 10, linewidth=2, edgecolor='gray', facecolor='none', linestyle='--')
    ax.add_patch(aoi)
    ax.text(9.8, 9.8, "Sentinel-1 AOI (5 × 5 km)", ha='right', va='top', fontsize=10, color='gray', style='italic')

    # 3. Reported Coordinate (Center)
    ax.plot(5, 5, marker='X', markersize=15, color='red', markeredgecolor='darkred', markeredgewidth=1.5, zorder=5)
    ax.annotate("Reported Coordinate\n(NOSDRA Source)", xy=(5, 5), xytext=(1.5, 3.5),
                arrowprops=dict(arrowstyle="->", color='red', lw=1.5, shrinkA=0, shrinkB=5),
                fontsize=10, color='darkred', fontweight='bold', ha='left')

    # 4. Actual Slick (Advected)
    slick = patches.Ellipse((7.5, 7.5), width=3.5, height=1.5, angle=45, 
                            facecolor='black', alpha=0.6, edgecolor='black', lw=1.5, zorder=2)
    ax.add_patch(slick)
    ax.text(8.5, 8.8, "Actual Slick\n(Advected by wind/currents)", ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Wind/Current Arrow
    ax.annotate("", xy=(8.5, 8.5), xytext=(5.5, 5.5),
                arrowprops=dict(arrowstyle="->", color='blue', lw=2, ls='-'))
    ax.text(6.8, 6.8, "Wind /\nCurrent", color='blue', fontsize=9, ha='center', va='center', rotation=45)

    # 5. SAR Anomalies (Detected Clusters)
    np.random.seed(42)
    
    # Some clusters near the actual slick
    ax.scatter([7.2, 7.8, 7.5], [7.2, 7.8, 7.1], s=80, c='black', alpha=0.8, edgecolors='white', linewidth=1, zorder=4)
    
    # Some clusters near the reported coordinate
    ax.scatter([4.8, 5.2, 4.5], [4.8, 5.1, 5.2], s=80, c='black', alpha=0.8, edgecolors='white', linewidth=1, zorder=4)
    
    # Some look-alike clusters far away
    ax.scatter([2.0, 2.5, 3.0, 1.5], [7.0, 7.2, 6.8, 7.5], s=80, c='black', alpha=0.8, edgecolors='white', linewidth=1, zorder=4)
    ax.scatter([7.0, 8.0, 7.5, 8.5], [2.0, 2.5, 1.5, 2.8], s=80, c='black', alpha=0.8, edgecolors='white', linewidth=1, zorder=4)

    # Annotations for anomalies
    ax.annotate("Detected SAR Anomalies", xy=(7.5, 7.1), xytext=(7.5, 5.5),
                arrowprops=dict(arrowstyle="->", color='black', lw=1.5),
                fontsize=10, ha='center')
    
    ax.annotate("Look-alike\n(Low wind / Biogenic)", xy=(2.3, 7.2), xytext=(2.3, 8.5),
                arrowprops=dict(arrowstyle="->", color='gray', lw=1.5),
                fontsize=9, color='gray', ha='center')
    
    ax.annotate("Coordinate\nImprecision", xy=(4.5, 4.7), xytext=(2.5, 3.5),
                arrowprops=dict(arrowstyle="->", color='orange', lw=1.5),
                fontsize=9, color='darkorange', ha='center')

    # 6. Distance Line
    ax.plot([5, 7.5], [5, 7.5], color='green', linestyle=':', linewidth=2)
    ax.text(6.25, 6.25, r"$\Delta$ distance > 1.5 km", color='green', fontsize=10, 
            ha='center', va='center', rotation=45, fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="green", alpha=0.8))

    # NO TITLE HERE
    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', pad_inches=0.1)
    plt.close()
    print(f"Wrote {OUT_PNG}")

if __name__ == "__main__":
    main()
