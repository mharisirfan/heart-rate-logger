"""
18-Channel Spectral Fusion Heart Rate Analyzer
Uses ALL channels with intelligent weighting to extract accurate HR
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, detrend
from scipy.fft import rfft, rfftfreq

# ============================================================================
# CHANNEL MAPPING
# ============================================================================
WAVELENGTHS = {
    'A_410nm': 410,   'B_435nm': 435,   'C_460nm': 460,  'D_485nm': 485,
    'E_510nm': 510,   'F_535nm': 535,   'G_560nm': 560,  'H_585nm': 585,
    'R_610nm': 610,   'I_645nm': 645,   'S_680nm': 680,  'J_705nm': 705,
    'T_730nm': 730,   'U_760nm': 760,   'V_810nm': 810,  'W_860nm': 860,
    'K_900nm': 900,   'L_940nm': 940
}

ALL_CHANNELS = list(WAVELENGTHS.keys())
FS = 20  # Sampling frequency (Hz)

# ============================================================================
# SIGNAL PROCESSING
# ============================================================================

def preprocess_signal(signal):
    """Clean and prepare signal"""
    signal = np.asarray(signal, dtype=float)
    # Remove NaN
    signal = signal[~np.isnan(signal)]
    if len(signal) < 50:
        return None
    
    # Remove DC
    signal = detrend(signal)
    
    # Bandpass: 0.67-3 Hz (40-180 BPM)
    nyquist = FS / 2
    low = max(0.67 / nyquist, 0.001)
    high = min(3.0 / nyquist, 0.999)
    b, a = butter(3, [low, high], btype='band')
    signal = filtfilt(b, a, signal)
    
    return signal

def extract_fft_bpm(signal):
    """Extract BPM and signal quality metrics from FFT"""
    if signal is None or len(signal) < 50:
        return None
    
    yf = rfft(signal)
    xf = rfftfreq(len(signal), 1/FS)
    
    # Heart rate range: 0.67-3 Hz
    valid = (xf >= 0.67) & (xf <= 3.0)
    if not np.any(valid):
        return None
    
    xf_valid = xf[valid]
    yf_valid = np.abs(yf[valid])
    
    peak_idx = np.argmax(yf_valid)
    peak_freq = xf_valid[peak_idx]
    peak_mag = yf_valid[peak_idx]
    
    # Signal quality metrics
    baseline = np.median(yf_valid)
    snr = peak_mag / (baseline + 1e-6)
    
    # Power in signal band
    total_power = np.sum(yf_valid)
    peak_power = peak_mag
    power_ratio = peak_power / (total_power + 1e-6)
    
    bpm = peak_freq * 60
    
    return {
        'bpm': bpm,
        'frequency': peak_freq,
        'peak_magnitude': peak_mag,
        'snr': snr,
        'power_ratio': power_ratio,
        'baseline': baseline,
        'total_power': total_power
    }

# ============================================================================
# CHANNEL QUALITY SCORING
# ============================================================================

def score_channel_quality(signal_metrics):
    """Score channel quality (0-100)"""
    if signal_metrics is None:
        return 0
    
    snr = signal_metrics['snr']
    power = signal_metrics['power_ratio']
    
    # SNR weight (higher is better, saturate at 20)
    snr_score = min(snr / 20 * 50, 50)
    
    # Power ratio weight (higher is better, saturate at 0.5)
    power_score = min(power / 0.5 * 50, 50)
    
    quality = snr_score + power_score
    return quality

# ============================================================================
# SPECTRAL FUSION - COMBINE ALL 18 CHANNELS
# ============================================================================

class SpectralFusion:
    def __init__(self, df):
        self.df = df
        self.channel_data = {}
        self.results = {}
    
    def process_all_channels(self):
        """Process and score all 18 channels"""
        print("🔄 Processing all 18 channels...")
        print("=" * 70)
        
        all_bpms = []
        channel_weights = {}
        
        for channel_name in ALL_CHANNELS:
            if channel_name not in self.df.columns:
                continue
            
            # Get raw signal
            signal = self.df[channel_name].values
            
            # Preprocess
            processed = preprocess_signal(signal)
            if processed is None:
                continue
            
            # Extract metrics
            metrics = extract_fft_bpm(processed)
            if metrics is None:
                continue
            
            # Score quality
            quality = score_channel_quality(metrics)
            
            self.channel_data[channel_name] = {
                'raw': signal,
                'processed': processed,
                'metrics': metrics,
                'quality': quality
            }
            
            channel_weights[channel_name] = quality
            all_bpms.append(metrics['bpm'])
            
            wmf = WAVELENGTHS[channel_name]
            print(f"  {channel_name:12} ({wmf:3d}nm):  {metrics['bpm']:6.1f} BPM  |  "
                  f"SNR: {metrics['snr']:6.1f}  |  Quality: {quality:5.1f}")
        
        return channel_weights, all_bpms
    
    def fuse_channels_weighted(self, weights):
        """Fuse channels using quality-weighted averaging"""
        print(f"\n📊 FUSION METHOD 1: WEIGHTED AVERAGE (by SNR + Power)")
        print("=" * 70)
        
        total_weight = sum(weights.values())
        if total_weight == 0:
            return None
        
        weighted_bpm = 0
        for channel, weight in weights.items():
            bpm = self.channel_data[channel]['metrics']['bpm']
            weighted_bpm += (bpm * weight)
        
        weighted_bpm /= total_weight
        
        print(f"  Weighted Average BPM: {weighted_bpm:.1f}")
        print(f"  Total Quality Score: {total_weight:.1f}")
        print(f"  # Channels Used: {len(weights)}")
        
        return weighted_bpm
    
    def fuse_channels_consensus(self, all_bpms):
        """Fuse using robust median + outlier rejection"""
        print(f"\n📊 FUSION METHOD 2: ROBUST CONSENSUS (median + IQR)")
        print("=" * 70)
        
        if not all_bpms:
            return None
        
        all_bpms = np.array(all_bpms)
        
        # Calculate median and IQR
        median_bpm = np.median(all_bpms)
        q1 = np.percentile(all_bpms, 25)
        q3 = np.percentile(all_bpms, 75)
        iqr = q3 - q1
        
        # Outlier bounds (1.5 * IQR)
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        
        # Filter outliers
        valid = (all_bpms >= lower) & (all_bpms <= upper)
        valid_bpms = all_bpms[valid]
        outliers = all_bpms[~valid]
        
        consensus_bpm = np.median(valid_bpms)
        
        print(f"  Consensus BPM (Median): {consensus_bpm:.1f}")
        print(f"  Q1: {q1:.1f}, Q3: {q3:.1f}, IQR: {iqr:.1f}")
        print(f"  Outlier Range: {lower:.1f} - {upper:.1f}")
        print(f"  Valid Channels: {len(valid)} / {len(all_bpms)}")
        if len(outliers) > 0:
            print(f"  Rejected Outliers: {', '.join([f'{x:.0f}' for x in outliers])} BPM")
        
        return consensus_bpm
    
    def fuse_channels_top_performers(self, top_n=5):
        """Fuse using only top N channels by quality"""
        print(f"\n📊 FUSION METHOD 3: TOP {top_n} PERFORMERS")
        print("=" * 70)
        
        # Sort by quality
        sorted_channels = sorted(
            self.channel_data.items(),
            key=lambda x: x[1]['quality'],
            reverse=True
        )
        
        top_channels = sorted_channels[:top_n]
        top_bpms = [ch[1]['metrics']['bpm'] for ch in top_channels]
        
        top_avg = np.mean(top_bpms)
        
        print(f"  Top {top_n} Channels:")
        for i, (ch_name, ch_data) in enumerate(top_channels, 1):
            bpm = ch_data['metrics']['bpm']
            qual = ch_data['quality']
            wl = WAVELENGTHS[ch_name]
            print(f"    {i}. {ch_name} ({wl:3d}nm): {bpm:6.1f} BPM, Quality={qual:5.1f}")
        
        print(f"  Top {top_n} Average: {top_avg:.1f} BPM")
        
        return top_avg
    
    def analyze(self):
        """Run complete analysis with all fusion methods"""
        print("\n" + "=" * 70)
        print("🫀 18-CHANNEL SPECTRAL FUSION ANALYZER")
        print("=" * 70)
        
        # Step 1: Process all channels
        weights, all_bpms = self.process_all_channels()
        
        if not weights:
            print("❌ No valid channels processed")
            return None
        
        # Step 2: Three fusion methods
        weighted = self.fuse_channels_weighted(weights)
        consensus = self.fuse_channels_consensus(all_bpms)
        top5 = self.fuse_channels_top_performers(top_n=5)
        
        # Final consensus
        print(f"\n✅ FINAL RESULTS")
        print("=" * 70)
        print(f"  Method 1 (Weighted):    {weighted:.1f} BPM")
        print(f"  Method 2 (Consensus):   {consensus:.1f} BPM")
        print(f"  Method 3 (Top 5):       {top5:.1f} BPM")
        
        final_bpm = np.median([weighted, consensus, top5])
        print(f"\n  🎯 FINAL HEART RATE:    {final_bpm:.1f} BPM")
        print("=" * 70)
        
        return {
            'weighted': weighted,
            'consensus': consensus,
            'top5': top5,
            'final': final_bpm,
            'all_bpms': all_bpms
        }
    
    def plot_results(self, results):
        """Visualize channel analysis"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # Plot 1: BPM distribution
        ax = axes[0, 0]
        ax.hist(results['all_bpms'], bins=10, color='skyblue', edgecolor='black')
        ax.axvline(results['final'], color='red', linestyle='--', linewidth=2, label=f"Final: {results['final']:.1f}")
        ax.set_xlabel("BPM")
        ax.set_ylabel("Count")
        ax.set_title("Distribution of BPM across 18 Channels")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Plot 2: Channel quality scores
        ax = axes[0, 1]
        channels = list(self.channel_data.keys())
        qualities = [self.channel_data[ch]['quality'] for ch in channels]
        wavelengths = [WAVELENGTHS[ch] for ch in channels]
        
        scatter = ax.scatter(wavelengths, qualities, s=100, c=qualities, cmap='RdYlGn', edgecolors='black')
        ax.set_xlabel("Wavelength (nm)")
        ax.set_ylabel("Quality Score")
        ax.set_title("Channel Quality vs Wavelength")
        ax.grid(True, alpha=0.3)
        plt.colorbar(scatter, ax=ax)
        
        # Plot 3: Fusion method comparison
        ax = axes[1, 0]
        methods = ['Weighted', 'Consensus', 'Top 5', 'Final']
        bpms = [results['weighted'], results['consensus'], results['top5'], results['final']]
        colors = ['skyblue', 'lightgreen', 'lightyellow', 'lightcoral']
        bars = ax.bar(methods, bpms, color=colors, edgecolor='black', linewidth=2)
        for bar, bpm in zip(bars, bpms):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{bpm:.1f}', ha='center', va='bottom', fontweight='bold')
        ax.set_ylabel("BPM")
        ax.set_title("Fusion Method Comparison")
        ax.set_ylim([80, 130])
        ax.grid(True, alpha=0.3, axis='y')
        
        # Plot 4: Top channels
        ax = axes[1, 1]
        sorted_channels = sorted(
            self.channel_data.items(),
            key=lambda x: x[1]['quality'],
            reverse=True
        )[:5]
        top_names = [f"{ch[0]}\n({WAVELENGTHS[ch[0]]}nm)" for ch in sorted_channels]
        top_bpms = [ch[1]['metrics']['bpm'] for ch in sorted_channels]
        bars = ax.bar(range(len(top_names)), top_bpms, color='lightsteelblue', edgecolor='black', linewidth=2)
        ax.set_xticks(range(len(top_names)))
        ax.set_xticklabels(top_names, fontsize=9)
        ax.set_ylabel("BPM")
        ax.set_title("Top 5 Channels by Quality")
        ax.axhline(results['final'], color='red', linestyle='--', linewidth=2, label='Final HR')
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig('18channel_fusion_analysis.png', dpi=150)
        print("\n📈 Plot saved as '18channel_fusion_analysis.png'")
        plt.show()

# ============================================================================
# MAIN
# ============================================================================

def main():
    # Load data
    try:
        df = pd.read_csv('heart_rate_spectral_log.csv')
    except FileNotFoundError:
        print("❌ CSV file not found")
        return
    
    print(f"✅ Loaded {len(df)} samples")
    print(f"📍 Duration: {len(df) / FS:.1f} seconds\n")
    
    # Analyze
    fusion = SpectralFusion(df)
    results = fusion.analyze()
    
    if results:
        fusion.plot_results(results)

if __name__ == "__main__":
    main()
