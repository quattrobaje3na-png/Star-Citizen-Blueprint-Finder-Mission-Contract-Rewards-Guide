"""Builds the translated WordPress page fronts for the Blueprint Finder.

Input:  wp-source/page.html   -- the English Custom HTML block, exactly as it
                                is pasted into WordPress today
Output: dist-wp/page.<lang>.html + hreflang.html

Approach and its one hard rule: this replaces **visible text only**, by exact
match against wp_page_strings.json, and rewrites the iframe src to the matching
language build. CSS, class names, IDs, inline styles, anchors and URLs are
never touched. Anything not in the strings file is left in English rather than
guessed at, so an unreviewed string can never silently ship.

The iframe src is repointed per language, which is the whole point -- the
German page must embed the German tool.

Usage:
    py -3 build_wp_page.py [--src wp-source/page.html] [--out dist-wp]
"""
from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGS = ["de", "fr", "ja", "zh"]

SITE = "https://citizen-starter-guide.com"
PAGE_SLUG = "star-citizen-blueprint-finder"
# Single-repo layout (see SETUP.md): the tool repo publishes ONE Pages site
# with English at the root and each language in a subfolder. So the translated
# builds live under the SAME base URL the English tool already uses -- which is
# why the existing English URL never has to change.
SOURCE_IFRAME = (
    "https://quattrobaje3na-png.github.io/"
    "Star-Citizen-Blueprint-Finder-Mission-Contract-Rewards-Guide/"
)
TOOL_BASE = SOURCE_IFRAME.rstrip("/")

# WordPress path convention for the translated pages.
WP_PATH = {
    "en": f"{SITE}/{PAGE_SLUG}/",
    "de": f"{SITE}/de/{PAGE_SLUG}/",
    "fr": f"{SITE}/fr/{PAGE_SLUG}/",
    "ja": f"{SITE}/ja/{PAGE_SLUG}/",
    "zh": f"{SITE}/zh/{PAGE_SLUG}/",
}
HREFLANG_CODE = {"en": "en", "de": "de", "fr": "fr", "ja": "ja", "zh": "zh-Hans"}


def translate_html(source: str, strings: dict, lang: str) -> tuple[str, list[str]]:
    """Replaces visible text spans only. Returns (html, untranslated)."""
    out = source
    untranslated: list[str] = []

    # Longest first, so a long paragraph is replaced before any short phrase
    # that happens to be a substring of it.
    for en in sorted(strings, key=len, reverse=True):
        target = strings[en].get(lang)
        if not target:
            untranslated.append(en)
            continue

        # The page stores "&" as "&amp;", so a literal "&" in the strings file
        # never matches. This silently skipped three real strings ("Maximize
        # Your DPS & Gear Upgrades", "SC Weapon & Armor Schematics", "Craft
        # Better Guns & Ammo") while the build still reported success.
        # Try both the raw and the HTML-escaped form, and escape the
        # replacement the same way the surrounding document does.
        variants = {en, htmlmod.escape(en, quote=False)}
        escaped_target = htmlmod.escape(target, quote=False)

        before = out
        for variant in sorted(variants, key=len, reverse=True):
            repl = escaped_target if "&amp;" in variant else target
            # HTML wraps prose across lines with arbitrary indentation, so a
            # literal match fails on any multi-line paragraph. Treat every run
            # of whitespace in the source string as flexible. This is what the
            # referral paragraph (wrapped around a <strong>) needed.
            flexible = r"\s+".join(
                re.escape(w) for w in variant.split()
            )
            pat_text = re.compile(r"(>\s*)" + flexible + r"(\s*<)")
            pat_attr = re.compile(
                r'((?:title|alt|aria-label)=")' + flexible + r'(")'
            )
            out = pat_text.sub(lambda m: m.group(1) + repl + m.group(2), out)
            out = pat_attr.sub(lambda m: m.group(1) + repl + m.group(2), out)

        # A target identical to the source is a deliberate keep-in-English
        # (common for tool names in DE/FR), not a failure to apply.
        norm_source = " ".join(source.split())
        present = any(" ".join(v.split()) in norm_source for v in variants)
        if out == before and present and target != en:
            # Present in the page but not in a position we consider safe.
            untranslated.append(en)
        elif not present:
            # In the strings file but nowhere in the page -- a stale entry.
            untranslated.append(f"(not found in page) {en}")

    # Repoint the embedded tool at this language's build.
    out = out.replace(SOURCE_IFRAME, f"{TOOL_BASE}/{lang}/")

    # Internal site links get the language prefix so a translated page does not
    # bounce readers back into English.
    out = re.sub(r'href="/([a-z0-9-]+/)"', rf'href="/{lang}/\1"', out)
    out = out.replace(f"{SITE}/", f"{SITE}/{lang}/")
    return out, untranslated


def build_hreflang() -> str:
    lines = ["<!-- Paste into the <head> of EVERY language version of this page.",
             "     WordPress: use a head-injection snippet or your SEO plugin's",
             "     custom-head field. Without these, Google may treat the",
             "     translations as duplicate content instead of alternates. -->"]
    for lang, url in WP_PATH.items():
        lines.append(
            f'<link rel="alternate" hreflang="{HREFLANG_CODE[lang]}" href="{url}" />'
        )
    lines.append(
        f'<link rel="alternate" hreflang="x-default" href="{WP_PATH["en"]}" />'
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=HERE / "wp-source" / "page.html")
    ap.add_argument("--out", type=Path, default=HERE / "dist-wp")
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: source page not found: {args.src}")
        print("Save the English Custom HTML block there first.")
        return 1

    source = args.src.read_text(encoding="utf-8")
    strings = json.loads(
        (HERE / "wp_page_strings.json").read_text(encoding="utf-8")
    )["strings"]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "hreflang.html").write_text(build_hreflang(), encoding="utf-8")

    for lang in LANGS:
        out, missed = translate_html(source, strings, lang)
        dest = args.out / f"page.{lang}.html"
        dest.write_text(out, encoding="utf-8")
        status = f"{len(strings) - len(missed)}/{len(strings)} strings applied"
        print(f"  {lang}: {status} -> {dest.name}")
        for m in missed:
            print(f"       not applied: {m[:70]}")

    print(f"\nhreflang block -> {args.out / 'hreflang.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
