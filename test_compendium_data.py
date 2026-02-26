#!/usr/bin/env python3
"""Test script to verify Compendium data files load and are valid."""
import json
from pathlib import Path

def test_json_files():
    """Verify all JSON files in data/compendium/ are valid."""
    compendium_dir = Path("data/compendium")
    json_files = list(compendium_dir.glob("*.json"))

    print(f"Found {len(json_files)} JSON files in {compendium_dir}")
    print()

    all_valid = True
    total_items = 0

    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)

            if not isinstance(data, dict) or 'items' not in data:
                print(f"❌ {json_file.name}: Invalid structure (missing 'items' key)")
                all_valid = False
                continue

            items = data['items']
            if not isinstance(items, list):
                print(f"❌ {json_file.name}: 'items' is not a list")
                all_valid = False
                continue

            item_count = len(items)
            total_items += item_count

            # Validate each item has required fields
            for idx, item in enumerate(items):
                # Categories have different structure (no category field)
                if json_file.name == 'categories.json':
                    required_fields = ['id', 'name']
                else:
                    required_fields = ['id', 'name', 'category', 'description']

                missing_fields = [f for f in required_fields if f not in item]
                if missing_fields:
                    print(f"❌ {json_file.name}[{idx}]: Missing fields: {missing_fields}")
                    all_valid = False

            print(f"✅ {json_file.name}: {item_count} items")

        except json.JSONDecodeError as e:
            print(f"❌ {json_file.name}: JSON parse error: {e}")
            all_valid = False
        except Exception as e:
            print(f"❌ {json_file.name}: {type(e).__name__}: {e}")
            all_valid = False

    print()
    print(f"Total items across all files: {total_items}")

    if all_valid:
        print("✅ All data files are valid!")
        return True
    else:
        print("❌ Some data files have errors")
        return False

def test_category_hierarchy():
    """Verify categories.json has valid hierarchy."""
    print("\n--- Testing Category Hierarchy ---")

    try:
        with open("data/compendium/categories.json", 'r') as f:
            categories_data = json.load(f)

        categories = {item['id']: item for item in categories_data['items']}
        print(f"✅ Found {len(categories)} categories")

        # Check music root exists
        if 'music' not in categories:
            print("❌ No 'music' root category found")
            return False

        music_cat = categories['music']
        children = music_cat.get('children', [])
        print(f"✅ Music category has {len(children)} children: {children}")

        # Verify all children exist
        for child_id in children:
            if child_id not in categories:
                print(f"❌ Child category '{child_id}' not found")
                return False

        print("✅ All category children exist")
        return True

    except Exception as e:
        print(f"❌ Error testing categories: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("COMPENDIUM DATA VALIDATION TEST")
    print("=" * 60)
    print()

    files_ok = test_json_files()
    hierarchy_ok = test_category_hierarchy()

    print()
    print("=" * 60)
    if files_ok and hierarchy_ok:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    exit(main())
