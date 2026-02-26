#!/usr/bin/env python3
# ABOUTME: Script to generate compendium JSON data files from ChordLibrary and music theory
# ABOUTME: Extracts chords, scales, instruments, genres, and creates category definitions

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from music.chord_library import ChordLibrary

def generate_chords_json():
    """Generate chords.json from ChordLibrary."""
    library = ChordLibrary()

    items = []
    chord_id_counter = 0

    for key in library.KEYS:
        for chord_type in library.get_chord_types(key):
            notes = library.get_chord_notes(key, chord_type)
            chord_id_counter += 1

            # Map chord type to intervals (simplified - actual intervals vary by chord)
            interval_map = {
                'Major': ['1', '3', '5'],
                'Minor': ['1', 'b3', '5'],
                'Diminished': ['1', 'b3', 'b5'],
                'Augmented': ['1', '3', '#5'],
                'Major 7th': ['1', '3', '5', '7'],
                'Minor 7th': ['1', 'b3', '5', 'b7'],
                'Dominant 7th': ['1', '3', '5', 'b7'],
                'Diminished 7th': ['1', 'b3', 'b5', 'bb7'],
                'Sus2': ['1', '2', '5'],
                'Sus4': ['1', '4', '5'],
                'Major 6th': ['1', '3', '5', '6'],
                'Minor 6th': ['1', 'b3', '5', '6'],
                '9th': ['1', '3', '5', 'b7', '9'],
                'Major 9th': ['1', '3', '5', '7', '9'],
                'Minor 9th': ['1', 'b3', '5', 'b7', '9'],
            }

            item = {
                "id": f"{key}_{chord_type.replace(' ', '_').lower()}",
                "name": f"{key} {chord_type}",
                "category": "chords",
                "description": f"A {chord_type} chord based on {key}.",
                "details": f"Notes: {', '.join(notes)}. This is a {chord_type.lower()} chord in the key of {key}.",
                "examples": [f"Play as root voicing: {'-'.join(notes)}", f"Melodic use in C major or relative minor keys"],
                "related": [],  # Can be filled in later with cross-references
                "metadata": {
                    "notes": notes,
                    "intervals": interval_map.get(chord_type, []),
                    "root": key,
                    "type": chord_type
                }
            }
            items.append(item)

    return {"items": items}


