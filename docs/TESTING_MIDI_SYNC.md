# MIDI Synchronization Testing Guide

## Overview
This guide helps verify that the MIDI event queue synchronization system is working correctly and eliminates clicks.

## Quick Test Checklist

### ✅ 1. Single Note Click Test
**Test**: Press and release individual keys one at a time

**Expected Result**:
- ✅ Completely click-free note attacks
- ✅ Smooth note release with no pops
- ✅ Clean start even at low frequencies (C1, C2)

**What to Listen For**:
- ❌ "Click" or "pop" at note start = FAIL
- ❌ "Pop" at note end = FAIL (check release time)
- ✅ Smooth, clean note = PASS

---

### ✅ 2. Chord Press Test
**Test**: Press 2-4 keys simultaneously (chord)

**Expected Result**:
- ✅ All notes start together smoothly
- ✅ No clicks from simultaneous triggers
- ✅ Voices blend cleanly

**What to Listen For**:
- ❌ Sharp "click" when pressing chord = FAIL
- ❌ Stuttering or crackling = FAIL
- ✅ Smooth chord attack = PASS

---

### ✅ 3. Rapid Playing Test
**Test**: Play fast scales or arpeggios (8+ notes/second)

**Expected Result**:
- ✅ Smooth, even note attacks
- ✅ No clicks during fast playing
- ✅ Consistent latency (notes feel responsive)

**What to Listen For**:
- ❌ Intermittent clicks during fast playing = FAIL
- ❌ Notes feel "delayed" or "sluggish" = Check buffer size
- ✅ Fast, clean note transitions = PASS

---

### ✅ 4. Voice Stealing Test
**Test**: Hold 4 notes, then press 5th, 6th, 7th notes

**Expected Result**:
- ✅ Voice stealing happens smoothly
- ✅ No clicks when voices are stolen
- ✅ Oldest/quietest voices stolen gracefully

**What to Listen For**:
- ❌ Click or pop when 5th note pressed = FAIL
- ❌ Abrupt cutoff of stolen voice = Check filter state preservation
- ✅ Smooth voice transitions = PASS

---

### ✅ 5. Pitch Bend + Notes Test
**Test**: Play notes while moving pitch wheel

**Expected Result**:
- ✅ Smooth pitch modulation
- ✅ No clicks when pressing notes during pitch bend
- ✅ Pitch wheel feels smooth (not steppy)

**What to Listen For**:
- ❌ "Jumpy" or "steppy" pitch wheel = Check smoothing factor
- ❌ Clicks when pressing notes during bend = FAIL
- ✅ Smooth pitch glide with clean note triggers = PASS

---

### ✅ 6. Extreme Frequency Test
**Test**: Play lowest notes (C1-C2) and highest notes (C6-C7)

**Expected Result**:
- ✅ Low notes: Deep, clean, no clicks
- ✅ High notes: Bright, clean, no artifacts
- ✅ Consistent behavior across full range

**What to Listen For**:
- ❌ Low notes have more clicks than high notes = Check anti-click fade
- ❌ High notes sound aliased or distorted = Check sample rate
- ✅ Clean across full keyboard = PASS

---

## Latency Test

### Acceptable Latency Range
- **Target**: 15-25ms (feels instant)
- **Acceptable**: 25-40ms (playable)
- **Too High**: >50ms (noticeable delay)

### How to Test
1. Connect MIDI keyboard
2. Play short, percussive notes (middle C)
3. Compare feel to:
   - ✅ Hardware synthesizer: Should feel similar
   - ✅ Software piano VST: Comparable latency
   - ❌ Noticeable lag: Increase buffer or check CPU

### Current Configuration
```
Buffer Size: 1024 samples
Sample Rate: 48000 Hz
Theoretical Buffer Latency: ~21.3ms
Total Latency (typical): ~20-30ms
```

---

## Advanced Diagnostics

### If Clicks Persist

1. **Check Buffer Size**
   ```python
   # In synth_engine.py
   self.buffer_size = 1024  # Try 2048 if clicks persist
   ```

2. **Verify Queue is Working**
   - Add debug print in `_process_midi_events()`:
   ```python
   def _process_midi_events(self):
       events_processed = 0
       while not self.midi_event_queue.empty():
           # ... process event
           events_processed += 1
       if events_processed > 0:
           print(f"Processed {events_processed} events")
   ```
   - Should see batches of events (1-3 typically)

3. **Check Anti-Click Fade Duration**
   ```python
   # In _apply_envelope()
   click_prevention_time = 0.002  # Try 0.003 or 0.004 if needed
   ```

4. **Verify DC Blocker is Active**
   - `_apply_dc_blocker()` should be called in audio callback
   - Check filter coefficient: `0.995` (higher = more aggressive)

---

## System Requirements

### Minimum Specs
- **CPU**: Dual-core 2.0 GHz or better
- **RAM**: 2GB available
- **OS**: Windows 10+, macOS 10.14+, Linux (ALSA/PulseAudio)
- **Audio Interface**: Built-in or USB audio interface

### Optimal Performance
- **CPU Usage**: Should be 5-10% during 4-voice playback
- **Buffer Underruns**: Zero (check with `stream.get_stream_time()`)
- **Latency**: 15-25ms typical

---

## Common Issues

### Issue: Clicks on Single Notes
**Cause**: Events processed mid-buffer
**Fix**: Verify queue system is active

### Issue: Clicks on Chords Only
**Cause**: Multiple simultaneous triggers
**Fix**: Increase anti-click fade (2ms → 3ms)

### Issue: High CPU Usage
**Cause**: Inefficient processing
**Fix**: Check scipy is installed for optimized filtering

### Issue: Noticeable Latency
**Cause**: Buffer too large
**Fix**: Reduce buffer_size (1024 → 512, but may increase clicks)

### Issue: Audio Dropouts
**Cause**: CPU overload or buffer too small
**Fix**: Increase buffer_size or reduce polyphony

---

## Success Criteria

✅ **System Ready for Use** when ALL tests pass:
- ✅ Single notes click-free
- ✅ Chords click-free
- ✅ Fast playing smooth
- ✅ Voice stealing inaudible
- ✅ Pitch bend smooth with clean notes
- ✅ Full keyboard range clean
- ✅ Latency feels instant (<30ms)
- ✅ CPU usage reasonable (<15%)

---

## Reporting Issues

If clicks persist after verification:

1. Document which test fails
2. Note waveform type (Sine/Square/Sawtooth/Triangle)
3. Record filter settings (cutoff, resonance)
4. Note envelope settings (A/D/S/R)
5. Specify MIDI keyboard model
6. Check OS audio settings (sample rate, exclusive mode)

Most click issues are resolved by:
- ✅ Queue synchronization (already implemented)
- ✅ Proper anti-click fade (2ms)
- ✅ DC blocker filter (active)
- ✅ Correct buffer size (1024 samples)
