import os
import re
from pathlib import Path

# Set this to the folder containing the images you want to rename.
# Works with any game or character collection.
character_dir = Path(r"/allpokemon")

for file in character_dir.iterdir():
    if file.is_file():
        # Get the filename without extension
        name = file.stem
        extension = file.suffix

        # Remove ONLY the leading digits and optional separator (_, -, or nothing)
        # This keeps digits that are part of the name like "porygon2"
        new_name = re.sub(r'^\d+[_-]?', '', name)

        # Skip if name hasn't changed (already processed or no number prefix)
        if new_name == name:
            print(f"Skipped: {file.name} (already processed)")
            continue

        # Check if target file already exists
        new_path = character_dir / f"{new_name}{extension}"
        if new_path.exists():
            print(f"WARNING: {new_name}{extension} already exists! Skipping {file.name}")
            continue

        # Rename the file
        file.rename(new_path)
        print(f"Renamed: {file.name} → {new_name}{extension}")

print("Done!")