def generate_scales_json():
    """Generate scales.json with common scales and modes."""
    scales_data = [
        {
            "id": "major_scale",
            "name": "Major Scale (Ionian)",
            "category": "scales",
            "description": "The most fundamental scale in Western music. Also known as the Ionian mode.",
            "details": "The major scale consists of 7 notes with the pattern: W-W-H-W-W-W-H (W=whole step, H=half step). It's the basis for major keys and is widely used in all genres.",
            "examples": ["C major: C-D-E-F-G-A-B", "G major: G-A-B-C-D-E-F#"],
            "related": ["dorian_mode", "phrygian_mode", "lydian_mode", "mixolydian_mode", "aeolian_mode", "locrian_mode"],
            "metadata": {
                "intervals": [0, 2, 4, 5, 7, 9, 11],
                "semitones": "2-2-1-2-2-2-1",
                "modes_count": 7,
                "relative_minor": "natural_minor"
            }
        },
        {
            "id": "natural_minor_scale",
            "name": "Natural Minor Scale (Aeolian)",
            "category": "scales",
            "description": "The relative minor to the major scale. Also called the Aeolian mode.",
            "details": "The natural minor scale has 7 notes with the pattern: W-H-W-W-H-W-W. It's the minor scale most used in classical and popular music.",
            "examples": ["A minor: A-B-C-D-E-F-G", "E minor: E-F#-G-A-B-C-D"],
            "related": ["major_scale", "harmonic_minor", "melodic_minor"],
            "metadata": {
                "intervals": [0, 2, 3, 5, 7, 8, 10],
                "semitones": "2-1-2-2-1-2-2",
                "relative_major": "major_scale"
            }
        },
        {
            "id": "harmonic_minor",
            "name": "Harmonic Minor Scale",
            "category": "scales",
            "description": "A minor scale with a raised 7th degree, creating a leading tone.",
            "details": "Pattern: W-H-W-W-H-W+H-H. The raised 7th creates a leading tone that resolves to the root, making it useful for harmony but creating a distinctive sound.",
            "examples": ["A harmonic minor: A-B-C-D-E-F-G#", "E harmonic minor: E-F#-G-A-B-C-D#"],
            "related": ["natural_minor_scale", "melodic_minor"],
            "metadata": {
                "intervals": [0, 2, 3, 5, 7, 8, 11],
                "semitones": "2-1-2-2-1-3-1"
            }
        },
        {
            "id": "melodic_minor",
            "name": "Melodic Minor Scale",
            "category": "scales",
            "description": "A minor scale with raised 6th and 7th degrees in ascending order.",
            "details": "Ascending: W-H-W-W-W-W-H. Descending: natural minor pattern. Used in classical melodies and jazz improvisation.",
            "examples": ["A melodic minor ascending: A-B-C-D-E-F#-G#", "A melodic minor descending: A-G-F-E-D-C-B"],
            "related": ["natural_minor_scale", "harmonic_minor"],
            "metadata": {
                "intervals": [0, 2, 3, 5, 7, 9, 11],
                "semitones": "2-1-2-2-2-2-1"
            }
        },
        {
            "id": "pentatonic_major",
            "name": "Major Pentatonic Scale",
            "category": "scales",
            "description": "A 5-note major scale with the 4th and 7th degrees removed.",
            "details": "Pattern: W-W-W+H-W-W+H (5 notes). Very melodic and commonly used in folk music, blues, and contemporary music.",
            "examples": ["C major pentatonic: C-D-E-G-A", "G major pentatonic: G-A-B-D-E"],
            "related": ["pentatonic_minor", "major_scale"],
            "metadata": {
                "intervals": [0, 2, 4, 7, 9],
                "semitones": "2-2-3-2-3",
                "note_count": 5
            }
        },
        {
            "id": "pentatonic_minor",
            "name": "Minor Pentatonic Scale",
            "category": "scales",
            "description": "A 5-note scale based on the natural minor with the 2nd and 6th degrees removed.",
            "details": "Pattern: W+H-W-W-W+H-W (5 notes). Essential for blues, rock, and contemporary music. Very singable and expressive.",
            "examples": ["A minor pentatonic: A-C-D-E-G", "E minor pentatonic: E-G-A-B-D"],
            "related": ["pentatonic_major", "natural_minor_scale", "blues_scale"],
            "metadata": {
                "intervals": [0, 3, 5, 7, 10],
                "semitones": "3-2-2-3-2",
                "note_count": 5
            }
        },
        {
            "id": "blues_scale",
            "name": "Blues Scale",
            "category": "scales",
            "description": "A minor pentatonic with an added flat 5 (blue note).",
            "details": "The 6-note scale includes the characteristic 'blue note' (flat 5). Used extensively in blues, rock, and jazz.",
            "examples": ["A blues: A-C-D-Eb-E-G", "E blues: E-G-A-B-B-D"],
            "related": ["pentatonic_minor", "blues_music"],
            "metadata": {
                "intervals": [0, 3, 5, 6, 7, 10],
                "semitones": "3-2-1-1-3-2",
                "note_count": 6,
                "blue_note": "flat_5"
            }
        }
    ]

    return {"items": scales_data}


