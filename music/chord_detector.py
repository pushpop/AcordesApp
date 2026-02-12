"""Chord recognition using mingus."""
from typing import Set, List, Optional
import mingus.core.chords as chords
import mingus.core.notes as notes


class ChordDetector:
    """Detects chords from MIDI note numbers using mingus."""

    # MIDI note 60 = C4 (middle C)
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    def __init__(self):
        pass

    def midi_to_note_name(self, midi_note: int) -> str:
        """Convert MIDI note number to note name with octave.

        Args:
            midi_note: MIDI note number (0-127).

        Returns:
            Note name with octave (e.g., "C4", "D#5").
        """
        octave = (midi_note // 12) - 1
        note_index = midi_note % 12
        note_name = self.NOTE_NAMES[note_index]
        return f"{note_name}{octave}"

    def midi_to_note_name_no_octave(self, midi_note: int) -> str:
        """Convert MIDI note number to note name without octave.

        Args:
            midi_note: MIDI note number (0-127).

        Returns:
            Note name without octave (e.g., "C", "D#").
        """
        note_index = midi_note % 12
        return self.NOTE_NAMES[note_index]

    def detect_chord(self, midi_notes: Set[int]) -> Optional[str]:
        """Detect chord from set of MIDI note numbers.

        Supports all chord types including:
        - Triads (major, minor, diminished, augmented)
        - 7th chords (maj7, min7, dom7, dim7, etc.)
        - Extended chords (9th, 11th, 13th)
        - All inversions (1st, 2nd, 3rd, etc.)

        Args:
            midi_notes: Set of MIDI note numbers currently pressed.

        Returns:
            Chord name if detected, None if no valid chord or <2 notes.
        """
        if len(midi_notes) < 2:
            return None

        # Convert MIDI notes to note names (without octave)
        note_names = [self.midi_to_note_name_no_octave(n) for n in sorted(midi_notes)]

        # Remove duplicates while preserving order
        unique_notes = []
        seen = set()
        for note in note_names:
            if note not in seen:
                unique_notes.append(note)
                seen.add(note)

        if len(unique_notes) < 2:
            return None

        try:
            # Use mingus to determine the chord with shorthand notation
            # This will detect triads, 7ths, 9ths, 11ths, 13ths, and more
            detected_chords = chords.determine(unique_notes, shorthand=True)

            if detected_chords:
                # Return the first (most likely) detected chord
                chord_name = detected_chords[0]

                # Check if this is an inversion by comparing bass note with root
                bass_note = unique_notes[0]  # Lowest note played

                # Detect inversion by checking if chord is in root position
                # mingus.determine returns chords in format like "CM" or "Am7"
                # Extract the root note from the chord name
                chord_root = self._extract_root_from_chord_name(chord_name)

                if chord_root and bass_note != chord_root:
                    # This is an inversion - add slash notation
                    return f"{chord_name}/{bass_note}"

                return chord_name
            else:
                # If mingus can't determine, show the notes as a chord stack
                return f"{unique_notes[0]} + {len(unique_notes)-1} notes"
        except Exception as e:
            print(f"Error detecting chord: {e}")
            return None

    def _extract_root_from_chord_name(self, chord_name: str) -> Optional[str]:
        """Extract the root note from a chord name.

        Args:
            chord_name: Chord name like "CM", "Am7", "G#dim"

        Returns:
            Root note like "C", "A", "G#"
        """
        if not chord_name:
            return None

        # Handle sharp notes (two characters)
        if len(chord_name) > 1 and chord_name[1] == '#':
            return chord_name[:2]
        # Handle flat notes (two characters)
        elif len(chord_name) > 1 and chord_name[1] == 'b':
            return chord_name[:2]
        # Single character root note
        else:
            return chord_name[0]

    def get_note_names(self, midi_notes: Set[int]) -> List[str]:
        """Get list of note names with octaves from MIDI notes.

        Args:
            midi_notes: Set of MIDI note numbers.

        Returns:
            List of note names with octaves, sorted by pitch.
        """
        return [self.midi_to_note_name(n) for n in sorted(midi_notes)]
