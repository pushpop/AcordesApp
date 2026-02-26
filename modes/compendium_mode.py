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
from textual.message import Message
from components.header_widget import HeaderWidget

if TYPE_CHECKING:
    from music.chord_library import ChordLibrary
    from music.synth_engine import SynthEngine


class CompendiumTree(Tree):
    """Custom Tree for Compendium mode - simple subclass without custom bindings."""

    def __init__(self, label: str, compendium_mode: Optional['CompendiumMode'] = None, **kwargs):
        super().__init__(label, **kwargs)
        self.compendium_mode = compendium_mode


class CompendiumDataManager:
    """Load and cache music knowledge data from JSON files."""

    def __init__(self):
        """Initialize data manager and load all data."""
        self.data_dir = Path(__file__).parent.parent / "data" / "compendium"
        self.categories: Dict[str, Any] = {}
        self.chords: Dict[str, Any] = {}
        self.scales: Dict[str, Any] = {}
        self.modes: Dict[str, Any] = {}
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
        for category_name in ["chords", "scales", "modes", "instruments", "genres"]:
            data = self._load_json_file(f"{category_name}.json")
            items = data.get("items", [])

            # Store by ID for quick lookup
            category_dict = {item["id"]: item for item in items}

            if category_name == "chords":
                self.chords = category_dict
            elif category_name == "scales":
                self.scales = category_dict
            elif category_name == "modes":
                self.modes = category_dict
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
        elif category_name == "modes":
            return self.modes
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

    def search_items(self, query: str, categories: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Search across all items or specific categories.

        Args:
            query: Search string (will be lowercased for matching)
            categories: Optional list of category names to limit search.
                       If None, searches all categories

        Returns:
            Dict mapping item_id → item with full data
        """
        query_lower = query.lower()
        results = {}

        # Determine which categories to search
        search_cats = categories or ["chords", "scales", "modes", "instruments", "genres"]

        for category in search_cats:
            items = self.get_category_items(category)

            for item_id, item in items.items():
                # Build searchable text from all relevant fields
                searchable_fields = [
                    item.get("name", ""),
                    item.get("description", ""),
                    item.get("details", ""),
                    " ".join(item.get("examples", [])),
                    # Also search metadata values
                    " ".join(str(v) for v in item.get("metadata", {}).values() if isinstance(v, (str, int)))
                ]
                searchable_text = " ".join(searchable_fields).lower()

                # Include if query matches any searchable field
                if query_lower in searchable_text:
                    results[item_id] = item

        return results


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

        # Get the root category (music)
        root_cat = categories.get("music")
        if not root_cat:
            return

        # Iterate through child categories listed in root
        for child_id in root_cat.get("children", []):
            child_cat = categories.get(child_id)
            if not child_cat:
                continue

            # Add category node with icon and name
            cat_icon = child_cat.get("icon", "🎵")
            cat_node = tree.root.add(f"{cat_icon} {child_cat['name']}")
            cat_node.data = child_id

            # Add items under this category
            items = self.data_manager.get_category_items(child_id)

            # Special handling for chords: group by root note (key)
            if child_id == "chords":
                self._build_chords_tree(cat_node, items)
            # Special handling for instruments: group by family type
            elif child_id == "instruments":
                self._build_instruments_tree(cat_node, items)
            else:
                # For other categories, just list items directly
                sorted_items = sorted(items.values(), key=lambda x: x["name"])
                for item in sorted_items:
                    item_node = cat_node.add(item["name"])
                    item_node.data = item["id"]

    def _build_chords_tree(self, cat_node, items: Dict[str, Any]) -> None:
        """Build chords sub-tree grouped by root note (key)."""
        # Group chords by their root note
        chords_by_key: Dict[str, List[Dict[str, Any]]] = {}

        for item in items.values():
            # Extract root note from chord name (first part before space)
            # e.g., "C Major" -> "C", "F# Minor" -> "F#"
            root_note = item["name"].split()[0]
            if root_note not in chords_by_key:
                chords_by_key[root_note] = []
            chords_by_key[root_note].append(item)

        # Define the key order (chromatic scale)
        key_order = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

        # Add key nodes in order, then chords under each key
        for key in key_order:
            if key in chords_by_key:
                # Add key node
                key_node = cat_node.add(f"  {key}")
                key_node.data = None  # Key nodes don't have data IDs

                # Sort chords within this key by name (chord type)
                sorted_chords = sorted(chords_by_key[key], key=lambda x: x["name"])

                # Add chord nodes under key
                for chord in sorted_chords:
                    chord_node = key_node.add(chord["name"])
                    chord_node.data = chord["id"]

    def _build_instruments_tree(self, cat_node, items: Dict[str, Any]) -> None:
        """Build instruments sub-tree grouped by family type."""
        # Separate instruments by their family type and category items
        families: Dict[str, List[Dict[str, Any]]] = {}
        family_items: Dict[str, Dict[str, Any]] = {}  # Store family category items

        for item in items.values():
            # Check if this is a family category item
            metadata = item.get("metadata", {})
            if metadata.get("family_type") == "category":
                # This is a family grouping item (e.g., "String Instruments")
                family_id = item["id"]
                family_items[family_id] = item
            else:
                # This is an actual instrument
                family = metadata.get("family", "other")
                if family not in families:
                    families[family] = []
                families[family].append(item)

        # Define family order
        family_order = ["strings", "brass", "woodwind", "percussion", "keyboard", "voice"]

        # Add family nodes and instruments under each
        for family in family_order:
            if family in families:
                # Find the family item for display
                family_id = f"{family}_family"
                if family_id in family_items:
                    family_name = family_items[family_id]["name"]
                else:
                    family_name = family.capitalize() + " Instruments"

                # Add family node
                family_node = cat_node.add(family_name)
                family_node.data = None  # Family nodes don't have data IDs

                # Sort instruments within this family by name
                sorted_instruments = sorted(families[family], key=lambda x: x["name"])

                # Add instrument nodes under family
                for instrument in sorted_instruments:
                    instr_node = family_node.add(instrument["name"])
                    instr_node.data = instrument["id"]


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

    def render_category(self, category: Dict[str, Any]):
        """Render and display category details."""
        self.current_item = category

        # Build detail text
        detail_text = ""

        # Title with icon
        icon = category.get("icon", "🎵")
        category_name = category.get("name", "Category")
        detail_text += f"\n{icon} {category_name}\n"
        detail_text += "=" * (len(category_name) + 2) + "\n\n"

        # Description
        if category.get("description"):
            detail_text += f"[DESCRIPTION]\n{category['description']}\n\n"

        # List child items if this is the root category
        if category.get("children"):
            detail_text += "[SUBCATEGORIES]\n"
            categories = self.data_manager.get_categories()
            for child_id in category["children"]:
                child_cat = categories.get(child_id)
                if child_cat:
                    detail_text += f"  • {child_cat.get('name', child_id)}\n"
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
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("left", "previous_category", "Prev Category", show=False),
        Binding("right", "next_category", "Next Category", show=False),
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

    #search-input {
        width: 100%;
        height: 3;
        border: solid $accent;
        background: $surface;
        color: $text;
        padding: 0 1;
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
        height: 100%;
        border: none;
    }

    #right-panel {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
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

        # Store category list for navigation
        root_cat = self.data_manager.get_categories().get("music")
        self.categories_list = root_cat.get("children", []) if root_cat else []

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
            yield Input(
                placeholder="Search music knowledge (coming soon)",
                id="search-input"
            )

            # Two-column split with Container wrappers for proper layout
            with Horizontal(id="content-split"):
                # Left panel - Tree navigation (using custom CompendiumTree)
                with Container(id="left-panel"):
                    yield CompendiumTree("Music", compendium_mode=self, id="chord-tree")

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

    def on_key(self, event) -> None:
        """Intercept key presses to handle left/right arrows when tree is focused."""
        tree = self.query_one("#chord-tree", Tree)

        # Only handle left/right if tree is focused
        if self.app.focused == tree:
            if event.key == "left":
                event.prevent_default()
                self.action_previous_category()
                return
            elif event.key == "right":
                event.prevent_default()
                self.action_next_category()
                return

    def _build_tree(self):
        """Build the full hierarchical tree."""
        tree = self.query_one("#chord-tree", Tree)
        self.tree_builder.build_full_tree(tree)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        """Handle tree node selection."""
        node = event.node
        item_id = node.data

        if item_id:
            # Check if this is a category node
            categories = self.data_manager.get_categories()
            if item_id in categories:
                # Render category details
                category = categories[item_id]
                detail_panel = self.query_one("#detail-panel", CompendiumDetailPanel)
                detail_panel.render_category(category)
            else:
                # Render item details
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

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes - filter tree in real-time."""
        search_text = event.input.value.strip()

        if not search_text:
            # Empty search - rebuild full hierarchical tree
            self._build_tree()
            return

        # Perform search and show results grouped by category
        results = self.data_manager.search_items(search_text)
        self._build_search_results_tree(results)

    def _build_search_results_tree(self, results: Dict[str, Dict[str, Any]]) -> None:
        """Build tree showing search results grouped by category."""
        tree = self.query_one("#chord-tree", Tree)
        tree.clear()
        tree.root.expand()

        if not results:
            # No results - show empty state
            tree.root.add("No results found")
            return

        # Group results by category for organized display
        results_by_category: Dict[str, List[Dict[str, Any]]] = {}

        for item_id, item in results.items():
            category = item.get("category", "unknown")
            if category not in results_by_category:
                results_by_category[category] = []
            results_by_category[category].append(item)

        # Add category nodes in standard order
        category_order = ["chords", "scales", "modes", "instruments", "genres"]

        for category in category_order:
            if category not in results_by_category:
                continue

            # Get category display info
            categories_data = self.data_manager.get_categories()
            cat_info = categories_data.get(category, {})
            cat_name = cat_info.get("name", category.capitalize())
            cat_icon = cat_info.get("icon", "🎵")

            # Create category node with result count
            cat_node = tree.root.add(f"{cat_icon} {cat_name} ({len(results_by_category[category])})")
            cat_node.data = category  # Store category ID for detail panel lookup

            # Add items under category, sorted by name
            sorted_items = sorted(results_by_category[category], key=lambda x: x["name"])
            for item in sorted_items:
                item_node = cat_node.add(item["name"])
                item_node.data = item["id"]  # Store ID for detail panel lookup

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

    def action_focus_next(self):
        """Move focus to the next panel (search → tree → search cycle)."""
        try:
            focused = self.app.focused
            search_input = self.query_one("#search-input", Input)
            tree = self.query_one("#chord-tree", Tree)

            if focused == search_input:
                # Move from search to tree
                tree.focus()
            else:
                # Move from tree back to search
                search_input.focus()
        except Exception:
            pass

    def action_focus_previous(self):
        """Move focus to the previous panel (search ← tree cycle)."""
        try:
            focused = self.app.focused
            search_input = self.query_one("#search-input", Input)
            tree = self.query_one("#chord-tree", Tree)

            if focused == search_input:
                # Move from search backwards to tree
                tree.focus()
            else:
                # Move from tree to search
                search_input.focus()
        except Exception:
            pass

    def action_previous_category(self):
        """Left arrow: Jump to parent category and collapse it, or go to previous category."""
        try:
            tree = self.query_one("#chord-tree", Tree)
            cursor_node = tree.cursor_node

            if not cursor_node:
                return

            # Determine if cursor is on item or category
            is_on_category = cursor_node.parent == tree.root
            current_cat_id = None
            current_cat_node = None

            # Find which category the cursor is in
            if is_on_category:
                # Already on a category
                current_cat_id = cursor_node.data
                current_cat_node = cursor_node
            else:
                # On an item, find parent category
                node = cursor_node
                while node and node.parent:
                    parent = node.parent
                    if parent == tree.root:
                        current_cat_id = node.data
                        current_cat_node = node
                        break
                    node = parent

            if not current_cat_id or current_cat_id not in self.categories_list:
                return

            if not is_on_category:
                # On an item: jump to parent category and collapse it
                tree.cursor_node = current_cat_node
                if current_cat_node.is_expanded:
                    tree.toggle_node(current_cat_node)
            else:
                # On a category: go to previous category
                current_idx = self.categories_list.index(current_cat_id)
                if current_idx > 0:
                    # Collapse current category
                    if current_cat_node.is_expanded:
                        tree.toggle_node(current_cat_node)
                    # Jump to previous category
                    prev_cat_id = self.categories_list[current_idx - 1]
                    self._focus_category(tree, prev_cat_id)

        except Exception:
            pass

    def action_next_category(self):
        """Right arrow: Expand category if on one, or jump to next category."""
        try:
            tree = self.query_one("#chord-tree", Tree)
            cursor_node = tree.cursor_node

            if not cursor_node:
                return

            # Determine if cursor is on item or category
            is_on_category = cursor_node.parent == tree.root

            if is_on_category:
                # On a category: expand it (if it has children)
                if cursor_node.children and not cursor_node.is_expanded:
                    tree.toggle_node(cursor_node)
            else:
                # On an item: jump to next category
                current_cat_id = None
                node = cursor_node
                while node and node.parent:
                    parent = node.parent
                    if parent == tree.root:
                        current_cat_id = node.data
                        break
                    node = parent

                if current_cat_id and current_cat_id in self.categories_list:
                    current_idx = self.categories_list.index(current_cat_id)
                    if current_idx < len(self.categories_list) - 1:
                        # Go to next category
                        next_cat_id = self.categories_list[current_idx + 1]
                        self._focus_category(tree, next_cat_id)

        except Exception:
            pass

    def _focus_category(self, tree: Tree, category_id: str):
        """Focus on a specific category and its first item."""
        try:
            # Find the category node
            for node in tree.root.children:
                if node.data == category_id:
                    # Expand the category if not already expanded
                    if not node.is_expanded:
                        tree.toggle_node(node)
                    # Focus on the first child (first item in category)
                    if node.children:
                        tree.cursor_node = node.children[0]
                    else:
                        tree.cursor_node = node
                    return
        except Exception:
            pass