def generate_instruments_json():
    """Generate instruments.json with common instruments."""
    instruments_data = [
        {
            "id": "piano",
            "name": "Piano",
            "category": "instruments",
            "description": "A keyboard instrument with 88 keys spanning 7+ octaves.",
            "details": "The piano is a percussion instrument with strings struck by hammers. Used across all genres - classical, jazz, pop, and more. Excellent for learning music theory.",
            "examples": ["Classical: Chopin, Debussy", "Jazz: Bill Evans, Keith Jarrett", "Pop: Elton John, Billy Joel"],
            "related": [],
            "metadata": {
                "family": "keyboard",
                "range": "A0-C8",
                "strings": True,
                "polyphony": "unlimited",
                "learning_curve": "medium"
            }
        },
        {
            "id": "guitar",
            "name": "Guitar (Acoustic/Electric)",
            "category": "instruments",
            "description": "A string instrument with typically 6 strings and 20+ frets.",
            "details": "Acoustic and electric variants. Extremely versatile - used in blues, rock, jazz, folk, classical. Great for chord work and melody.",
            "examples": ["Rock: Jimi Hendrix, Eddie Van Halen", "Jazz: Django Reinhardt, Wes Montgomery", "Classical: Andrés Segovia"],
            "related": [],
            "metadata": {
                "family": "strings",
                "variants": ["acoustic", "electric", "classical"],
                "strings_count": 6,
                "frets": "20-24",
                "polyphony": "6",
                "learning_curve": "medium"
            }
        },
        {
            "id": "violin",
            "name": "Violin",
            "category": "instruments",
            "description": "A bowed string instrument with 4 strings.",
            "details": "One of the highest-pitched orchestral instruments. Essential in classical, baroque, and folk music. Also used in jazz and contemporary music.",
            "examples": ["Classical: Niccolò Paganini", "Jazz: Stephan Grappelli", "Folk: Lindsey Stirling"],
            "related": [],
            "metadata": {
                "family": "strings",
                "strings_count": 4,
                "range": "G3-E7",
                "polyphony": "1",
                "learning_curve": "hard"
            }
        },
        {
            "id": "drums",
            "name": "Drums (Drum Kit)",
            "category": "instruments",
            "description": "A collection of percussion instruments including kick, snare, toms, hi-hat, and cymbals.",
            "details": "The foundation of rhythm in rock, pop, jazz, and modern music. Requires coordination between all four limbs. Essential for timekeeping.",
            "examples": ["Rock: Keith Moon, John Bonham", "Jazz: Art Blakey, Tony Williams", "Pop: Ringo Starr, Travis Barker"],
            "related": [],
            "metadata": {
                "family": "percussion",
                "components": ["kick", "snare", "tom", "hi-hat", "crash", "ride"],
                "tuning": "pitch_variable",
                "polyphony": "multiple",
                "learning_curve": "hard"
            }
        },
        {
            "id": "trumpet",
            "name": "Trumpet",
            "category": "instruments",
            "description": "A brass instrument with 3 valves, known for bright, cutting tone.",
            "details": "Essential in jazz, orchestral, and brass band music. Requires strong breath control and embouchure. Can play loud, cutting notes or soft, mellow ones.",
            "examples": ["Jazz: Miles Davis, Dizzy Gillespie", "Classical: Maurice André", "Pop: Herb Alpert"],
            "related": [],
            "metadata": {
                "family": "brass",
                "range": "F#3-B6",
                "valves": 3,
                "polyphony": "1",
                "learning_curve": "hard"
            }
        },
        {
            "id": "bass",
            "name": "Bass Guitar (Electric/Acoustic)",
            "category": "instruments",
            "description": "A string instrument with typically 4 strings, lower register than guitar.",
            "details": "Provides the bridge between harmony and rhythm in most modern music. Electric bass is standard in rock, pop, funk, and jazz.",
            "examples": ["Rock: John Entwistle, John Paul Jones", "Funk: James Jamerson, Victor Wooten", "Jazz: Charles Mingus"],
            "related": [],
            "metadata": {
                "family": "strings",
                "variants": ["electric", "acoustic", "fretless"],
                "strings_count": 4,
                "range": "B0-D5",
                "polyphony": "4",
                "learning_curve": "medium"
            }
        }
    ]

    return {"items": instruments_data}


def generate_genres_json():
    """Generate genres.json with music genres."""
    genres_data = [
        {
            "id": "jazz",
            "name": "Jazz",
            "category": "genres",
            "description": "An American art form emphasizing improvisation, syncopation, and blues influences.",
            "details": "Originated in New Orleans in the early 20th century. Combines African rhythms, European harmony, and American culture. Emphasizes individual expression and ensemble interaction.",
            "examples": ["Bebop: Charlie Parker, Dizzy Gillespie", "Cool Jazz: Miles Davis, John Coltrane", "Fusion: Herbie Hancock, Weather Report"],
            "related": ["blues", "swing"],
            "metadata": {
                "era": "1900s-present",
                "origin": "New Orleans, USA",
                "key_characteristics": ["improvisation", "syncopation", "swing", "blues_influence"],
                "instruments": ["trumpet", "saxophone", "piano", "bass", "drums"]
            }
        },
        {
            "id": "blues",
            "name": "Blues",
            "category": "genres",
            "description": "American music genre with roots in African American spirituals and work songs.",
            "details": "Characterized by 12-bar chord progression, blues scale, and expressive bending. Central to rock, jazz, and R&B. About expressing emotion and hardship.",
            "examples": ["Robert Johnson", "Muddy Waters", "B.B. King", "Stevie Ray Vaughan"],
            "related": ["jazz", "rock"],
            "metadata": {
                "era": "1890s-present",
                "origin": "Mississippi Delta, USA",
                "key_characteristics": ["12-bar progression", "blues_scale", "bending", "call_and_response"],
                "chord_progression": "I-IV-I-V-IV-I"
            }
        },
        {
            "id": "rock",
            "name": "Rock",
            "category": "genres",
            "description": "Popular music genre characterized by guitars, strong rhythm, and youth culture.",
            "details": "Emerged in the 1950s combining blues, country, and pop. Emphasizes electric guitar, drums, and vocals. Extremely diverse with countless subgenres.",
            "examples": ["Classic Rock: The Beatles, Led Zeppelin", "Hard Rock: AC/DC, Aerosmith", "Alternative: Nirvana, Radiohead"],
            "related": ["blues", "pop"],
            "metadata": {
                "era": "1950s-present",
                "origin": "United States",
                "key_characteristics": ["electric_guitar", "strong_rhythm", "youth_culture"],
                "instruments": ["electric_guitar", "bass", "drums", "vocals"]
            }
        },
        {
            "id": "classical",
            "name": "Classical",
            "category": "genres",
            "description": "Western art music tradition with written compositions and formal structure.",
            "details": "Spans from Renaissance to contemporary classical. Emphasizes complex harmony, orchestration, and structured forms like sonata and symphony.",
            "examples": ["Baroque: Bach, Vivaldi", "Classical: Mozart, Beethoven", "Romantic: Chopin, Wagner"],
            "related": [],
            "metadata": {
                "era": "1600s-present",
                "key_characteristics": ["written_composition", "formal_structure", "harmony", "orchestration"],
                "main_periods": ["renaissance", "baroque", "classical", "romantic", "contemporary"]
            }
        },
        {
            "id": "pop",
            "name": "Pop",
            "category": "genres",
            "description": "Contemporary commercial music designed for mass appeal and radio play.",
            "details": "Emerged in the 1950s-60s. Characterized by catchy melodies, simple chord progressions, and relatable lyrics. Most commercially successful genre.",
            "examples": ["The Beatles", "Michael Jackson", "Taylor Swift", "The Weeknd"],
            "related": ["rock", "hip_hop"],
            "metadata": {
                "era": "1950s-present",
                "key_characteristics": ["catchy_melody", "simple_harmony", "radio_friendly"],
                "typical_length": "3-4 minutes"
            }
        },
        {
            "id": "hip_hop",
            "name": "Hip Hop / Rap",
            "category": "genres",
            "description": "Urban music genre emphasizing rhythmic spoken/sung lyrics over instrumental beats.",
            "details": "Originated in the 1970s Bronx. Core elements: DJing, rapping, breaking, and graffiti art. Rhythm and wordplay are essential.",
            "examples": ["Old School: Grandmaster Flash, Run-DMC", "Golden Age: Nas, Biggie, Wu-Tang", "Modern: Drake, Kendrick Lamar"],
            "related": ["pop", "r_and_b"],
            "metadata": {
                "era": "1970s-present",
                "origin": "Bronx, New York",
                "key_characteristics": ["rhythm", "wordplay", "beats", "sampling"],
                "elements": ["djing", "rapping", "breaking", "graffiti"]
            }
        }
    ]

    return {"items": genres_data}


