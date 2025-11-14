#!/usr/bin/env python3
# /// script
# dependencies = [
#   "pandas>=2.0.0",
#   "matplotlib>=3.7.0",
#   "numpy>=1.24.0",
# ]
# ///

"""
Rolling Sum Analysis Tool
Analyzes CSV output from the GStreamer rollingsum plugin
Usage: uv run analyze_sma.py [csv_file]
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from datetime import datetime
import shutil


def analyze_csv(csv_file: str = "output.csv"):
    """Analyze the rolling sum CSV data and generate insights."""
    
    # Create output directory
    output_dir = Path("results/debug")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Read the CSV
    try:
        df = pd.read_csv(csv_file)
    except FileNotFoundError:
        print(f"Error: CSV file '{csv_file}' not found.")
        sys.exit(1)
    
    # Copy input CSV to results directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_name = Path(csv_file).stem
    archived_csv = output_dir / f"{csv_name}_{timestamp}.csv"
    shutil.copy(csv_file, archived_csv)
    
    print("=" * 80)
    print(f"ROLLING SUM ANALYSIS - {csv_file}")
    print("=" * 80)
    print()
    
    # Basic statistics
    print("DATASET OVERVIEW:")
    print(f"  Total frames: {len(df)}")
    print(f"  Frames dropped: {df['dropped'].sum()}")
    print(f"  Frames kept: {(df['dropped'] == 0).sum()}")
    print(f"  Drop rate: {df['dropped'].mean() * 100:.2f}%")
    print()
    
    # Column mean statistics
    print("COLUMN MEAN STATISTICS:")
    print(f"  Min: {df['column_mean'].min():.6f}")
    print(f"  Max: {df['column_mean'].max():.6f}")
    print(f"  Range: {df['column_mean'].max() - df['column_mean'].min():.6f}")
    print(f"  Mean: {df['column_mean'].mean():.6f}")
    print(f"  Std Dev: {df['column_mean'].std():.6f}")
    print()
    
    # Deviation statistics
    print("DEVIATION STATISTICS:")
    print(f"  Min deviation: {df['deviation'].min():.6f}")
    print(f"  Max deviation: {df['deviation'].max():.6f}")
    print(f"  Mean deviation: {df['deviation'].mean():.6f}")
    print(f"  Std dev of deviations: {df['deviation'].std():.6f}")
    print()
    
    # Normalized deviation statistics
    print("NORMALIZED DEVIATION STATISTICS:")
    print(f"  Min: {df['normalized_deviation'].min():.8f}")
    print(f"  Max: {df['normalized_deviation'].max():.8f}")
    print(f"  Mean: {df['normalized_deviation'].mean():.8f}")
    print(f"  Median: {df['normalized_deviation'].median():.8f}")
    print(f"  95th percentile: {df['normalized_deviation'].quantile(0.95):.8f}")
    print(f"  99th percentile: {df['normalized_deviation'].quantile(0.99):.8f}")
    print()
    
    # Threshold recommendations
    print("THRESHOLD RECOMMENDATIONS:")
    print("  (Based on normalized deviation percentiles)")
    print()
    
    percentiles = [50, 75, 90, 95, 99]
    for p in percentiles:
        threshold = df['normalized_deviation'].quantile(p / 100)
        frames_dropped = (df['normalized_deviation'] > threshold).sum()
        drop_rate = (frames_dropped / len(df)) * 100
        print(f"  {p}th percentile: threshold={threshold:.8f}")
        print(f"    → Would drop {frames_dropped} frames ({drop_rate:.1f}%)")
        print()
    
    # Suggest optimal thresholds based on standard deviations
    mean_norm_dev = df['normalized_deviation'].mean()
    std_norm_dev = df['normalized_deviation'].std()
    
    print("STANDARD DEVIATION-BASED THRESHOLDS:")
    for n in [1, 2, 3]:
        threshold = mean_norm_dev + (n * std_norm_dev)
        frames_dropped = (df['normalized_deviation'] > threshold).sum()
        drop_rate = (frames_dropped / len(df)) * 100
        print(f"  Mean + {n}σ: threshold={threshold:.8f}")
        print(f"    → Would drop {frames_dropped} frames ({drop_rate:.1f}%)")
        print()
    
    # Create visualizations
    plot_file = create_plots(df, csv_file, output_dir, timestamp)
    
    print("=" * 80)
    print("OUTPUT FILES:")
    print(f"  CSV Archive: {archived_csv}")
    print(f"  Analysis Plot: {plot_file}")
    print("=" * 80)


def create_plots(df: pd.DataFrame, csv_file: str, output_dir: Path, timestamp: str) -> Path:
    """Create analysis plots and return the output file path."""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Rolling Sum Analysis - {csv_file}', fontsize=16, fontweight='bold')
    
    # Plot 1: Column mean over time
    ax1 = axes[0, 0]
    ax1.plot(df['frame'], df['column_mean'], label='Column Mean', linewidth=1)
    ax1.plot(df['frame'], df['rolling_mean'], label='Rolling Mean', linewidth=1, alpha=0.7)
    ax1.set_xlabel('Frame')
    ax1.set_ylabel('Pixel Value')
    ax1.set_title('Column Mean vs Rolling Mean')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Deviation over time
    ax2 = axes[0, 1]
    ax2.plot(df['frame'], df['deviation'], linewidth=1, color='orange')
    ax2.axhline(y=df['deviation'].mean(), color='r', linestyle='--', 
                label=f'Mean: {df["deviation"].mean():.4f}')
    ax2.axhline(y=df['deviation'].quantile(0.95), color='g', linestyle='--',
                label=f'95th: {df["deviation"].quantile(0.95):.4f}')
    ax2.set_xlabel('Frame')
    ax2.set_ylabel('Absolute Deviation')
    ax2.set_title('Deviation from Rolling Mean')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Normalized deviation distribution
    ax3 = axes[1, 0]
    ax3.hist(df['normalized_deviation'], bins=50, edgecolor='black', alpha=0.7)
    ax3.axvline(x=df['normalized_deviation'].mean(), color='r', linestyle='--',
                label=f'Mean: {df["normalized_deviation"].mean():.6f}')
    ax3.axvline(x=df['normalized_deviation'].median(), color='g', linestyle='--',
                label=f'Median: {df["normalized_deviation"].median():.6f}')
    ax3.set_xlabel('Normalized Deviation')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Normalized Deviation Distribution')
    ax3.legend()
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Plot 4: Cumulative distribution
    ax4 = axes[1, 1]
    sorted_norm_dev = np.sort(df['normalized_deviation'])
    cumulative = np.arange(1, len(sorted_norm_dev) + 1) / len(sorted_norm_dev) * 100
    ax4.plot(sorted_norm_dev, cumulative, linewidth=2)
    
    # Mark percentiles
    for p in [50, 75, 90, 95, 99]:
        threshold = df['normalized_deviation'].quantile(p / 100)
        ax4.axvline(x=threshold, color='red', linestyle=':', alpha=0.5)
        ax4.text(threshold, p, f'{p}th', rotation=90, va='bottom', ha='right', fontsize=8)
    
    ax4.set_xlabel('Normalized Deviation')
    ax4.set_ylabel('Cumulative Percentage (%)')
    ax4.set_title('Cumulative Distribution Function')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the plot to results/debug
    csv_name = Path(csv_file).stem
    output_file = output_dir / f"{csv_name}_analysis_{timestamp}.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n✓ Saved analysis plot to: {output_file}\n")
    
    return output_file


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "output.csv"
    
    if not Path(csv_file).exists():
        print(f"Error: File '{csv_file}' not found.")
        print(f"Usage: uv run analyze_sma.py [csv_file]")
        sys.exit(1)
    
    analyze_csv(csv_file)