"""Chord reference tree view screen."""
from textual.widget import Widget
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Tree, Label
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from components.header_widget import HeaderWidget
from typing import TYPE_CHECKING, List, Dict, Optional

if TYPE_CHECKING:
    from music.chord_library import ChordLibrary
    from music.synth_engine import SynthEngine


class CompendiumMode(Widget):
    """Widget for browsing the chord compendium."""

    BINDINGS = [
        Binding("space", "play_chord", "Play Chord", show=True),
        Binding("e", "expand_all", "Expand All", show=True),
    ]

    CSS = """
    CompendiumMode {
        align: center middle;
        width: 100%;
        height: 100%;
        border: heavy $accent;
        padding: 1;
    }

    #compendium-container {
        width: 100%;
        height: 100%;
        background: #1a1a1a;
        padding: 1 2;
    }

    #tree-container {
        width: 100%;
        height: 1fr;
        border: solid $accent;
        margin: 1 0;
    }

    #chord-info {
        width: 100%;
        height: 3;
        content-align: center middle;
        color: #00ff87;
        margin: 1 0;
    }

    #instructions {
        width: 100%;
        content-align: center middle;
        color: #888888;
        text-style: italic;
    }
    """

    def __init__(self, chord_library: 'ChordLibrary', synth_engine: 'SynthEngine'):
        super().__init__()
        self.chord_library = chord_library
        self.synth_engine = synth_engine
        self.selected_notes: List[int] = []

    def compose(self):
        """Compose the compendium mode layout."""
        with Vertical(id="compendium-container"):
            yield HeaderWidget(title="CHORD COMPENDIUM", subtitle="Browse chords across all keys")
            with Container(id="tree-container"):
                yield Tree("Chords", id="chord-tree")
            yield Label("", id="chord-info")
            yield Label(
                "↑↓: Navigate | Enter: Expand/Collapse | Space: Play Chord | E: Expand All",
                id="instructions"
            )

    def on_mount(self):
        """Called when screen is mounted."""
        self._build_tree()
        # Focus the tree so keyboard navigation works immediately
        tree = self.query_one("#chord-tree", Tree)
        tree.focus()

    def _build_tree(self):
        """Build the chord tree structure."""
        tree = self.query_one("#chord-tree", Tree)
        tree.clear()

        # Add root
        tree.root.expand()

        # Add each key as a top-level node
        for key in self.chord_library.get_keys():
            key_node = tree.root.add(f"🎵 {key}", expand=False)

            # Add chord types under each key
            chord_types = self.chord_library.get_chord_types(key)
            for chord_type in chord_types:
                notes = self.chord_library.get_chord_notes(key, chord_type)
                notes_str = " ".join(notes)
                chord_node = key_node.add(f"{key} {chord_type}: [{notes_str}]")

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        """Handle tree node highlight (on navigation)."""
        node = event.node
        label = str(node.label)

        # Display chord information
        info_label = self.query_one("#chord-info", Label)

        if "[" in label and "]" in label:
            # This is a chord node with notes
            # Format: "C Major: [C E G]"
            info_label.update(label)
            
            # Extract notes from label
            try:
                notes_part = label.split("[")[1].split("]")[0]
                note_names = notes_part.split()
                # Store MIDI notes for playing (start from middle C/C4 = 60)
                self.selected_notes = self._note_names_to_midi(note_names)
                # Auto-play on highlight
                self.action_play_chord()
            except:
                self.selected_notes = []
        else:
            # This is a key node
            info_label.update(f"Select a chord to view its notes")
            self.selected_notes = []

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        """Handle tree node selection (Enter/Click)."""
        # NodeSelected also triggers play_chord via on_tree_node_highlighted
        # But we keep it to handle expansion/collapse
        pass

    def _note_names_to_midi(self, note_names: List[str]) -> List[int]:
        """Convert a list of note names to MIDI note numbers."""
        name_map = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 
                    'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 
                    'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
        
        midi_notes = []
        base_octave = 60 # C4
        
        # Ensure notes go up in pitch
        last_val = -1
        octave_offset = 0
        
        for name in note_names:
            # Normalize note name (mingus might use flats)
            name = name.replace("♭", "b").replace("♯", "#")
            val = name_map.get(name, 0)
            
            # If current note value is less than previous, it probably moved to next octave
            if val <= last_val:
                octave_offset += 12
            
            midi_notes.append(base_octave + val + octave_offset)
            last_val = val
            
        return midi_notes

    def action_play_chord(self):
        """Play the currently selected chord using the synth engine."""
        if not self.selected_notes:
            return

        # Stop any existing notes first (clean start)
        self.synth_engine.all_notes_off()
        
        # Play each note with a slight stagger (strum)
        # We use a small stagger for better musical feel
        stagger = 0.02
        
        for i, note in enumerate(self.selected_notes):
            if i == 0:
                self.synth_engine.note_on(note, 80)
            else:
                import threading
                # Staggered note onset
                threading.Timer(i * stagger, self.synth_engine.note_on, args=[note, 80]).start()
        
        # Automatically release the chord after a fixed duration
        # This is more responsive than a manual thread with sleep
        duration = 0.8
        def release_all():
            for note in self.selected_notes:
                self.synth_engine.note_off(note)
                
        import threading
        threading.Timer(duration, release_all).start()

    def action_expand_all(self):
        """Expand all nodes in the tree."""
        tree = self.query_one("#chord-tree", Tree)
        tree.root.expand_all()

