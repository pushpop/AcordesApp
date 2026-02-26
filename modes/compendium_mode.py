"""Music Knowledge Hub - comprehensive reference browser with hierarchical navigation."""
# ABOUTME: CompendiumMode implements a two-column Music Knowledge Hub with tree navigation
# ABOUTME: Combines chord library, scales, instruments, genres in expandable JSON-based system

import json
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Optional, Any
from textual.widget import Widget
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Tree, Label, Input
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from components.header_widget import HeaderWidget

if TYPE_CHECKING:
    from music.chord_library import ChordLibrary
    from music.synth_engine import SynthEngine


class CompendiumDataManager:
    """Load and cache music knowledge data from JSON files."""

    def __init__(self):
        """Initialize data manager and load all data."""
        self.data_dir = Path(__file__).parent.parent / "data" / "compendium"
        self.categories: Dict[str, Any] = {}
        self.chords: Dict[str, Any] = {}
        self.scales: Dict[str, Any] = {}
        self.instruments: Dict[str, Any] = {}
        self.genres: Dict[str, Any] = {}
        self.category_map: Dict[str, str] = {}  # id -> category_name mapping
        self._load_all_data()

    def _load_json_file(self, filename: str) -> Dict[str, Any]:
        """Load a JSON file from the compendium directory."""
        filepath = self.data_dir / filename
        try:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load {filename}: {e}")
        return {"items": []}

    def _load_all_data(self):
        """Load all data files into memory."""
        # Load categories
        categories_data = self._load_json_file("categories.json")
        self.categories = {item["id"]: item for item in categories_data.get("items", [])}

        # Load each category's data
        for category_name in ["chords", "scales", "instruments", "genres"]:
            data = self._load_json_file(f"{category_name}.json")
            items = data.get("items", [])

            # Store by ID for quick lookup
            category_dict = {item["id"]: item for item in items}

            if category_name == "chords":
                self.chords = category_dict
            elif category_name == "scales":
                self.scales = category_dict
            elif category_name == "instruments":
                self.instruments = category_dict
            elif category_name == "genres":
                self.genres = category_dict

            # Build category map
            for item_id in category_dict:
                self.category_map[item_id] = category_name

    def get_categories(self) -> Dict[str, Any]:
        """Get all categories."""
        return self.categories

    def get_category_items(self, category_name: str) -> Dict[str, Any]:
        """Get all items in a category."""
        if category_name == "chords":
            return self.chords
        elif category_name == "scales":
            return self.scales
        elif category_name == "instruments":
            return self.instruments
        elif category_name == "genres":
            return self.genres
        return {}

    def get_item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a single item by ID."""
        category = self.category_map.get(item_id)
        if category:
            items = self.get_category_items(category)
            return items.get(item_id)
        return None

    def get_related_items(self, item_id: str) -> List[Dict[str, Any]]:
        """Get items related to a given item."""
        item = self.get_item_by_id(item_id)
        if not item or "related" not in item:
            return []

        related = []
        for related_id in item.get("related", []):
            related_item = self.get_item_by_id(related_id)
            if related_item:
                related.append(related_item)
        return related


class CompendiumTreeBuilder:
    """Build and manage the hierarchical tree view."""

    def __init__(self, data_manager: CompendiumDataManager):
        """Initialize tree builder with data manager."""
        self.data_manager = data_manager

    def build_category_tree(self, tree: Tree, category_name: str):
        """Build tree nodes for a specific category."""
        tree.clear()
        tree.root.expand()

        items = self.data_manager.get_category_items(category_name)

        # Sort items by name
        sorted_items = sorted(items.values(), key=lambda x: x["name"])

        for item in sorted_items:
            # Each item becomes a tree node with its ID stored in the data
            node = tree.root.add(item["name"])
            node.data = item["id"]  # Store ID for later retrieval

    def build_full_tree(self, tree: Tree):
        """Build complete hierarchical tree (Music -> Categories -> Items)."""
        tree.clear()
        tree.root.expand()

        categories = self.data_manager.get_categories()

        # Filter to main categories (those with 'children')
        main_categories = {k: v for k, v in categories.items() if "children" in v}
        sorted_cats = sorted(main_categories.values(), key=lambda x: x["name"])

        for category in sorted_cats:
            cat_node = tree.root.add(f"🎵 {category['name']}")
            cat_node.data = category["id"]

            # Add items under this category
            items = self.data_manager.get_category_items(category["id"])
            sorted_items = sorted(items.values(), key=lambda x: x["name"])

            for item in sorted_items:
                item_node = cat_node.add(item["name"])
                item_node.data = item["id"]


class CompendiumDetailPanel(Static):
    """Display detailed information about selected items."""

    def __init__(self, data_manager: CompendiumDataManager):
        """Initialize detail panel."""
        super().__init__()
        self.data_manager = data_manager
        self.current_item: Optional[Dict[str, Any]] = None

    def render_item(self, item: Dict[str, Any]):
        """Render and display item details."""
        self.current_item = item

        # Build detail text
        detail_text = ""

        # Title and category badge
        detail_text += f"\n{item['name']}\n"
        detail_text += "=" * len(item['name']) + "\n"
        detail_text += f"Category: {item['category'].upper()}\n\n"

        # Description
        if item.get("description"):
            detail_text += f"[DESCRIPTION]\n{item['description']}\n\n"

        # Details (extended info)
        if item.get("details"):
            detail_text += f"[DETAILS]\n{item['details']}\n\n"

        # Examples
        if item.get("examples"):
            detail_text += "[EXAMPLES]\n"
            for example in item['examples']:
                detail_text += f"  • {example}\n"
            detail_text += "\n"

        # Metadata
        if item.get("metadata"):
            detail_text += "[METADATA]\n"
            for key, value in item['metadata'].items():
                if isinstance(value, list):
                    detail_text += f"  {key}: {', '.join(str(v) for v in value)}\n"
                else:
                    detail_text += f"  {key}: {value}\n"
            detail_text += "\n"

        # Related items
        if item.get("related"):
            detail_text += "[RELATED ITEMS]\n"
            for related_id in item['related']:
                related_item = self.data_manager.get_item_by_id(related_id)
                if related_item:
                    detail_text += f"  • {related_item['name']}\n"
            detail_text += "\n"

        self.update(detail_text)

    def clear_display(self):
        """Clear the detail panel."""
        self.current_item = None
        self.update("[Select an item to view details]")


class CompendiumMode(Widget):
    """Music Knowledge Hub - hierarchical music reference with two-column layout."""

    BINDINGS = [
        Binding("space", "play_item", "Play", show=True),
        Binding("e", "expand_all", "Expand All", show=True),
    ]

    CSS = """
    CompendiumMode {
        width: 100%;
        height: 100%;
        layout: vertical;
    }

    #compendium-container {
        width: 100%;
        height: 1fr;
        layout: vertical;
        padding: 0;
    }

    #search-bar {
        width: 100%;
        height: 3;
        border: solid $accent;
        padding: 0 1;
    }

    #search-input {
        width: 100%;
        border: none;
        background: $surface;
        color: $text;
    }

    #content-split {
        width: 100%;
        height: 1fr;
        layout: horizontal;
    }

    #left-panel {
        width: 1fr;
        height: 1fr;
        border-right: solid $accent;
    }

    #chord-tree {
        width: 100%;
        height: 1fr;
    }

    #right-panel {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        layout: vertical;
        overflow: auto;
    }

    #detail-panel {
        width: 100%;
        height: 1fr;
        overflow: auto;
        color: $text;
    }
    """

    def __init__(self, chord_library: 'ChordLibrary', synth_engine: 'SynthEngine'):
        super().__init__()
        self.chord_library = chord_library
        self.synth_engine = synth_engine
        self.selected_notes: List[int] = []

        # Initialize data manager
        self.data_manager = CompendiumDataManager()
        self.tree_builder = CompendiumTreeBuilder(self.data_manager)

    def compose(self):
        """Compose the two-column layout."""
        with Vertical(id="compendium-container"):
            yield HeaderWidget(title="MUSIC KNOWLEDGE HUB", subtitle="Explore chords, scales, instruments, and genres")

            # Search bar (non-functional placeholder)
            # TODO: Implement search functionality:
            #  - Full-text search on name, description, examples
            #  - Filter results by category (chords, scales, instruments, genres)
            #  - Keyboard navigation with arrow keys
            #  - Instant preview on hover/selection
            #  - Search results displayed in left tree as filtered subset
            with Container(id="search-bar"):
                yield Input(
                    placeholder="Search music knowledge (coming soon)",
                    id="search-input"
                )

            # Two-column split
            with Horizontal(id="content-split"):
                # Left panel - Tree navigation
                with Container(id="left-panel"):
                    yield Tree("Music", id="chord-tree")

                # Right panel - Detail view
                with Container(id="right-panel"):
                    detail_panel = CompendiumDetailPanel(self.data_manager)
                    detail_panel.id = "detail-panel"
                    yield detail_panel

    def on_mount(self):
        """Initialize the tree and focus it."""
        self._build_tree()
        tree = self.query_one("#chord-tree", Tree)
        tree.focus()

        # Initialize detail panel with empty state
        detail_panel = self.query_one("#detail-panel", CompendiumDetailPanel)
        detail_panel.clear_display()

    def _build_tree(self):
        """Build the full hierarchical tree."""
        tree = self.query_one("#chord-tree", Tree)
        self.tree_builder.build_full_tree(tree)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        """Handle tree node selection."""
        node = event.node
        item_id = node.data

        if item_id:
            item = self.data_manager.get_item_by_id(item_id)
            if item:
                detail_panel = self.query_one("#detail-panel", CompendiumDetailPanel)
                detail_panel.render_item(item)

                # Auto-play chords on selection
                if item["category"] == "chords":
                    self.selected_notes = self._note_names_to_midi(
                        item.get("metadata", {}).get("notes", [])
                    )
                    self.action_play_item()

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        """Handle tree node selection (Enter key)."""
        # Expansion/collapse is handled by Textual automatically
        pass

    def _note_names_to_midi(self, note_names: List[str]) -> List[int]:
        """Convert note names to MIDI note numbers."""
        name_map = {
            'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
            'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8,
            'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11
        }

        midi_notes = []
        base_octave = 60  # C4
        last_val = -1
        octave_offset = 0

        for name in note_names:
            # Normalize note name
            name = name.replace("♭", "b").replace("♯", "#")
            val = name_map.get(name, 0)

            # Handle octave wrapping
            if val <= last_val:
                octave_offset += 12

            midi_notes.append(base_octave + val + octave_offset)
            last_val = val

        return midi_notes

    def action_play_item(self):
        """Play the currently selected chord using the synth engine."""
        if not self.selected_notes:
            return

        self.synth_engine.all_notes_off()

        # Staggered note onset for musical effect
        stagger = 0.02
        for i, note in enumerate(self.selected_notes):
            if i == 0:
                self.synth_engine.note_on(note, 80)
            else:
                import threading
                threading.Timer(i * stagger, self.synth_engine.note_on, args=[note, 80]).start()

        # Auto-release after duration
        duration = 0.8
        def release_all():
            for note in self.selected_notes:
                self.synth_engine.note_off(note)

        import threading
        threading.Timer(duration, release_all).start()

    def action_expand_all(self):
        """Expand all tree nodes."""
        tree = self.query_one("#chord-tree", Tree)
        tree.root.expand_all()
