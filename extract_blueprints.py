import os
import re

# Drop this file directly into your Star Citizen "logbackups" folder — the
# one inside your LIVE folder (e.g. ...\StarCitizen\LIVE\logbackups). It
# figures out where it's running from, so there's nothing to edit and no
# install path to hardcode.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_DIR = os.path.dirname(SCRIPT_DIR)  # one folder up = the LIVE folder with game.log

BLUEPRINT_PATTERN = re.compile(r"Received Blueprint:\s*(.*?):")

# Fold curly/smart quotes to plain ASCII quotes so a name like
#   Arclight "Midnight" Pistol
# always comes out the same regardless of which quote characters the game
# log happens to use. Mirrored by normalizeBpName() on the site's side —
# keep the two in sync if this ever changes.
_SMART_SINGLE_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
})
_SMART_DOUBLE_QUOTES = str.maketrans({
    "“": '"', "”": '"', "„": '"', "″": '"',
})


def normalize_name(name):
    """Standardize a raw blueprint name: fold smart quotes to straight ASCII
    quotes and collapse/trim whitespace. Display casing is left alone — the
    site matches names case-insensitively — so blueprints.txt stays readable."""
    name = name.translate(_SMART_SINGLE_QUOTES).translate(_SMART_DOUBLE_QUOTES)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def find_log_files(script_dir, live_dir):
    """Find rotated logs sitting next to this script, plus the live game.log
    one folder up, in the LIVE directory."""
    paths = []

    for f in os.listdir(script_dir):
        if f.endswith(".log"):
            paths.append(os.path.join(script_dir, f))

    game_log = os.path.join(live_dir, "game.log")
    if os.path.isfile(game_log):
        paths.append(game_log)

    return paths


def extract_blueprints(paths, output_file):
    results = set()

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                results |= {
                    normalize_name(m.group(1))
                    for line in f
                    if (m := BLUEPRINT_PATTERN.search(line))
                }
        except Exception as e:
            print(f"Error reading {path}: {e}")

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(sorted(results)))
        print(f"Extracted {len(results)} unique entries to {output_file}")
    except Exception as e:
        print(f"Error writing output file: {e}")


def main():
    print(f"Looking for Star Citizen logs in: {SCRIPT_DIR}")
    print(f"(and for game.log in: {LIVE_DIR})")
    print()

    paths = find_log_files(SCRIPT_DIR, LIVE_DIR)

    if not paths:
        print("Couldn't find any .log files here, or game.log one folder up.")
        print()
        print("Move this file into your Star Citizen logbackups folder — the")
        print(r"one inside LIVE (e.g. ...\StarCitizen\LIVE\logbackups) —")
        print("then double-click it again.")
        return

    print(f"Found {len(paths)} log file(s) to scan:")
    for p in paths:
        print(f"  - {p}")
    print()

    output_file = os.path.join(SCRIPT_DIR, "blueprints.txt")
    extract_blueprints(paths, output_file)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Keep the console window open when double-clicked so the results
        # (or any error) are actually readable instead of flashing shut.
        input("\nPress Enter to close this window...")
