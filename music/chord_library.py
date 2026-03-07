"""Complete chord compendium data structure."""
from typing import Dict, List, Set, Optional
import mingus.core.chords as chords


class ChordLibrary:
    """Generates and stores a complete library of chords."""

    # All 12 chromatic notes
    KEYS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    # Enharmonic equivalents mapping (flats to sharps for normalization)
    ENHARMONIC_MAP = {
        'Db': 'C#',
        'Eb': 'D#',
        'Gb': 'F#',
        'Ab': 'G#',
        'Bb': 'A#',
    }

    # Common chord types with their mingus shorthand
    CHORD_TYPES = [
        ('Major', 'M'),
        ('Minor', 'm'),
        ('Diminished', 'dim'),
        ('Augmented', 'aug'),
        ('Major 7th', 'M7'),
        ('Minor 7th', 'm7'),
        ('Dominant 7th', '7'),
        ('Diminished 7th', 'dim7'),
        ('Sus2', 'sus2'),
        ('Sus4', 'sus4'),
        ('Major 6th', 'M6'),
        ('Minor 6th', 'm6'),
        ('9th', '9'),
        ('Major 9th', 'M9'),
        ('Minor 9th', 'm9'),
    ]

    def __init__(self):
        self.library: Dict[str, Dict[str, List[str]]] = {}
        self._generate_library()

    def _normalize_note(self, note: str) -> str:
        """Convert note to canonical form (sharps only, no flats).

        Args:
            note: Note name (e.g., "C", "C#", "Db", "Eb").

        Returns:
            Canonical note name using sharps (e.g., "C#" instead of "Db").
        """
        return self.ENHARMONIC_MAP.get(note, note)

    def _generate_library(self):
        """Generate the complete chord library."""
        for key in self.KEYS:
            self.library[key] = {}

            for chord_name, shorthand in self.CHORD_TYPES:
                try:
                    # Generate chord using mingus
                    chord_notes = chords.from_shorthand(f"{key}{shorthand}")

                    if chord_notes:
                        self.library[key][chord_name] = chord_notes
                except Exception as e:
                    # Some chord combinations might not be valid
                    pass

    def get_keys(self) -> List[str]:
        """Get list of all keys in the library.

        Returns:
            List of key names.
        """
        return self.KEYS

    def get_chord_types(self, key: str) -> List[str]:
        """Get list of chord types for a specific key.

        Args:
            key: Musical key (e.g., "C", "F#").

        Returns:
            List of chord type names for the key.
        """
        if key in self.library:
            return list(self.library[key].keys())
        return []

    def get_chord_notes(self, key: str, chord_type: str) -> List[str]:
        """Get notes for a specific chord.

        Args:
            key: Musical key (e.g., "C", "F#").
            chord_type: Chord type (e.g., "Major", "Minor 7th").

        Returns:
            List of note names in the chord.
        """
        if key in self.library and chord_type in self.library[key]:
            return self.library[key][chord_type]
        return []

    def get_all_chords(self) -> Dict[str, Dict[str, List[str]]]:
        """Get the entire chord library.

        Returns:
            Dictionary mapping keys to chord types to note lists.
        """
        return self.library

    def detect_chord_from_notes(self, note_names, bass_note: Optional[str] = None) -> Optional[str]:
        """Detect a chord from note names (without octaves).

        Matches the played notes against all chords in the library, including
        inversions. Returns the chord with root position or slash notation for
        inversions (e.g., "C Major" or "C Major/E").

        Handles enharmonic equivalents (e.g., Eb = D#) by normalizing to sharps.

        Args:
            note_names: Set or list of note names without octaves (e.g., {"C", "E", "G"})
            bass_note: Optional explicitly specified bass note for inversion detection.
                      If not provided, uses the first note if list, or lowest note if set.

        Returns:
            Chord name string ("C Major", "Am7", "G Major/B") or None if no match.
        """
        if len(note_names) < 2:
            return None

        # Handle both list and set inputs, preserving order if list
        if isinstance(note_names, list):
            unique_notes = note_names
            if not bass_note:
                bass_note = unique_notes[0]  # Use first (lowest MIDI) note as bass
        else:
            # If set, sort by pitch order
            unique_notes = sorted(list(note_names), key=lambda n: self.KEYS.index(n) if n in self.KEYS else 12)
            if not bass_note:
                bass_note = unique_notes[0]

        if len(unique_notes) < 2:
            return None

        # Normalize played notes (convert Eb to D#, etc.)
        normalized_played = set(self._normalize_note(n) for n in unique_notes)
        # Normalize bass note for comparison
        normalized_bass_note = self._normalize_note(bass_note)

        # Try each note as a potential root
        for potential_root in self.KEYS:
            if potential_root not in self.library:
                continue

            # Check all chord types for this root
            for chord_type, chord_notes in self.library[potential_root].items():
                # Normalize chord notes from library (convert Eb to D#, etc.)
                normalized_chord = set(self._normalize_note(n) for n in chord_notes)

                # Check if the played notes match this chord
                if normalized_chord == normalized_played:
                    # Found a match! Now check if it's in root position or inverted
                    if normalized_bass_note == potential_root:
                        # Root position
                        return f"{potential_root} {chord_type}"
                    else:
                        # Inversion - add slash notation
                        return f"{potential_root} {chord_type}/{bass_note}"

        # No matching chord found
        return None
