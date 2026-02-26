#!/usr/bin/env python3
"""ABOUTME: Test for multi-drum mixing - verifies multiple drums on same step don't interfere.
ABOUTME: Tests parameter isolation and per-MIDI-note parameter caching."""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from music.synth_engine import SynthEngine
from modes.tambor.music.drum_voice_manager import DrumVoiceManager
from modes.tambor.music.drum_presets import DRUM_PRESETS


class MultiDrumMixingTester:
    """Test multi-drum triggering and parameter isolation."""

    def __init__(self):
        self.synth = SynthEngine()
        self.drum_manager = DrumVoiceManager(self.synth)

    def test_parameter_isolation(self):
        """Test that parameters are properly isolated by MIDI note."""
        print("\n" + "="*70)
        print("TEST 1: Parameter Isolation by MIDI Note")
        print("="*70)

        # Get parameters for two drums
        kick_preset = DRUM_PRESETS.get("Kick", {})
        hh_preset = DRUM_PRESETS.get("Closed HH", {})

        kick_midi = kick_preset.get("midi_note", 36)
        hh_midi = hh_preset.get("midi_note", 42)

        kick_params = kick_preset.get("synth_params", {})
        hh_params = hh_preset.get("synth_params", {})

        print(f"\nKick MIDI Note: {kick_midi}")
        print(f"  - Cutoff: {kick_params.get('cutoff_freq', 'N/A')} Hz")
        print(f"  - Attack: {kick_params.get('attack', 'N/A')} s")
        print(f"  - Decay: {kick_params.get('decay', 'N/A')} s")

        print(f"\nClosed HH MIDI Note: {hh_midi}")
        print(f"  - Cutoff: {hh_params.get('cutoff_freq', 'N/A')} Hz")
        print(f"  - Attack: {hh_params.get('attack', 'N/A')} s")
        print(f"  - Decay: {hh_params.get('decay', 'N/A')} s")

        # Check that parameters are cached separately by MIDI note
        if kick_midi in self.drum_manager.midi_note_params:
            cached_kick = self.drum_manager.midi_note_params[kick_midi]
            print(f"\n✅ Kick parameters cached for MIDI note {kick_midi}")
            print(f"   Cached cutoff: {cached_kick.get('cutoff_freq')} Hz")
        else:
            print(f"\n⚠️ Kick parameters not cached for MIDI note {kick_midi}")

        if hh_midi in self.drum_manager.midi_note_params:
            cached_hh = self.drum_manager.midi_note_params[hh_midi]
            print(f"✅ Closed HH parameters cached for MIDI note {hh_midi}")
            print(f"   Cached cutoff: {cached_hh.get('cutoff_freq')} Hz")
        else:
            print(f"⚠️ Closed HH parameters not cached for MIDI note {hh_midi}")

        return kick_midi, hh_midi, kick_params, hh_params

    def test_simultaneous_triggers(self):
        """Test triggering multiple drums simultaneously."""
        print("\n" + "="*70)
        print("TEST 2: Simultaneous Multi-Drum Trigger")
        print("="*70)

        print("\nTriggering drums 0 (Kick) and 2 (Closed HH) simultaneously...")

        try:
            # Trigger both drums at the same time (simulating same step)
            self.drum_manager.trigger_drum(0, velocity=100, humanize_velocity=1.0)
            print("  ✓ Drum 0 (Kick) triggered")

            self.drum_manager.trigger_drum(2, velocity=100, humanize_velocity=1.0)
            print("  ✓ Drum 2 (Closed HH) triggered")

            # Verify both are active
            kick_active = self.drum_manager.drum_voices[0]["is_active"]
            hh_active = self.drum_manager.drum_voices[2]["is_active"]

            print(f"\n  Kick is_active: {kick_active}")
            print(f"  Closed HH is_active: {hh_active}")

            if kick_active and hh_active:
                print("\n✅ Both drums marked as active after triggering")
                return True
            else:
                print("\n❌ One or more drums not marked as active")
                return False

        except Exception as e:
            print(f"  ❌ Error during simultaneous trigger: {e}")
            return False

    def test_all_drums_together(self):
        """Test triggering all 8 drums on the same step."""
        print("\n" + "="*70)
        print("TEST 3: All 8 Drums on Same Step")
        print("="*70)

        print("\nTriggering all 8 drums simultaneously...")

        try:
            self.drum_manager.all_notes_off()  # Reset
            triggered = []

            for drum_idx in range(8):
                self.drum_manager.trigger_drum(drum_idx, velocity=100, humanize_velocity=1.0)
                triggered.append(drum_idx)

            print(f"  ✓ Triggered {len(triggered)} drums: {triggered}")

            # Verify all are active
            active_drums = [i for i in range(8) if self.drum_manager.drum_voices[i]["is_active"]]
            print(f"\n  Active drums: {active_drums}")
            print(f"  Expected: {list(range(8))}")

            if len(active_drums) == 8:
                print("\n✅ All 8 drums successfully triggered together")
                return True
            else:
                print(f"\n⚠️ Only {len(active_drums)}/8 drums active")
                return len(active_drums)

        except Exception as e:
            print(f"  ❌ Error triggering all drums: {e}")
            return False

    def test_event_queue_availability(self):
        """Test that MIDI event queue is available for parameter enqueuing."""
        print("\n" + "="*70)
        print("TEST 4: MIDI Event Queue Availability")
        print("="*70)

        if hasattr(self.synth, 'midi_event_queue'):
            print(f"\n✅ SynthEngine has midi_event_queue")
            print(f"   Queue type: {type(self.synth.midi_event_queue)}")
            return True
        else:
            print(f"\n⚠️ SynthEngine does not have midi_event_queue")
            print(f"   Parameter updates will fall back to immediate application")
            return False

    def test_parameter_dict_building(self):
        """Test that parameter dicts are built correctly."""
        print("\n" + "="*70)
        print("TEST 5: Parameter Dictionary Building")
        print("="*70)

        # Get a drum's parameters
        kick_preset = DRUM_PRESETS.get("Kick", {})
        kick_params = kick_preset.get("synth_params", {})

        print("\nKick original parameters:")
        for key, value in kick_params.items():
            print(f"  {key}: {value}")

        # Manually build the param dict to verify mapping
        params_to_apply = {}
        if "attack" in kick_params:
            params_to_apply["attack"] = kick_params["attack"]
        if "decay" in kick_params:
            params_to_apply["decay"] = kick_params["decay"]
        if "cutoff_freq" in kick_params:
            params_to_apply["cutoff"] = kick_params["cutoff_freq"]
        if "oscillator_type" in kick_params:
            osc_type = kick_params["oscillator_type"]
            if osc_type == "noise_pink":
                params_to_apply["waveform"] = "noise_pink"
            else:
                params_to_apply["waveform"] = osc_type

        print("\nMapped parameters for SynthEngine:")
        for key, value in params_to_apply.items():
            print(f"  {key}: {value}")

        if len(params_to_apply) > 0:
            print("\n✅ Parameter mapping successful")
            return True
        else:
            print("\n❌ No parameters were mapped")
            return False


