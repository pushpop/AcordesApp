"""Complete chord compendium data structure."""
from typing import Dict, List
import mingus.core.chords as chords


class ChordLibrary:
    """Generates and stores a complete library of chords."""

    # All 12 chromatic notes
    KEYS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

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