def generate_categories_json():
    """Generate categories.json defining the hierarchy."""
    categories_data = {
        "items": [
            {
                "id": "music",
                "name": "Music",
                "description": "The root of the music knowledge hierarchy",
                "children": ["chords", "scales", "instruments", "genres", "theory"],
                "icon": "🎵"
            },
            {
                "id": "chords",
                "name": "Chords",
                "parent": "music",
                "description": "Collections of notes played simultaneously",
                "icon": "🎹"
            },
            {
                "id": "scales",
                "name": "Scales",
                "parent": "music",
                "description": "Ordered collections of notes in ascending/descending pitch",
                "icon": "📊"
            },
            {
                "id": "instruments",
                "name": "Instruments",
                "parent": "music",
                "description": "Devices for producing musical sounds",
                "icon": "🎸"
            },
            {
                "id": "genres",
                "name": "Genres",
                "parent": "music",
                "description": "Styles and categories of music",
                "icon": "🎧"
            },
            {
                "id": "theory",
                "name": "Music Theory",
                "parent": "music",
                "description": "Fundamental concepts and principles of music",
                "icon": "📚"
            }
        ]
    }

    return categories_data


def main():
    """Generate all JSON files."""
    output_dir = Path(__file__).parent / "data" / "compendium"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Generating compendium data files...")

    # Generate chords
    print("  → Generating chords.json...")
    chords_data = generate_chords_json()
    with open(output_dir / "chords.json", "w") as f:
        json.dump(chords_data, f, indent=2)
    print(f"    Created {len(chords_data['items'])} chord entries")

    # Generate scales
    print("  → Generating scales.json...")
    scales_data = generate_scales_json()
    with open(output_dir / "scales.json", "w") as f:
        json.dump(scales_data, f, indent=2)
    print(f"    Created {len(scales_data['items'])} scale entries")

    # Generate instruments
    print("  → Generating instruments.json...")
    instruments_data = generate_instruments_json()
    with open(output_dir / "instruments.json", "w") as f:
        json.dump(instruments_data, f, indent=2)
    print(f"    Created {len(instruments_data['items'])} instrument entries")

    # Generate genres
    print("  → Generating genres.json...")
    genres_data = generate_genres_json()
    with open(output_dir / "genres.json", "w") as f:
        json.dump(genres_data, f, indent=2)
    print(f"    Created {len(genres_data['items'])} genre entries")

    # Generate categories
    print("  → Generating categories.json...")
    categories_data = generate_categories_json()
    with open(output_dir / "categories.json", "w") as f:
        json.dump(categories_data, f, indent=2)
    print(f"    Created {len(categories_data['items'])} category definitions")

    print("\n✓ All data files generated successfully!")
    print(f"  Location: {output_dir}")


if __name__ == "__main__":
    main()
