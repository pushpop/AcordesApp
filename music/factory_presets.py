"""
ABOUTME: Factory preset generator for the Acordes synthesizer
ABOUTME: Provides 128 professionally programmed presets across 8 categories
"""

from typing import Dict, Any, List

# Discrete key tracking steps matching the UI selector (0%/25%/50%/75%/100%)
_KT_STEPS = [0.0, 0.25, 0.5, 0.75, 1.0]


def _snap_key_tracking(val: float) -> float:
    """Snap a continuous key_tracking value to the nearest discrete step."""
    return min(_KT_STEPS, key=lambda s: abs(s - val))


def create_preset(
    name: str,
    description: str,
    waveform: str = "sine",
    octave: int = 0,
    noise_level: float = 0.0,
    cutoff: float = 400.0,
    hpf_cutoff: float = 20.0,
    resonance: float = 0.0,
    hpf_resonance: float = 0.0,
    key_tracking: float = 0.5,
    attack: float = 0.01,
    decay: float = 0.2,
    sustain: float = 0.7,
    release: float = 0.3,
    lfo_shape: str = "sine",
    lfo_freq: float = 1.0,
    lfo_depth: float = 0.0,
    lfo_target: str = "vcf",
    chorus_mix: float = 0.0,
    chorus_delay: float = 30.0,
    chorus_rate: float = 1.5,
    chorus_depth: float = 0.8,
    delay_mix: float = 0.0,
    delay_feedback: float = 0.0,
    delay_time: float = 0.5,
    arp_enabled: bool = False,
    arp_mode: str = "up",
    arp_rate: float = 8.0,
    arp_range: int = 1,
    voice_type: str = "poly",
    feg_attack:  float = 0.01,
    feg_decay:   float = 0.3,
    feg_sustain: float = 0.0,
    feg_release: float = 0.3,
    feg_amount:  float = 0.0,
) -> Dict[str, Any]:
    """Helper function to create a preset dict."""
    return {
        "name": name,
        "description": description,
        "waveform": waveform,
        "octave": octave,
        "noise_level": noise_level,
        "cutoff": cutoff,
        "hpf_cutoff": hpf_cutoff,
        "resonance": resonance,
        "hpf_resonance": hpf_resonance,
        "key_tracking": _snap_key_tracking(key_tracking),
        "attack": attack,
        "decay": decay,
        "sustain": sustain,
        "release": release,
        "lfo_shape": lfo_shape,
        "lfo_freq": lfo_freq,
        "lfo_depth": lfo_depth,
        "lfo_target": lfo_target,
        "chorus_mix": chorus_mix,
        "chorus_delay": chorus_delay,
        "chorus_rate": chorus_rate,
        "chorus_depth": chorus_depth,
        "delay_mix": delay_mix,
        "delay_feedback": delay_feedback,
        "delay_time": delay_time,
        "arp_enabled": arp_enabled,
        "arp_mode": arp_mode,
        "arp_rate": arp_rate,
        "arp_range": arp_range,
        "voice_type": voice_type,
        "feg_attack":  feg_attack,
        "feg_decay":   feg_decay,
        "feg_sustain": feg_sustain,
        "feg_release": feg_release,
        "feg_amount":  feg_amount,
    }


