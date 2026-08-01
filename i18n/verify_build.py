"""Correctness gate. Runs after build_dicts.py and BEFORE anything publishes.

This is not an approval step -- it does not ask whether a translation reads
well. It fails the build only when the output is structurally broken or
provably contaminated, which is the class of problem that must never reach a
live page unattended.

Checks, each of which corresponds to a real defect already hit in this project:
  1. The tool's own markup survived intact (script/style/tag counts unchanged,
     data file byte-identical). Guards against the classic failure where a
     translator reflows markup and the page renders as raw text.
  2. No CIG "TRANSLATION NOT FOUND FOR LOCID" placeholders leaked through.
     1,692 of these got into the first glossary build.
  3. No cross-script contamination -- e.g. Hangul inside a German/Japanese
     string. A stray Korean character was found in a hand-authored JA string.
  4. Every runtime pattern compiles, and its $N placeholders exist as capture
     groups in its own regex.
  5. The dictionary never maps a string to itself (silent no-op entries) and
     never contains an untranslated-looking value for CJK targets.

Exit code 1 on any failure, so CI stops.

Usage:
    py -3 verify_build.py --src <repo> --out dist [--lang de ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGS = ["de", "fr", "ja", "zh"]

PLACEHOLDER = re.compile(r"TRANSLATION NOT FOUND FOR LOCID", re.IGNORECASE)
HANGUL = re.compile(r"[가-힯ᄀ-ᇿ]")
CJK = re.compile(r"[぀-ヿ一-鿿]")

# Script ranges each target language is allowed to contain, beyond Latin.
ALLOWED_EXTRA = {
    "de": HANGUL,   # German must contain no Hangul
    "fr": HANGUL,
    "ja": HANGUL,   # Japanese uses kana/kanji, never Hangul
    "zh": HANGUL,
}


class Failures:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, msg: str) -> None:
        self.items.append(msg)

    def ok(self) -> bool:
        return not self.items


def check_markup(src: Path, out_dir: Path, lang: str, f: Failures) -> None:
    src_html = (src / "index.html").read_text(encoding="utf-8")
    out_html = (out_dir / "index.html").read_text(encoding="utf-8")

    for tag in ("script", "style", "div", "iframe"):
        a = len(re.findall(rf"<{tag}\b", src_html, re.IGNORECASE))
        b = len(re.findall(rf"<{tag}\b", out_html, re.IGNORECASE))
        # The build deliberately injects exactly two <script> tags.
        expected = a + 2 if tag == "script" else a
        if b != expected:
            f.add(f"[{lang}] <{tag}> count changed: source={a} output={b} "
                  f"(expected {expected})")

    # The tool's own JavaScript must be byte-identical: nothing may rewrite it.
    def body_of(html: str) -> str:
        """The tool's own INLINE script block.

        Must anchor on the bare `<script>` and the FIRST `</script>` after it.
        Using rfind() picks up the build's own injected `<script src=...>` tags
        instead, which made this check fail on a perfectly good build.
        """
        i = html.find("<script>")
        if i == -1:
            return ""
        j = html.find("</script>", i)
        return html[i:j] if j != -1 else ""

    if body_of(src_html) != body_of(out_html):
        f.add(f"[{lang}] the tool's inline JavaScript was modified -- it must "
              f"never be rewritten")

    src_data = src / "blueprint_explorer_data.json"
    out_data = out_dir / "blueprint_explorer_data.json"
    if not out_data.exists():
        f.add(f"[{lang}] data file missing from output")
    elif src_data.read_bytes() != out_data.read_bytes():
        f.add(f"[{lang}] data file was modified; it must be copied verbatim")


def check_dictionary(out_dir: Path, lang: str, f: Failures) -> None:
    js_path = out_dir / f"i18n.{lang}.js"
    if not js_path.exists():
        f.add(f"[{lang}] i18n.{lang}.js missing")
        return
    js = js_path.read_text(encoding="utf-8")

    def grab(var: str):
        m = re.search(rf"window\.{var}=(.*?);\n", js, re.DOTALL)
        if not m:
            f.add(f"[{lang}] could not parse {var}")
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            f.add(f"[{lang}] {var} is not valid JSON: {e}")
            return None

    dictionary = grab("SC_I18N_DICT")
    patterns = grab("SC_I18N_PATTERNS")
    if dictionary is None or patterns is None:
        return

    bad_placeholder = [k for k, v in dictionary.items() if PLACEHOLDER.search(v)]
    if bad_placeholder:
        f.add(f"[{lang}] {len(bad_placeholder)} entries contain CIG "
              f"'TRANSLATION NOT FOUND' placeholders, e.g. "
              f"{bad_placeholder[0]!r}")

    forbidden = ALLOWED_EXTRA.get(lang)
    if forbidden:
        bad_script = [(k, v) for k, v in dictionary.items() if forbidden.search(v)]
        if bad_script:
            f.add(f"[{lang}] {len(bad_script)} entries contain characters from "
                  f"the wrong script, e.g. {bad_script[0][1]!r}")

    noop = [k for k, v in dictionary.items() if k == v]
    if noop:
        # Not fatal on its own for de/fr (many proper nouns legitimately match),
        # but for CJK targets an identical value means nothing was translated.
        if lang in ("ja", "zh") and len(noop) > 0:
            f.add(f"[{lang}] {len(noop)} entries map a string to itself, e.g. "
                  f"{noop[0]!r} -- for a CJK target this is a silent no-op")

    for i, p in enumerate(patterns):
        try:
            rx = re.compile(p["regex"])
        except re.error as e:
            f.add(f"[{lang}] pattern {i} does not compile: {e}")
            continue
        used = {int(d) for d in re.findall(r"\$(\d)", p.get("out", ""))}
        if used and max(used) > rx.groups:
            f.add(f"[{lang}] pattern {i} references ${max(used)} but its regex "
                  f"has only {rx.groups} capture groups")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--lang", action="append")
    args = ap.parse_args()

    f = Failures()
    for lang in (args.lang or LANGS):
        out_dir = args.out / lang
        if not out_dir.exists():
            f.add(f"[{lang}] output directory missing: {out_dir}")
            continue
        check_markup(args.src, out_dir, lang, f)
        check_dictionary(out_dir, lang, f)

    if f.ok():
        print("integrity gate: PASS")
        return 0
    print("integrity gate: FAIL")
    for item in f.items:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
