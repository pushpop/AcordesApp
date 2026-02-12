"""Chord reference tree view screen."""
from textual.widget import Widget
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Tree, Label
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from music.chord_library import ChordLibrary


class CompendiumMode(Widget):
    """Widget for browsing the chord compendium."""

    CSS = """
    CompendiumMode {
        align: center middle;
    }

    #compendium-container {
        width: 80;
        height: 30;
        border: thick #ffd700;
        background: #1a1a1a;
        padding: 1 2;
    }

    #title {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: #ffd700;
        margin-bottom: 1;
    }

    #tree-container {
        width: 100%;
        height: 1fr;
        border: solid #ffd700;
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

    def __init__(self, chord_library: 'ChordLibrary'):
        super().__init__()
        self.chord_library = chord_library

    def compose(self):
        """Compose the compendium mode layout."""
        with Vertical(id="compendium-container"):
            yield Label("📖 Chord Compendium", id="title")
            with Container(id="tree-container"):
                yield Tree("Chords", id="chord-tree")
            yield Label("", id="chord-info")
            yield Label(
                "↑↓: Navigate | Enter: Expand/Collapse | Space: Expand All",
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

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        """Handle tree node selection."""
        node = event.node
        label = str(node.label)

        # Display chord information
        info_label = self.query_one("#chord-info", Label)

        if "[" in label and "]" in label:
            # This is a chord node with notes
            info_label.update(label)
        else:
            # This is a key node
            info_label.update(f"Select a chord to view its notes")