def get_factory_presets() -> Dict[str, Dict[str, Any]]:
    """Return all factory presets organized by category."""

    presets = {
        "bass": {
            "name": "Bass",
            "icon": "🔊",
            "presets": [
                create_preset("Deep Sub", "Subharmonic bass for dub and electronic", waveform="sine", octave=-2, cutoff=60.0, resonance=0.4, key_tracking=0.3, attack=0.8, decay=1.2, sustain=0.95, release=1.5, lfo_freq=0.3, lfo_depth=0.15, lfo_target="vcf", voice_type="poly"),
                create_preset("Wobble Bass", "Modulated bass with moving filter", waveform="sawtooth", octave=-1, cutoff=80.0, resonance=0.65, key_tracking=0.4, attack=0.05, decay=0.8, sustain=0.9, release=1.0, lfo_freq=2.5, lfo_depth=0.6, lfo_target="vcf", voice_type="poly"),
                create_preset("Reese Bass", "Classic 90s detuned sawtooth bass", waveform="sawtooth", octave=-1, cutoff=100.0, resonance=0.7, key_tracking=0.2, attack=0.1, decay=0.5, sustain=0.92, release=0.8, lfo_freq=0.8, lfo_depth=0.3, lfo_target="vco", chorus_mix=0.4, chorus_delay=35.0, chorus_rate=1.2, chorus_depth=0.6, voice_type="poly"),
                create_preset("Sine Bass", "Pure sine wave bass, warm and focused", waveform="sine", octave=-1, cutoff=150.0, resonance=0.3, key_tracking=0.5, attack=0.3, decay=1.0, sustain=0.98, release=1.2, lfo_shape="triangle", lfo_freq=0.5, lfo_depth=0.1, lfo_target="vcf", delay_mix=0.08, delay_feedback=0.25, voice_type="poly"),
                create_preset("Massive Bass", "Thick, distorted bass with resonance", waveform="sawtooth", octave=-1, noise_level=0.05, cutoff=120.0, resonance=0.8, key_tracking=0.3, attack=0.2, decay=0.6, sustain=0.93, release=1.1, lfo_freq=1.5, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.15, chorus_delay=32.0, chorus_rate=1.3, chorus_depth=0.5, voice_type="poly"),
                create_preset("Dark Bass", "Low-pass filtered darkness", waveform="triangle", octave=-2, noise_level=0.02, cutoff=50.0, resonance=0.5, key_tracking=0.2, attack=0.4, decay=1.5, sustain=0.9, release=2.0, lfo_freq=0.4, lfo_depth=0.2, lfo_target="vcf", delay_mix=0.12, delay_feedback=0.35, voice_type="poly"),
                create_preset("Punchy Bass", "Tight bass with quick attack", waveform="sawtooth", octave=-1, cutoff=140.0, resonance=0.6, key_tracking=0.35, attack=0.02, decay=0.3, sustain=0.85, release=0.6, lfo_freq=3.5, lfo_depth=0.4, lfo_target="vcf", voice_type="poly"),
                create_preset("Smooth Bass", "Silky smooth with slow modulation", waveform="sine", octave=-1, cutoff=180.0, resonance=0.2, key_tracking=0.6, attack=0.5, decay=1.2, sustain=1.0, release=1.5, lfo_freq=0.3, lfo_depth=0.08, lfo_target="vco", chorus_mix=0.2, chorus_delay=35.0, chorus_rate=1.0, chorus_depth=0.7, delay_mix=0.06, delay_feedback=0.2, voice_type="poly"),
                create_preset("Acid Bass", "TB-303 style acid bass", waveform="sawtooth", octave=-1, cutoff=90.0, resonance=0.75, key_tracking=0.25, attack=0.0, decay=0.9, sustain=0.0, release=0.3, lfo_freq=2.0, lfo_depth=0.5, lfo_target="vcf", voice_type="poly"),
                create_preset("Filtered Bass", "Heavy filter sweep bass", waveform="triangle", octave=-1, noise_level=0.03, cutoff=70.0, resonance=0.7, key_tracking=0.3, attack=0.08, decay=0.7, sustain=0.88, release=0.9, lfo_freq=1.8, lfo_depth=0.55, lfo_target="vcf", chorus_mix=0.05, chorus_delay=33.0, chorus_rate=1.4, chorus_depth=0.4, delay_mix=0.03, delay_feedback=0.18, voice_type="poly"),
                create_preset("Vintage Bass", "70s style warm bass", waveform="sine", octave=-1, noise_level=0.01, cutoff=110.0, resonance=0.35, key_tracking=0.4, attack=0.15, decay=1.1, sustain=0.96, release=1.3, lfo_freq=0.6, lfo_depth=0.15, lfo_target="vco", chorus_mix=0.25, chorus_delay=36.0, chorus_rate=0.9, chorus_depth=0.6, delay_mix=0.07, delay_feedback=0.22, voice_type="poly"),
                create_preset("Gritty Bass", "Noisy, dirty bass", waveform="sawtooth", octave=-1, noise_level=0.15, cutoff=100.0, resonance=0.55, key_tracking=0.35, attack=0.05, decay=0.5, sustain=0.85, release=0.7, lfo_freq=2.2, lfo_depth=0.35, lfo_target="vcf", chorus_mix=0.1, chorus_delay=31.0, chorus_rate=1.6, chorus_depth=0.45, delay_mix=0.01, delay_feedback=0.1, voice_type="poly"),
                create_preset("Hollow Bass", "Thin, hollow bass texture", waveform="triangle", octave=-1, cutoff=130.0, resonance=0.4, key_tracking=0.5, attack=0.2, decay=0.8, sustain=0.8, release=1.0, lfo_freq=1.2, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.3, chorus_delay=34.0, chorus_rate=1.1, chorus_depth=0.7, delay_mix=0.05, delay_feedback=0.2, voice_type="poly"),
                create_preset("Thumpy Bass", "Emphasis on initial attack", waveform="sawtooth", octave=-1, noise_level=0.02, cutoff=95.0, resonance=0.5, key_tracking=0.3, attack=0.01, decay=0.2, sustain=0.7, release=0.5, lfo_freq=4.0, lfo_depth=0.3, lfo_target="vcf", voice_type="poly"),
                create_preset("Mellow Bass", "Soft, mellow bass tone", waveform="sine", octave=-1, cutoff=200.0, resonance=0.15, key_tracking=0.7, attack=0.35, decay=1.3, sustain=1.0, release=1.8, lfo_shape="triangle", lfo_freq=0.4, lfo_depth=0.06, lfo_target="vco", chorus_mix=0.3, chorus_delay=37.0, chorus_rate=0.8, chorus_depth=0.8, delay_mix=0.08, delay_feedback=0.25, voice_type="poly"),
                create_preset("Synth Bass", "Synthesized bass with character", waveform="sawtooth", octave=-1, noise_level=0.08, cutoff=115.0, resonance=0.65, key_tracking=0.4, attack=0.12, decay=0.7, sustain=0.9, release=0.95, lfo_freq=2.8, lfo_depth=0.45, lfo_target="vcf", chorus_mix=0.12, chorus_delay=32.0, chorus_rate=1.25, chorus_depth=0.55, delay_mix=0.02, delay_feedback=0.12, voice_type="poly"),
            ]
        },
        "leads": {
            "name": "Leads",
            "icon": "🎸",
            "presets": [
                create_preset("Bright Lead", "Punchy, bright lead sound", waveform="sawtooth", octave=1, cutoff=3000.0, resonance=0.45, key_tracking=0.8, attack=0.02, decay=0.15, sustain=0.6, release=0.25, lfo_freq=4.5, lfo_depth=0.25, lfo_target="vcf", voice_type="mono"),
                create_preset("Electric Piano", "Warm, warm lead with quick attack", waveform="sine", octave=1, cutoff=2500.0, resonance=0.2, key_tracking=0.9, attack=0.01, decay=0.5, sustain=0.8, release=0.4, lfo_freq=0.5, lfo_depth=0.1, lfo_target="vcf", chorus_mix=0.3, chorus_delay=25.0, chorus_rate=1.5, chorus_depth=0.6, voice_type="mono"),
                create_preset("Soprano Voice", "Airy lead with pitch bend character", waveform="triangle", octave=1, cutoff=2800.0, resonance=0.3, key_tracking=0.85, attack=0.05, decay=0.3, sustain=0.7, release=0.35, lfo_shape="triangle", lfo_freq=2.0, lfo_depth=0.15, lfo_target="vco", voice_type="mono"),
                create_preset("Acid Lead", "Aggressive acid lead", waveform="sawtooth", octave=1, cutoff=2000.0, resonance=0.8, key_tracking=0.6, attack=0.01, decay=0.4, sustain=0.5, release=0.2, lfo_freq=3.0, lfo_depth=0.4, lfo_target="vcf", voice_type="mono"),
                create_preset("Synth Solo", "Classic synth lead", waveform="sawtooth", octave=1, cutoff=3500.0, resonance=0.5, key_tracking=0.7, attack=0.03, decay=0.2, sustain=0.75, release=0.3, lfo_freq=2.2, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.1, chorus_delay=28.0, chorus_rate=1.2, chorus_depth=0.5, voice_type="mono"),
                create_preset("Stab Lead", "Sharp, staccato lead", waveform="square", octave=1, cutoff=3200.0, resonance=0.4, key_tracking=0.75, attack=0.005, decay=0.1, sustain=0.4, release=0.15, lfo_freq=5.5, lfo_depth=0.3, lfo_target="vcf", voice_type="mono"),
                create_preset("Smooth Lead", "Warm, smooth lead", waveform="sine", octave=1, cutoff=2200.0, resonance=0.25, key_tracking=0.85, attack=0.04, decay=0.25, sustain=0.8, release=0.4, lfo_freq=1.5, lfo_depth=0.12, lfo_target="vcf", delay_mix=0.05, delay_feedback=0.15, voice_type="mono"),
                create_preset("Screamer", "High-pitched, resonant lead", waveform="sawtooth", octave=2, cutoff=4000.0, resonance=0.7, key_tracking=0.8, attack=0.01, decay=0.2, sustain=0.7, release=0.25, lfo_freq=4.0, lfo_depth=0.35, lfo_target="vcf", voice_type="mono"),
                create_preset("Glass Bell", "Crystalline lead tone", waveform="triangle", octave=1, cutoff=3800.0, resonance=0.35, key_tracking=0.9, attack=0.02, decay=0.6, sustain=0.6, release=0.5, lfo_freq=1.8, lfo_depth=0.15, lfo_target="vco", chorus_mix=0.4, chorus_delay=30.0, chorus_rate=1.3, chorus_depth=0.7, voice_type="mono"),
                create_preset("Whistle", "Pure, whistling lead", waveform="sine", octave=1, noise_level=0.02, cutoff=3000.0, resonance=0.15, key_tracking=0.95, attack=0.08, decay=0.3, sustain=0.85, release=0.35, lfo_shape="triangle", lfo_freq=2.5, lfo_depth=0.08, lfo_target="vco", voice_type="mono"),
                create_preset("Brassy", "Bright, brassy lead", waveform="sawtooth", octave=1, noise_level=0.03, cutoff=3500.0, resonance=0.6, key_tracking=0.7, attack=0.02, decay=0.3, sustain=0.75, release=0.4, lfo_freq=3.5, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.15, chorus_delay=26.0, chorus_rate=1.4, chorus_depth=0.45, voice_type="mono"),
                create_preset("Oboe", "Reedy, expressive lead", waveform="square", octave=1, noise_level=0.04, cutoff=2600.0, resonance=0.4, key_tracking=0.8, attack=0.06, decay=0.2, sustain=0.7, release=0.3, lfo_freq=2.0, lfo_depth=0.2, lfo_target="vcf", delay_mix=0.03, delay_feedback=0.1, voice_type="mono"),
                create_preset("Violin", "Smooth, singing lead", waveform="sine", octave=1, cutoff=2400.0, resonance=0.3, key_tracking=0.85, attack=0.08, decay=0.2, sustain=0.9, release=0.5, lfo_shape="triangle", lfo_freq=1.2, lfo_depth=0.1, lfo_target="vcf", chorus_mix=0.25, chorus_delay=32.0, chorus_rate=0.9, chorus_depth=0.6, voice_type="mono"),
                create_preset("Flute", "Airy, light lead", waveform="triangle", octave=2, cutoff=3200.0, resonance=0.2, key_tracking=0.9, attack=0.06, decay=0.2, sustain=0.75, release=0.3, lfo_freq=1.8, lfo_depth=0.12, lfo_target="vco", voice_type="mono"),
                create_preset("Metallic", "Shimmering metallic lead", waveform="square", octave=1, cutoff=4200.0, resonance=0.65, key_tracking=0.75, attack=0.02, decay=0.25, sustain=0.65, release=0.2, lfo_freq=5.0, lfo_depth=0.4, lfo_target="vcf", chorus_mix=0.2, chorus_delay=27.0, chorus_rate=1.6, chorus_depth=0.55, voice_type="mono"),
                create_preset("Pulse", "PWM-style lead", waveform="square", octave=1, cutoff=3000.0, resonance=0.5, key_tracking=0.8, attack=0.015, decay=0.18, sustain=0.72, release=0.28, lfo_freq=3.8, lfo_depth=0.3, lfo_target="vcf", delay_mix=0.04, delay_feedback=0.12, voice_type="mono"),
            ]
        },
        "pads": {
            "name": "Pads",
            "icon": "🌊",
            "presets": [
                create_preset("Warm Pad", "Soft, warm atmospheric pad", waveform="sine", octave=0, cutoff=1500.0, resonance=0.25, key_tracking=0.5, attack=1.5, decay=2.0, sustain=1.0, release=2.5, lfo_shape="triangle", lfo_freq=0.4, lfo_depth=0.15, lfo_target="vcf", chorus_mix=0.5, chorus_delay=40.0, chorus_rate=1.0, chorus_depth=0.8, delay_mix=0.15, delay_feedback=0.3),
                create_preset("Lush Pad", "Lush, full-spectrum pad", waveform="sawtooth", octave=-1, noise_level=0.02, cutoff=2000.0, resonance=0.35, key_tracking=0.4, attack=2.0, decay=1.5, sustain=1.0, release=3.0, lfo_shape="sine", lfo_freq=0.3, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.6, chorus_delay=35.0, chorus_rate=1.2, chorus_depth=0.9, delay_mix=0.2, delay_feedback=0.35),
                create_preset("String Pad", "Emulated string ensemble", waveform="sine", octave=0, cutoff=1800.0, resonance=0.2, key_tracking=0.6, attack=1.8, decay=1.8, sustain=1.0, release=2.8, lfo_freq=0.35, lfo_depth=0.12, lfo_target="vco", chorus_mix=0.7, chorus_delay=38.0, chorus_rate=0.85, chorus_depth=0.85, delay_mix=0.1, delay_feedback=0.25),
                create_preset("Choir Pad", "Vocal pad with wide spread", waveform="triangle", octave=0, cutoff=2200.0, resonance=0.3, key_tracking=0.5, attack=2.2, decay=2.0, sustain=0.95, release=3.2, lfo_shape="sine", lfo_freq=0.25, lfo_depth=0.18, lfo_target="vcf", chorus_mix=0.8, chorus_delay=42.0, chorus_rate=1.1, chorus_depth=0.95, delay_mix=0.12, delay_feedback=0.28),
                create_preset("Ethereal", "Ethereal, floating pad", waveform="sine", octave=1, cutoff=1600.0, resonance=0.15, key_tracking=0.3, attack=3.0, decay=2.5, sustain=0.98, release=4.0, lfo_shape="triangle", lfo_freq=0.2, lfo_depth=0.1, lfo_target="vco", chorus_mix=0.7, chorus_delay=45.0, chorus_rate=0.95, chorus_depth=0.9, delay_mix=0.18, delay_feedback=0.32),
                create_preset("Electric Pad", "Warm electric pad", waveform="sawtooth", octave=0, cutoff=1900.0, resonance=0.4, key_tracking=0.45, attack=1.2, decay=1.5, sustain=0.95, release=2.2, lfo_freq=0.45, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.5, chorus_delay=36.0, chorus_rate=1.3, chorus_depth=0.7, delay_mix=0.08, delay_feedback=0.2),
                create_preset("Glass Pad", "Crystalline, glass-like pad", waveform="triangle", octave=1, cutoff=2400.0, resonance=0.25, key_tracking=0.6, attack=1.5, decay=2.0, sustain=1.0, release=2.8, lfo_freq=0.5, lfo_depth=0.15, lfo_target="vco", chorus_mix=0.6, chorus_delay=41.0, chorus_rate=1.15, chorus_depth=0.8, delay_mix=0.14, delay_feedback=0.27),
                create_preset("Bell Pad", "Warm, bell-like pad", waveform="sine", octave=0, cutoff=1700.0, resonance=0.2, key_tracking=0.5, attack=2.5, decay=3.0, sustain=0.92, release=3.5, lfo_shape="sine", lfo_freq=0.3, lfo_depth=0.12, lfo_target="vcf", chorus_mix=0.65, chorus_delay=39.0, chorus_rate=1.05, chorus_depth=0.85, delay_mix=0.16, delay_feedback=0.3),
                create_preset("Analog Pad", "Classic analog synth pad", waveform="sawtooth", octave=-1, cutoff=1600.0, resonance=0.5, key_tracking=0.4, attack=1.8, decay=1.5, sustain=0.98, release=2.5, lfo_freq=0.4, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.45, chorus_delay=33.0, chorus_rate=1.25, chorus_depth=0.65, delay_mix=0.1, delay_feedback=0.22),
                create_preset("Synth Pad", "Bright synth pad", waveform="sawtooth", octave=0, noise_level=0.01, cutoff=2100.0, resonance=0.35, key_tracking=0.5, attack=1.5, decay=1.8, sustain=0.96, release=2.6, lfo_freq=0.38, lfo_depth=0.18, lfo_target="vcf", chorus_mix=0.55, chorus_delay=37.0, chorus_rate=1.15, chorus_depth=0.75, delay_mix=0.12, delay_feedback=0.26),
                create_preset("Ambient", "Ambient, spacious pad", waveform="sine", octave=0, cutoff=1300.0, resonance=0.2, key_tracking=0.3, attack=3.5, decay=3.0, sustain=0.9, release=4.5, lfo_shape="triangle", lfo_freq=0.15, lfo_depth=0.08, lfo_target="vco", chorus_mix=0.8, chorus_delay=48.0, chorus_rate=0.85, chorus_depth=0.95, delay_mix=0.25, delay_feedback=0.4),
                create_preset("Warm Strings", "Warm string section", waveform="sine", octave=0, cutoff=1950.0, resonance=0.22, key_tracking=0.55, attack=2.0, decay=1.8, sustain=0.99, release=3.0, lfo_shape="sine", lfo_freq=0.28, lfo_depth=0.14, lfo_target="vcf", chorus_mix=0.7, chorus_delay=43.0, chorus_rate=1.0, chorus_depth=0.88, delay_mix=0.11, delay_feedback=0.24),
                create_preset("Atmospheric", "Atmospheric, mysterious pad", waveform="triangle", octave=-1, cutoff=1400.0, resonance=0.3, key_tracking=0.35, attack=2.8, decay=2.5, sustain=0.93, release=3.8, lfo_shape="triangle", lfo_freq=0.22, lfo_depth=0.16, lfo_target="vcf", chorus_mix=0.75, chorus_delay=44.0, chorus_rate=1.08, chorus_depth=0.92, delay_mix=0.18, delay_feedback=0.33),
                create_preset("Dreamy", "Dreamy, floating pad", waveform="sine", octave=0, cutoff=1550.0, resonance=0.18, key_tracking=0.4, attack=3.2, decay=2.8, sustain=0.97, release=4.2, lfo_freq=0.32, lfo_depth=0.11, lfo_target="vco", chorus_mix=0.72, chorus_delay=46.0, chorus_rate=0.95, chorus_depth=0.9, delay_mix=0.2, delay_feedback=0.34),
                create_preset("Sweeping Pad", "Sweeping filter movement", waveform="sawtooth", octave=0, cutoff=2300.0, resonance=0.45, key_tracking=0.45, attack=2.0, decay=2.2, sustain=0.95, release=3.0, lfo_shape="sine", lfo_freq=0.5, lfo_depth=0.3, lfo_target="vcf", chorus_mix=0.5, chorus_delay=35.0, chorus_rate=1.2, chorus_depth=0.7, delay_mix=0.13, delay_feedback=0.28),
                create_preset("Velvet Pad", "Smooth, velvety pad", waveform="sine", octave=-1, cutoff=1650.0, resonance=0.2, key_tracking=0.5, attack=2.3, decay=2.0, sustain=0.98, release=3.2, lfo_shape="triangle", lfo_freq=0.33, lfo_depth=0.13, lfo_target="vcf", chorus_mix=0.65, chorus_delay=40.0, chorus_rate=1.1, chorus_depth=0.8, delay_mix=0.14, delay_feedback=0.29),
            ]
        },
        "plucked": {
            "name": "Plucked",
            "icon": "🎹",
            "presets": [
                create_preset("Piano", "Classic piano sound", waveform="sine", octave=0, cutoff=2500.0, resonance=0.2, key_tracking=0.8, attack=0.01, decay=0.8, sustain=0.3, release=0.6, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Harpsichord", "Bright harpsichord", waveform="square", octave=0, cutoff=3500.0, resonance=0.25, key_tracking=0.7, attack=0.005, decay=0.6, sustain=0.1, release=0.4, lfo_freq=2.5, lfo_depth=0.15, lfo_target="vcf"),
                create_preset("Marimba", "Wooden marimba sound", waveform="triangle", octave=0, cutoff=2800.0, resonance=0.3, key_tracking=0.6, attack=0.02, decay=0.5, sustain=0.05, release=0.3, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf", chorus_mix=0.2, chorus_delay=20.0, chorus_rate=1.5, chorus_depth=0.4),
                create_preset("Vibraphone", "Vibrant vibraphone", waveform="sine", octave=0, noise_level=0.01, cutoff=2200.0, resonance=0.15, key_tracking=0.7, attack=0.015, decay=0.7, sustain=0.2, release=0.4, lfo_shape="sine", lfo_freq=6.0, lfo_depth=0.25, lfo_target="vco"),
                create_preset("Glockenspiel", "Bright, metallic glockenspiel", waveform="square", octave=1, cutoff=4000.0, resonance=0.2, key_tracking=0.8, attack=0.008, decay=0.4, sustain=0.0, release=0.2, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Bells", "Resonant bell tones", waveform="sine", octave=0, cutoff=1800.0, resonance=0.35, key_tracking=0.5, attack=0.03, decay=1.2, sustain=0.2, release=0.8, lfo_shape="sine", lfo_freq=3.5, lfo_depth=0.2, lfo_target="vco", chorus_mix=0.3, chorus_delay=25.0, chorus_rate=1.3, chorus_depth=0.5),
                create_preset("Guitar", "Warm guitar pluck", waveform="sawtooth", octave=0, noise_level=0.05, cutoff=2200.0, resonance=0.3, key_tracking=0.65, attack=0.01, decay=0.6, sustain=0.1, release=0.4, lfo_freq=1.5, lfo_depth=0.1, lfo_target="vcf", chorus_mix=0.15, chorus_delay=22.0, chorus_rate=1.2, chorus_depth=0.4),
                create_preset("Kalimba", "African kalimba pluck", waveform="triangle", octave=1, cutoff=3000.0, resonance=0.25, key_tracking=0.7, attack=0.01, decay=0.5, sustain=0.05, release=0.3, lfo_freq=2.0, lfo_depth=0.12, lfo_target="vcf"),
                create_preset("Clavinet", "Electric clavinet", waveform="square", octave=0, cutoff=3200.0, resonance=0.4, key_tracking=0.6, attack=0.008, decay=0.4, sustain=0.15, release=0.3, lfo_freq=1.8, lfo_depth=0.18, lfo_target="vcf", chorus_mix=0.1, chorus_delay=21.0, chorus_rate=1.4, chorus_depth=0.35),
                create_preset("Sitar", "Metallic sitar pluck", waveform="sawtooth", octave=0, noise_level=0.08, cutoff=2500.0, resonance=0.55, key_tracking=0.5, attack=0.02, decay=0.7, sustain=0.1, release=0.4, lfo_freq=3.5, lfo_depth=0.25, lfo_target="vcf"),
                create_preset("Harp", "Shimmering harp", waveform="sine", octave=0, cutoff=2800.0, resonance=0.2, key_tracking=0.75, attack=0.01, decay=0.9, sustain=0.0, release=0.5, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf", chorus_mix=0.25, chorus_delay=24.0, chorus_rate=1.1, chorus_depth=0.5),
                create_preset("Pizzicato", "Pizzicato strings", waveform="sine", octave=0, cutoff=2000.0, resonance=0.25, key_tracking=0.7, attack=0.005, decay=0.4, sustain=0.05, release=0.25, lfo_freq=1.5, lfo_depth=0.08, lfo_target="vcf"),
                create_preset("Gamelan", "Metallic gamelan hit", waveform="triangle", octave=1, cutoff=3500.0, resonance=0.4, key_tracking=0.5, attack=0.03, decay=0.8, sustain=0.0, release=0.4, lfo_shape="sine", lfo_freq=4.5, lfo_depth=0.2, lfo_target="vcf"),
                create_preset("Twangy", "Twangy plucked sound", waveform="square", octave=0, cutoff=2600.0, resonance=0.35, key_tracking=0.6, attack=0.006, decay=0.5, sustain=0.1, release=0.3, lfo_freq=2.2, lfo_depth=0.2, lfo_target="vcf"),
                create_preset("Lute", "Classical lute", waveform="sine", octave=0, cutoff=2100.0, resonance=0.2, key_tracking=0.75, attack=0.012, decay=0.7, sustain=0.05, release=0.4, lfo_freq=1.0, lfo_depth=0.1, lfo_target="vcf", delay_mix=0.05, delay_feedback=0.12),
                create_preset("Banjo", "Bright banjo", waveform="sawtooth", octave=0, noise_level=0.03, cutoff=3200.0, resonance=0.3, key_tracking=0.65, attack=0.008, decay=0.35, sustain=0.08, release=0.25, lfo_freq=2.8, lfo_depth=0.15, lfo_target="vcf"),
            ]
        },
        "seq": {
            "name": "Seq",
            "icon": "⚡",
            "presets": [
                create_preset("Arp Up", "Upward arpeggiator pattern", waveform="sawtooth", octave=0, cutoff=2500.0, resonance=0.45, key_tracking=0.6, attack=0.01, decay=0.15, sustain=0.4, release=0.08, lfo_freq=2.0, lfo_depth=0.2, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=16.0, arp_range=2),
                create_preset("Arp Down", "Downward arpeggiator pattern", waveform="sawtooth", octave=0, cutoff=2400.0, resonance=0.4, key_tracking=0.6, attack=0.01, decay=0.15, sustain=0.4, release=0.08, lfo_freq=1.5, lfo_depth=0.15, lfo_target="vcf", arp_enabled=True, arp_mode="down", arp_rate=16.0, arp_range=2),
                create_preset("Arp UpDown", "Up-down arpeggiator pattern", waveform="square", octave=0, cutoff=2600.0, resonance=0.5, key_tracking=0.5, attack=0.01, decay=0.15, sustain=0.35, release=0.08, lfo_freq=2.5, lfo_depth=0.25, lfo_target="vcf", arp_enabled=True, arp_mode="updown", arp_rate=16.0, arp_range=2),
                create_preset("Arp Random", "Random arpeggiator pattern", waveform="triangle", octave=0, cutoff=2300.0, resonance=0.35, key_tracking=0.5, attack=0.01, decay=0.12, sustain=0.3, release=0.06, lfo_freq=3.0, lfo_depth=0.3, lfo_target="vcf", arp_enabled=True, arp_mode="random", arp_rate=12.0, arp_range=2),
                create_preset("Arp Slow", "Slow arpeggiator pattern", waveform="sine", octave=0, cutoff=2000.0, resonance=0.3, key_tracking=0.6, attack=0.02, decay=0.2, sustain=0.5, release=0.1, lfo_freq=1.0, lfo_depth=0.1, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=4.0, arp_range=1),
                create_preset("Arp Fast", "Fast arpeggiator pattern", waveform="sawtooth", octave=0, cutoff=3000.0, resonance=0.55, key_tracking=0.5, attack=0.008, decay=0.1, sustain=0.25, release=0.05, lfo_freq=4.0, lfo_depth=0.35, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=32.0, arp_range=1),
                create_preset("Arp Octave", "Wide octave arpeggiator", waveform="square", octave=-1, cutoff=2200.0, resonance=0.4, key_tracking=0.5, attack=0.01, decay=0.18, sustain=0.4, release=0.08, lfo_freq=2.2, lfo_depth=0.2, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=16.0, arp_range=3),
                create_preset("Arp Pulse", "Pulsing arpeggiator", waveform="sine", octave=0, cutoff=2500.0, resonance=0.25, key_tracking=0.6, attack=0.015, decay=0.12, sustain=0.2, release=0.07, lfo_shape="triangle", lfo_freq=3.5, lfo_depth=0.25, lfo_target="vco", arp_enabled=True, arp_mode="updown", arp_rate=8.0, arp_range=1),
                create_preset("Arp Acid", "Acid-style arpeggiator", waveform="sawtooth", octave=0, cutoff=1800.0, resonance=0.75, key_tracking=0.4, attack=0.01, decay=0.2, sustain=0.0, release=0.05, lfo_freq=3.0, lfo_depth=0.4, lfo_target="vcf", arp_enabled=True, arp_mode="random", arp_rate=12.0, arp_range=1),
                create_preset("Arp Smooth", "Smooth arpeggiator", waveform="sine", octave=0, cutoff=2200.0, resonance=0.2, key_tracking=0.7, attack=0.02, decay=0.25, sustain=0.6, release=0.12, lfo_freq=1.5, lfo_depth=0.12, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=8.0, arp_range=2, chorus_mix=0.2, chorus_delay=28.0, chorus_rate=1.2, chorus_depth=0.5),
                create_preset("Arp Stab", "Stabbing arpeggiator", waveform="square", octave=0, cutoff=3200.0, resonance=0.5, key_tracking=0.5, attack=0.005, decay=0.1, sustain=0.2, release=0.04, lfo_freq=5.0, lfo_depth=0.3, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=24.0, arp_range=1),
                create_preset("Arp Bell", "Bell-like arpeggiator", waveform="sine", octave=0, cutoff=2600.0, resonance=0.3, key_tracking=0.6, attack=0.03, decay=0.5, sustain=0.15, release=0.2, lfo_shape="sine", lfo_freq=2.0, lfo_depth=0.15, lfo_target="vcf", arp_enabled=True, arp_mode="updown", arp_rate=12.0, arp_range=2, chorus_mix=0.25, chorus_delay=30.0, chorus_rate=1.3, chorus_depth=0.6),
                create_preset("Arp Glitch", "Glitchy arpeggiator", waveform="square", octave=0, noise_level=0.1, cutoff=2000.0, resonance=0.45, key_tracking=0.4, attack=0.008, decay=0.08, sustain=0.1, release=0.03, lfo_freq=6.0, lfo_depth=0.4, lfo_target="vcf", arp_enabled=True, arp_mode="random", arp_rate=20.0, arp_range=2),
                create_preset("Arp Melodic", "Melodic arpeggiator", waveform="triangle", octave=0, cutoff=2700.0, resonance=0.35, key_tracking=0.65, attack=0.012, decay=0.18, sustain=0.35, release=0.1, lfo_freq=2.2, lfo_depth=0.18, lfo_target="vcf", arp_enabled=True, arp_mode="up", arp_rate=12.0, arp_range=2),
                create_preset("Arp Ambient", "Ambient arpeggiator", waveform="sine", octave=-1, cutoff=1600.0, resonance=0.2, key_tracking=0.4, attack=0.05, decay=0.4, sustain=0.5, release=0.15, lfo_shape="triangle", lfo_freq=0.8, lfo_depth=0.15, lfo_target="vco", arp_enabled=True, arp_mode="updown", arp_rate=2.0, arp_range=1, chorus_mix=0.4, chorus_delay=35.0, chorus_rate=1.0, chorus_depth=0.7, delay_mix=0.15, delay_feedback=0.3),
                create_preset("Arp Hypnotic", "Hypnotic looping arpeggiator", waveform="sawtooth", octave=0, cutoff=2400.0, resonance=0.4, key_tracking=0.55, attack=0.01, decay=0.2, sustain=0.3, release=0.08, lfo_shape="sine", lfo_freq=2.8, lfo_depth=0.22, lfo_target="vcf", arp_enabled=True, arp_mode="updown", arp_rate=16.0, arp_range=3),
            ]
        },
        "fx": {
            "name": "FX",
            "icon": "✨",
            "presets": [
                create_preset("Vocoder", "Vocoder-like effect", waveform="square", octave=0, noise_level=0.3, cutoff=1500.0, resonance=0.6, key_tracking=0.5, attack=0.05, decay=0.3, sustain=0.4, release=0.2, lfo_shape="square", lfo_freq=8.0, lfo_depth=0.5, lfo_target="vcf"),
                create_preset("Wobble", "Extreme wobble effect", waveform="sawtooth", octave=0, cutoff=2000.0, resonance=0.8, key_tracking=0.3, attack=0.02, decay=0.2, sustain=0.3, release=0.1, lfo_shape="sine", lfo_freq=15.0, lfo_depth=0.9, lfo_target="vcf", chorus_mix=0.6, chorus_delay=30.0, chorus_rate=3.5, chorus_depth=0.9),
                create_preset("Siren", "Siren effect", waveform="triangle", octave=0, cutoff=3500.0, resonance=0.7, key_tracking=0.2, attack=0.01, decay=0.15, sustain=0.2, release=0.05, lfo_shape="sine", lfo_freq=12.0, lfo_depth=0.8, lfo_target="vcf", delay_mix=0.3, delay_feedback=0.5),
                create_preset("Bitcrusher", "Digital bitcrusher feel", waveform="square", octave=0, noise_level=0.2, cutoff=1200.0, resonance=0.5, key_tracking=0.3, attack=0.08, decay=0.25, sustain=0.25, release=0.15, lfo_shape="square", lfo_freq=10.0, lfo_depth=0.6, lfo_target="vco"),
                create_preset("Spectral", "Spectral freeze effect", waveform="sine", octave=0, noise_level=0.4, cutoff=2200.0, resonance=0.4, key_tracking=0.2, attack=0.1, decay=0.5, sustain=0.6, release=0.3, lfo_shape="triangle", lfo_freq=0.5, lfo_depth=0.3, lfo_target="vcf", chorus_mix=0.7, chorus_delay=40.0, chorus_rate=2.0, chorus_depth=0.95),
                create_preset("Resonator", "Resonating filter effect", waveform="triangle", octave=0, cutoff=1800.0, resonance=0.95, key_tracking=0.6, attack=0.02, decay=0.4, sustain=0.1, release=0.2, lfo_freq=4.0, lfo_depth=0.4, lfo_target="vcf", delay_mix=0.2, delay_feedback=0.4),
                create_preset("Swirl", "Swirling modulation effect", waveform="sawtooth", octave=0, cutoff=2600.0, resonance=0.5, key_tracking=0.4, attack=0.03, decay=0.25, sustain=0.35, release=0.15, lfo_shape="sine", lfo_freq=7.0, lfo_depth=0.7, lfo_target="vco", chorus_mix=0.8, chorus_delay=35.0, chorus_rate=2.2, chorus_depth=0.9),
                create_preset("Laser", "Laser sound effect", waveform="square", octave=1, cutoff=4000.0, resonance=0.6, key_tracking=0.2, attack=0.005, decay=0.3, sustain=0.0, release=0.1, lfo_shape="sine", lfo_freq=20.0, lfo_depth=0.8, lfo_target="vcf"),
                create_preset("Portal", "Portal/teleport effect", waveform="sine", octave=0, noise_level=0.5, cutoff=1000.0, resonance=0.7, key_tracking=0.1, attack=0.2, decay=0.8, sustain=0.2, release=0.5, lfo_shape="sine", lfo_freq=2.0, lfo_depth=0.6, lfo_target="vcf", chorus_mix=0.7, chorus_delay=45.0, chorus_rate=1.5, chorus_depth=0.95, delay_mix=0.4, delay_feedback=0.6),
                create_preset("Metallic", "Metallic texture effect", waveform="square", octave=1, cutoff=3200.0, resonance=0.75, key_tracking=0.3, attack=0.02, decay=0.3, sustain=0.25, release=0.1, lfo_shape="square", lfo_freq=9.0, lfo_depth=0.65, lfo_target="vcf", chorus_mix=0.5, chorus_delay=32.0, chorus_rate=3.0, chorus_depth=0.8),
                create_preset("Underwater", "Underwater bubbling effect", waveform="sine", octave=-1, noise_level=0.3, cutoff=800.0, resonance=0.4, key_tracking=0.2, attack=0.08, decay=0.6, sustain=0.3, release=0.4, lfo_shape="sine", lfo_freq=3.0, lfo_depth=0.5, lfo_target="vcf", chorus_mix=0.6, chorus_delay=50.0, chorus_rate=1.2, chorus_depth=0.8, delay_mix=0.25, delay_feedback=0.4),
                create_preset("Sci-Fi", "Sci-fi effect", waveform="triangle", octave=0, cutoff=2000.0, resonance=0.65, key_tracking=0.25, attack=0.04, decay=0.35, sustain=0.2, release=0.15, lfo_shape="sine", lfo_freq=11.0, lfo_depth=0.75, lfo_target="vcf", delay_mix=0.3, delay_feedback=0.5),
                create_preset("Glitch", "Glitchy digital effect", waveform="square", octave=0, noise_level=0.6, cutoff=1500.0, resonance=0.55, key_tracking=0.2, attack=0.01, decay=0.15, sustain=0.1, release=0.05, lfo_shape="square", lfo_freq=18.0, lfo_depth=0.85, lfo_target="vcf"),
                create_preset("Echo Chamber", "Echo chamber effect", waveform="sine", octave=0, cutoff=2000.0, resonance=0.3, key_tracking=0.5, attack=0.05, decay=0.4, sustain=0.3, release=0.3, lfo_freq=2.0, lfo_depth=0.15, lfo_target="vcf", delay_mix=0.5, delay_feedback=0.7),
                create_preset("Chaos", "Chaotic texture effect", waveform="sawtooth", octave=0, noise_level=0.7, cutoff=2500.0, resonance=0.8, key_tracking=0.1, attack=0.06, decay=0.3, sustain=0.25, release=0.2, lfo_shape="sine", lfo_freq=13.0, lfo_depth=0.9, lfo_target="vcf", chorus_mix=0.8, chorus_delay=38.0, chorus_rate=2.8, chorus_depth=0.95, delay_mix=0.2, delay_feedback=0.35),
                create_preset("Phantom", "Phantom/ghost effect", waveform="sine", octave=-1, noise_level=0.2, cutoff=1200.0, resonance=0.2, key_tracking=0.3, attack=0.15, decay=0.7, sustain=0.4, release=0.5, lfo_shape="triangle", lfo_freq=0.75, lfo_depth=0.4, lfo_target="vco", chorus_mix=0.9, chorus_delay=48.0, chorus_rate=0.8, chorus_depth=0.95, delay_mix=0.35, delay_feedback=0.55),
            ]
        },
        "misc": {
            "name": "Misc",
            "icon": "🎯",
            "presets": [
                create_preset("Kick Drum", "Synthesized kick drum", waveform="sine", octave=-1, cutoff=150.0, resonance=0.5, key_tracking=0.2, attack=0.001, decay=0.5, sustain=0.0, release=0.1, lfo_shape="sine", lfo_freq=1.5, lfo_depth=0.3, lfo_target="vcf"),
                create_preset("Snare Drum", "Snare drum synthesis", waveform="square", octave=0, noise_level=0.4, cutoff=5000.0, resonance=0.3, key_tracking=0.0, attack=0.002, decay=0.15, sustain=0.0, release=0.08, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Hihat Closed", "Closed hihat sound", waveform="square", octave=2, noise_level=0.7, cutoff=8000.0, resonance=0.2, key_tracking=0.0, attack=0.001, decay=0.1, sustain=0.0, release=0.05, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Hihat Open", "Open hihat sound", waveform="triangle", octave=2, noise_level=0.8, cutoff=7000.0, resonance=0.25, key_tracking=0.0, attack=0.002, decay=0.4, sustain=0.1, release=0.2, lfo_shape="sine", lfo_freq=3.0, lfo_depth=0.2, lfo_target="vcf"),
                create_preset("Tom High", "High tom sound", waveform="sine", octave=1, cutoff=800.0, resonance=0.4, key_tracking=0.2, attack=0.005, decay=0.2, sustain=0.0, release=0.1, lfo_freq=2.0, lfo_depth=0.15, lfo_target="vcf"),
                create_preset("Tom Mid", "Mid tom sound", waveform="sine", octave=0, cutoff=500.0, resonance=0.4, key_tracking=0.2, attack=0.005, decay=0.25, sustain=0.0, release=0.12, lfo_freq=1.8, lfo_depth=0.15, lfo_target="vcf"),
                create_preset("Tom Low", "Low tom sound", waveform="sine", octave=-1, cutoff=300.0, resonance=0.4, key_tracking=0.2, attack=0.005, decay=0.3, sustain=0.0, release=0.15, lfo_freq=1.5, lfo_depth=0.15, lfo_target="vcf"),
                create_preset("Cowbell", "Metallic cowbell", waveform="square", octave=0, cutoff=2000.0, resonance=0.5, key_tracking=0.3, attack=0.008, decay=0.3, sustain=0.05, release=0.15, lfo_shape="sine", lfo_freq=4.0, lfo_depth=0.25, lfo_target="vcf"),
                create_preset("Clap", "Hand clap sound", waveform="triangle", octave=0, noise_level=0.5, cutoff=3000.0, resonance=0.3, key_tracking=0.0, attack=0.003, decay=0.2, sustain=0.0, release=0.1, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Perc Hit", "Percussive hit", waveform="square", octave=1, cutoff=4000.0, resonance=0.4, key_tracking=0.5, attack=0.01, decay=0.25, sustain=0.0, release=0.1, lfo_freq=5.0, lfo_depth=0.2, lfo_target="vcf"),
                create_preset("Zap", "Electronic zap sound", waveform="sawtooth", octave=1, cutoff=3000.0, resonance=0.6, key_tracking=0.2, attack=0.02, decay=0.3, sustain=0.0, release=0.08, lfo_shape="sine", lfo_freq=10.0, lfo_depth=0.5, lfo_target="vcf"),
                create_preset("Bleep", "Short bleep sound", waveform="sine", octave=1, cutoff=2000.0, resonance=0.2, key_tracking=0.3, attack=0.01, decay=0.1, sustain=0.0, release=0.05, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
                create_preset("Boom", "Deep boom sound", waveform="sine", octave=-2, cutoff=80.0, resonance=0.6, key_tracking=0.1, attack=0.01, decay=0.8, sustain=0.0, release=0.2, lfo_freq=1.0, lfo_depth=0.2, lfo_target="vcf"),
                create_preset("Ping", "Clear ping sound", waveform="sine", octave=2, cutoff=3500.0, resonance=0.3, key_tracking=0.6, attack=0.005, decay=0.4, sustain=0.0, release=0.15, lfo_shape="sine", lfo_freq=3.0, lfo_depth=0.15, lfo_target="vco"),
                create_preset("Whoosh", "Whoosh effect", waveform="sawtooth", octave=1, noise_level=0.3, cutoff=4000.0, resonance=0.4, key_tracking=0.1, attack=0.05, decay=0.4, sustain=0.0, release=0.15, lfo_shape="sine", lfo_freq=6.0, lfo_depth=0.4, lfo_target="vcf"),
                create_preset("Pop", "Pop/click sound", waveform="square", octave=0, cutoff=5000.0, resonance=0.4, key_tracking=0.0, attack=0.002, decay=0.12, sustain=0.0, release=0.05, lfo_freq=0.0, lfo_depth=0.0, lfo_target="vcf"),
            ]
        },
        "synth": {
            "name": "Synth",
            "icon": "🎛️",
            "presets": [
                create_preset("Moog Classic", "Classic Moog-style synth", waveform="sawtooth", octave=0, cutoff=2000.0, resonance=0.7, key_tracking=0.7, attack=0.1, decay=0.5, sustain=0.8, release=0.6, lfo_shape="sine", lfo_freq=0.8, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.15, chorus_delay=28.0, chorus_rate=1.2, chorus_depth=0.5),
                create_preset("Minimoog", "Warm Minimoog-inspired", waveform="sine", octave=0, cutoff=2500.0, resonance=0.5, key_tracking=0.8, attack=0.08, decay=0.4, sustain=0.75, release=0.5, lfo_shape="sine", lfo_freq=1.0, lfo_depth=0.15, lfo_target="vcf", delay_mix=0.05, delay_feedback=0.15),
                create_preset("Prophet", "Prophet-V style", waveform="sawtooth", octave=0, cutoff=2200.0, resonance=0.6, key_tracking=0.65, attack=0.12, decay=0.3, sustain=0.7, release=0.4, lfo_freq=2.0, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.3, chorus_delay=32.0, chorus_rate=1.3, chorus_depth=0.6),
                create_preset("Juno", "Juno-style warm synth", waveform="square", octave=0, cutoff=1900.0, resonance=0.4, key_tracking=0.7, attack=0.1, decay=0.5, sustain=0.8, release=0.6, lfo_freq=0.6, lfo_depth=0.1, lfo_target="vcf", chorus_mix=0.5, chorus_delay=35.0, chorus_rate=1.0, chorus_depth=0.8),
                create_preset("Blade Runner", "Blade Runner pad", waveform="sine", octave=0, cutoff=1600.0, resonance=0.3, key_tracking=0.5, attack=2.0, decay=1.5, sustain=0.9, release=2.0, lfo_freq=0.4, lfo_depth=0.15, lfo_target="vco", chorus_mix=0.6, chorus_delay=38.0, chorus_rate=1.1, chorus_depth=0.8, delay_mix=0.1, delay_feedback=0.2),
                create_preset("Wavetable", "Modern wavetable synth", waveform="triangle", octave=0, cutoff=2600.0, resonance=0.5, key_tracking=0.75, attack=0.05, decay=0.2, sustain=0.65, release=0.3, lfo_shape="sine", lfo_freq=3.5, lfo_depth=0.3, lfo_target="vcf", chorus_mix=0.2, chorus_delay=26.0, chorus_rate=1.4, chorus_depth=0.5),
                create_preset("PPG", "PPG Wave style", waveform="sawtooth", octave=0, cutoff=2100.0, resonance=0.65, key_tracking=0.6, attack=0.08, decay=0.4, sustain=0.75, release=0.5, lfo_freq=1.5, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.25, chorus_delay=30.0, chorus_rate=1.25, chorus_depth=0.6, delay_mix=0.04, delay_feedback=0.12),
                create_preset("Waldorf", "Waldorf-inspired", waveform="square", octave=0, cutoff=2400.0, resonance=0.55, key_tracking=0.7, attack=0.06, decay=0.3, sustain=0.7, release=0.4, lfo_freq=2.2, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.15, chorus_delay=27.0, chorus_rate=1.3, chorus_depth=0.55),
                create_preset("ARP Odyssey", "ARP Odyssey style", waveform="sawtooth", octave=0, cutoff=1800.0, resonance=0.6, key_tracking=0.65, attack=0.1, decay=0.6, sustain=0.6, release=0.7, lfo_shape="triangle", lfo_freq=1.2, lfo_depth=0.18, lfo_target="vcf", chorus_mix=0.1, chorus_delay=24.0, chorus_rate=1.15, chorus_depth=0.45),
                create_preset("Mellotron", "Mellotron emulation", waveform="sine", octave=0, cutoff=2300.0, resonance=0.25, key_tracking=0.8, attack=0.15, decay=0.5, sustain=0.85, release=0.7, lfo_freq=0.5, lfo_depth=0.1, lfo_target="vcf", chorus_mix=0.4, chorus_delay=33.0, chorus_rate=1.15, chorus_depth=0.7, delay_mix=0.06, delay_feedback=0.16),
                create_preset("Casio VZ", "Casio VZ-style", waveform="triangle", octave=0, cutoff=2000.0, resonance=0.35, key_tracking=0.7, attack=0.08, decay=0.4, sustain=0.7, release=0.5, lfo_freq=2.8, lfo_depth=0.2, lfo_target="vcf", chorus_mix=0.25, chorus_delay=29.0, chorus_rate=1.25, chorus_depth=0.55),
                create_preset("Ensoniq", "Ensoniq Mirage style", waveform="sawtooth", octave=0, cutoff=2250.0, resonance=0.5, key_tracking=0.75, attack=0.07, decay=0.35, sustain=0.75, release=0.45, lfo_freq=1.8, lfo_depth=0.22, lfo_target="vcf", chorus_mix=0.2, chorus_delay=25.0, chorus_rate=1.2, chorus_depth=0.5),
                create_preset("Fairlight", "Fairlight CMI style", waveform="sine", octave=0, cutoff=2100.0, resonance=0.3, key_tracking=0.8, attack=0.12, decay=0.5, sustain=0.8, release=0.6, lfo_freq=0.7, lfo_depth=0.12, lfo_target="vco", chorus_mix=0.35, chorus_delay=34.0, chorus_rate=1.1, chorus_depth=0.65),
                create_preset("Korg MS20", "Korg MS20 style", waveform="square", octave=0, cutoff=2350.0, resonance=0.7, key_tracking=0.6, attack=0.05, decay=0.3, sustain=0.65, release=0.4, lfo_freq=3.0, lfo_depth=0.3, lfo_target="vcf", delay_mix=0.08, delay_feedback=0.18),
                create_preset("Roland SH", "Roland SH-101 inspired", waveform="sawtooth", octave=0, cutoff=1700.0, resonance=0.75, key_tracking=0.5, attack=0.08, decay=0.5, sustain=0.5, release=0.6, lfo_freq=2.5, lfo_depth=0.35, lfo_target="vcf", delay_mix=0.05, delay_feedback=0.1),
                create_preset("Hybrid", "Modern hybrid synth", waveform="sawtooth", octave=0, noise_level=0.02, cutoff=2500.0, resonance=0.6, key_tracking=0.7, attack=0.06, decay=0.3, sustain=0.72, release=0.4, lfo_shape="sine", lfo_freq=2.5, lfo_depth=0.25, lfo_target="vcf", chorus_mix=0.2, chorus_delay=28.0, chorus_rate=1.3, chorus_depth=0.55, delay_mix=0.06, delay_feedback=0.14),
            ]
        },
        "user": {
            "name": "User",
            "icon": "👤",
            "presets": []  # Empty, auto-populated with user-saved presets
        },
    }

    return presets


if __name__ == "__main__":
    # For testing
    presets = get_factory_presets()
    print(f"Factory presets module loaded")
    print(f"Categories: {list(presets.keys())}")
    print(f"Bass presets: {len(presets['bass']['presets'])}")
