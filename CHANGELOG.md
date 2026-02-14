# Changelog

All notable changes to the Acordes MIDI Piano TUI Application will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-14

### Added
- **Musical Staff Display**: Traditional music notation with side-by-side Bass and Treble clefs
  - Bass Clef (F) displays notes below B3 (MIDI note 59)
  - Treble Clef (G) displays notes B3 and above
  - Notes appear as yellow dots (●) on staff lines in real-time
  - Sharp notes clearly marked with ♯ symbol
  - Reference note labels (E4, G4, B4, D5, F5 for treble; G2, B2, D3, F3, A3 for bass)
  - Side-by-side layout with proper spacing and alignment
  - Staff width: 30 characters per clef for optimal display

- **Chord Display Component**: Dedicated widget for showing detected chords
  - Displays above the piano keyboard for better visibility
  - Centered alignment with consistent height to prevent layout shifts
  - Color-coded display:
    - Single notes: Cyan (#00d7ff)
    - Detected chords: Green (#00ff87)
    - Multiple notes (no chord): Gold (#ffd700)
  - Placeholder dash (─) when no notes playing to maintain layout stability

- **Layout Improvements**:
  - MIDI status message ("🎵 MIDI device connected - Play some notes!") moved below title
  - Centered status message for better visual hierarchy
  - Optimized section heights for better space distribution
  - Title section: ACORDES ASCII art + status
  - Chord display: Positioned above piano
  - Piano section: 3-octave visual keyboard
  - Staff section: Side-by-side Bass and Treble clefs

### Changed
- Enhanced piano mode layout with 4 distinct sections
- Improved visual spacing between UI elements
- Refined color scheme for better readability
- Optimized staff display for terminal width compatibility

### Fixed
- Staff alignment issues when notes appear/disappear
- Chord text positioning and centering
- Layout shifting when chord names are displayed
- Bass and Treble clef horizontal alignment
- Rich markup errors when displaying multiple notes
- Consistent width maintenance across empty and note-filled staffs

## [0.1.0] - Initial Release

### Added
- **Config Mode**: MIDI device selection and configuration
- **Piano Mode**: Real-time visual 3-octave piano keyboard
  - Note highlighting in red
  - Real-time MIDI input processing
- **Chord Compendium**: Reference library of chords
  - All 12 musical keys
  - 15+ chord types per key
  - Chord note display
- **Chord Detection**: Automatic recognition of played chords
  - Support for basic triads (major, minor, diminished, augmented)
  - Extended chords (7th, 9th, 11th, 13th)
  - Suspended and added tone chords
- **MIDI Support**:
  - Cross-platform MIDI device detection
  - Real-time MIDI input handling
  - Device configuration persistence
- **TUI Framework**: Built with Textual
  - Keyboard navigation
  - Tab-based mode switching
  - Quit confirmation dialog
  - Responsive terminal layout

### Technical Stack
- Python 3.8+
- Textual (TUI framework)
- mido (MIDI I/O)
- python-rtmidi (Real-time MIDI backend)
- mingus (Music theory)

---

## Release Notes

### Version 1.0.0 - Major Milestone
This release represents a major milestone with the addition of traditional musical staff notation. The application now provides a complete visual experience combining:
- ASCII piano keyboard visualization
- Real-time chord detection and display
- Traditional music notation with Bass and Treble clefs

The side-by-side clef layout follows the standard grand staff convention used in piano sheet music, making it intuitive for musicians to read their playing in standard notation.

### Future Considerations
Potential areas for future enhancement:
- Recording and playback functionality
- MIDI file import/export
- Customizable key ranges
- Additional clefs (Alto, Tenor)
- Ledger lines for notes outside staff range
- Note duration display
- Metronome integration
- Multiple simultaneous MIDI device support
