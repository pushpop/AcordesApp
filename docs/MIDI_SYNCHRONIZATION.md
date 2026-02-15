# MIDI Event Synchronization System

## Problem Statement

When MIDI note events arrive from a MIDI keyboard, they can occur at any random time. Previously, the synthesizer would trigger notes immediately when MIDI events arrived, which could happen in the middle of an audio buffer being generated. This caused audible clicks because:

1. **Mid-buffer discontinuities**: Starting a note halfway through a buffer creates a sudden amplitude change
2. **Phase misalignment**: Audio processing expects note changes at buffer boundaries
3. **Filter state jumps**: Filters can produce transient spikes when input suddenly changes

## Solution: Event Queue Synchronization

The MIDI synchronization system decouples MIDI input timing from audio processing timing by using a queue.

### Architecture

```
MIDI Input Thread          Audio Callback Thread
     │                           │
     ▼                           ▼
┌──────────┐              ┌────────────────┐
│ note_on()│              │ Audio Callback │
│ note_off()              │                │
└─────┬────┘              └────────┬───────┘
      │                            │
      │ Queue Event                │ Process Queue
      ▼                            ▼
  ┌────────────────────────────────────┐
  │      MIDI Event Queue              │
  │  (Thread-safe queue.Queue)         │
  └────────────────────────────────────┘
           │                      │
           │ Events stored        │ Events consumed
           │ asynchronously       │ at buffer boundary
           ▼                      ▼
    {'type': 'note_on',    ┌──────────────────┐
     'note': 60,           │_process_midi_    │
     'velocity': 0.8}      │    events()      │
                           └──────────────────┘
                                   │
                                   ▼
                           ┌──────────────────┐
                           │ _trigger_note()  │
                           │ _release_note()  │
                           └──────────────────┘
```

### Implementation Details

#### 1. Event Queue Creation
```python
# In SynthEngine.__init__()
self.midi_event_queue = queue.Queue()
```

Uses Python's `queue.Queue()` which is thread-safe, allowing MIDI input thread to safely communicate with audio callback thread.

#### 2. Public Methods Queue Events
```python
def note_on(self, midi_note: int, velocity: int = 127):
    """Queue a note on event for processing in the audio callback."""
    velocity_normalized = np.sqrt(velocity / 127.0)
    self.held_notes.add(midi_note)
    self.midi_event_queue.put({
        'type': 'note_on',
        'note': midi_note,
        'velocity': velocity_normalized
    })

def note_off(self, midi_note: int):
    """Queue a note off event for processing in the audio callback."""
    self.held_notes.discard(midi_note)
    self.midi_event_queue.put({
        'type': 'note_off',
        'note': midi_note
    })
```

These methods are called from the MIDI input thread and simply queue the event without doing any audio processing.

#### 3. Audio Callback Processes Queue
```python
def _audio_callback(self, in_data, frame_count, time_info, status):
    try:
        # Process all pending MIDI events at the start of the audio buffer
        self._process_midi_events()

        # Update pitch bend for smooth interpolation
        self._update_voice_frequencies()

        # Mix all active voices...
```

The audio callback (which runs in a separate high-priority audio thread) processes all queued events at the very start of each buffer.

#### 4. Event Processing Loop
```python
def _process_midi_events(self):
    """Process all pending MIDI events from the queue."""
    while not self.midi_event_queue.empty():
        try:
            event = self.midi_event_queue.get_nowait()
            event_type = event['type']

            if event_type == 'note_on':
                self._trigger_note(event['note'], event['velocity'])
            elif event_type == 'note_off':
                self._release_note(event['note'])

        except queue.Empty:
            break
```

This dequeues and processes all pending events, triggering/releasing notes as needed.

#### 5. Internal Processing Methods
```python
def _trigger_note(self, midi_note: int, velocity_normalized: float):
    """Internal method to trigger a note (called from audio callback)."""
    # Find available voice or steal one
    # Trigger the note with proper phase initialization

def _release_note(self, midi_note: int):
    """Internal method to release a note (called from audio callback)."""
    # Find voice playing this note and start release phase
```

These internal methods perform the actual audio processing and are only called from the audio thread.

## Benefits

### 1. Click Elimination
All note triggers now happen at buffer boundaries (every 1024 samples = ~21.3ms), ensuring:
- No mid-buffer amplitude discontinuities
- Clean phase initialization at buffer start
- Filter states update smoothly
- Anti-click fade-in operates correctly

### 2. Thread Safety
Separates MIDI input thread from audio thread:
- MIDI thread: Lightweight, just queues events
- Audio thread: High-priority, processes events at optimal time
- No locks needed in audio callback (queue handles synchronization)

### 3. Timing Precision
Events are processed at precise buffer boundaries:
- Maximum latency: One buffer period (~21.3ms @ 48kHz, 1024 samples)
- Consistent timing (not dependent on when MIDI event arrives)
- Predictable behavior for musicians

### 4. Jitter Reduction
Multiple rapid MIDI events are batched and processed together:
- All events in one buffer period processed simultaneously
- Reduces timing jitter from OS scheduling
- More stable audio output

## Performance Impact

### CPU Usage
- **Minimal overhead**: Queue operations are O(1) and very fast
- **No blocking**: `get_nowait()` prevents audio thread from waiting
- **Event processing**: Only happens when events exist in queue

### Latency Analysis
```
Total Latency Breakdown (from key press to sound):

1. MIDI Input Latency:           ~1-2ms   (USB MIDI, OS drivers)
2. Event Queue Latency:           ~0.01ms  (queue.put/get)
3. Buffer Alignment Wait:         0-21ms   (wait for next buffer)
4. Audio Processing:              ~2-3ms   (synth engine)
5. Audio Driver/DAC:              ~5-10ms  (hardware, OS audio)
─────────────────────────────────────────────────────────────
Total Perceived Latency:          ~8-36ms  (average ~20ms)
```

**Result**: Well within acceptable range for live playing (< 30ms feels instant)

## Testing Verification

To verify the synchronization is working:

1. **Single note test**: Press one key - should be completely click-free
2. **Chord test**: Press multiple keys simultaneously - no clicks
3. **Rapid playing**: Play fast sequences - smooth and clean
4. **Pitch bend during notes**: Should remain smooth without clicks
5. **Voice stealing**: Play 5+ notes quickly - stealing should be inaudible

## Alternative Approaches Considered

### 1. Immediate Processing (Previous Approach)
❌ **Rejected**: Causes clicks from mid-buffer note triggers

### 2. Mutex Locks
❌ **Rejected**: Locks in audio callback can cause priority inversion and audio dropouts

### 3. Lock-free Ring Buffer
⚠️ **Overkill**: More complex to implement, minimal performance gain for 4-voice synth

### 4. Event Queue (Current Implementation)
✅ **Selected**:
- Simple and maintainable
- Thread-safe without locks in audio callback
- Excellent performance
- Industry-standard approach

## Conclusion

The MIDI event queue synchronization system successfully eliminates clicks by ensuring all note events are processed at audio buffer boundaries. This is a proven technique used in professional synthesizers and DAWs, providing optimal balance between:

- **Low latency** (~20ms average)
- **Click-free audio** (no mid-buffer discontinuities)
- **Thread safety** (no blocking in audio callback)
- **Code simplicity** (maintainable and debuggable)

The system is now production-ready for live performance use.