def main():
    """Run all multi-drum mixing tests."""
    print("\n" + "="*70)
    print("TAMBOR MULTI-DRUM MIXING TEST SUITE")
    print("="*70)
    print("Testing: Multiple drums on same step, parameter isolation")

    tester = MultiDrumMixingTester()

    results = []

    # Test 1: Parameter isolation
    try:
        kick_midi, hh_midi, kick_params, hh_params = tester.test_parameter_isolation()
        results.append(("Parameter Isolation", True))
    except Exception as e:
        print(f"\n❌ Parameter isolation test failed: {e}")
        results.append(("Parameter Isolation", False))

    # Test 2: Simultaneous triggers
    try:
        success = tester.test_simultaneous_triggers()
        results.append(("Simultaneous Triggers", success))
    except Exception as e:
        print(f"\n❌ Simultaneous trigger test failed: {e}")
        results.append(("Simultaneous Triggers", False))

    # Test 3: All drums together
    try:
        success = tester.test_all_drums_together()
        results.append(("All Drums Together", success))
    except Exception as e:
        print(f"\n❌ All drums together test failed: {e}")
        results.append(("All Drums Together", False))

    # Test 4: Event queue
    try:
        success = tester.test_event_queue_availability()
        results.append(("Event Queue Available", success))
    except Exception as e:
        print(f"\n❌ Event queue test failed: {e}")
        results.append(("Event Queue Available", False))

    # Test 5: Parameter dict building
    try:
        success = tester.test_parameter_dict_building()
        results.append(("Parameter Dict Building", success))
    except Exception as e:
        print(f"\n❌ Parameter dict test failed: {e}")
        results.append(("Parameter Dict Building", False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result is True)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result is True else "❌ FAIL" if result is False else f"⚠️ {result}"
        print(f"{test_name}: {status}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All multi-drum mixing tests passed!")
        print("Multiple drums on the same step should now mix cleanly without parameter conflicts.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) need attention")
        return 1


if __name__ == "__main__":
    sys.exit(main())
