"""Builds per-language i18n dictionaries for the Blueprint Finder.

Sources, in priority order (first hit wins):
  1. tm/<lang>.json      -- translation memory: anything already translated,
                            including previous engine output. Committed, so a
                            rebuild never re-sends a string that hasn't changed.
  2. ui_strings.json     -- hand-translated UI chrome + runtime patterns.
  3. CIG glossary        -- loc_key_map (exact, by GUID) then glossary
                            translate/keep buckets, from the game's own files.
  4. engine              -- Google Cloud Translation, for whatever is left.
                            Skipped entirely without --api-key, so the build
                            works offline and simply reports the gap.

Output per language:
    dist/<lang>/i18n.<lang>.js   -- dictionary + patterns, one <script> tag
    dist/<lang>/index.html       -- source index.html + two script tags
    dist/<lang>/<data>.json      -- symlink-free copy is avoided; the page
                                    loads the shared data file from the root

Usage:
    py -3 build_dicts.py --src <repo> --out dist [--lang de] [--api-key KEY]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _find_glossaries() -> Path:
    """Locate the glossaries folder.

    Two supported layouts: this script sitting inside `i18n/` in the tool repo
    (glossaries alongside it), or inside `wp-translate/blueprint-finder/` in the
    dev tree (glossaries one level up). Checking only the second silently
    produced a 76-entry dictionary instead of 788 -- a build that looks fine and
    passes the integrity gate while missing ~700 translations.
    """
    for candidate in (HERE / "glossaries", HERE.parent / "glossaries"):
        if (candidate / "supplement.json").exists():
            return candidate
    raise SystemExit(
        "ERROR: could not find a glossaries/ folder containing supplement.json.\n"
        f"  looked in: {HERE / 'glossaries'}\n"
        f"             {HERE.parent / 'glossaries'}\n"
        "Copy wp-translate/glossaries/ next to this script."
    )


GLOSSARIES = _find_glossaries()

LANGS = ["de", "fr", "ja", "zh"]
# Google's code for Simplified Chinese differs from our internal short code.
GOOGLE_CODE = {"de": "de", "fr": "fr", "ja": "ja", "zh": "zh-CN"}


def load_json(p: Path, default=None):
    if not p.exists():
        return default if default is not None else {}
    return json.loads(p.read_text(encoding="utf-8"))


def collect_data_strings(data: dict) -> set[str]:
    """Every user-visible string in the tool's data file.

    Deliberately excludes `blueprint`: it looks like text but is an internal
    asset id (BP_CRAFT_AMRS_LaserCannon_S1). Translating it would break the
    tool's own lookups, and it is 1,556 of the ~3,500 string values.
    """
    out: set[str] = set()
    for it in data.get("items", []):
        for f in ("name", "type", "subtype"):
            v = it.get(f)
            if isinstance(v, str) and v.strip():
                out.add(v.strip())
        for m in it.get("missions") or []:
            for f in ("title", "faction", "repStanding", "system"):
                v = m.get(f)
                if isinstance(v, str) and v.strip():
                    out.add(v.strip())
    return out


def google_translate(strings: list[str], target: str, api_key: str) -> dict[str, str]:
    """Google Cloud Translation v2. Batched; `format=text` so nothing is
    HTML-escaped on the way back."""
    out: dict[str, str] = {}
    BATCH = 100
    url = "https://translation.googleapis.com/language/translate/v2"
    for i in range(0, len(strings), BATCH):
        chunk = strings[i : i + BATCH]
        body = [("key", api_key), ("target", target), ("source", "en"),
                ("format", "text")]
        body += [("q", s) for s in chunk]
        data = urllib.parse.urlencode(body).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        got = payload["data"]["translations"]
        if len(got) != len(chunk):
            raise RuntimeError(
                f"engine returned {len(got)} translations for {len(chunk)} inputs"
            )
        for src, t in zip(chunk, got):
            out[src] = t["translatedText"]
        print(f"    engine: {min(i+BATCH, len(strings))}/{len(strings)}")
    return out


def build_language(lang: str, src: Path, out_root: Path, api_key: str | None) -> dict:
    ui = load_json(HERE / "ui_strings.json")
    tm_path = HERE / "tm" / f"{lang}.json"
    tm = load_json(tm_path)
    # Missing glossary data must be fatal, not a shrug. Falling back to {} here
    # yields a structurally valid build that quietly drops ~700 translations and
    # sails through the integrity gate.
    for required in (f"glossary_{lang}.json", "loc_key_map.json",
                     "supplement.json"):
        if not (GLOSSARIES / required).exists():
            raise SystemExit(
                f"ERROR: missing {GLOSSARIES / required}.\n"
                "Refusing to build a dictionary without it -- the result would "
                "look fine and silently lose most translations."
            )
    glossary = load_json(GLOSSARIES / f"glossary_{lang}.json")
    loc_map = load_json(GLOSSARIES / "loc_key_map.json")
    supplement = load_json(GLOSSARIES / "supplement.json")

    data = load_json(src / "blueprint_explorer_data.json")
    needed = collect_data_strings(data)

    never = set(supplement.get("never_translate", []))
    keep = set(glossary.get("keep", []))
    g_tr = glossary.get("translate", {})
    g_rev = glossary.get("review", {})

    dictionary: dict[str, str] = {}
    stats = {"tm": 0, "ui": 0, "loc_map": 0, "glossary": 0, "review": 0,
             "keep": 0, "pattern": 0, "engine": 0, "untranslated": 0}

    # --- UI chrome (always included; it is not part of `needed`) ------------
    for en, langs in ui.get("exact", {}).items():
        v = langs.get(lang)
        if v:
            dictionary[en] = v
            stats["ui"] += 1

    patterns = []
    for p in ui.get("patterns", []):
        v = p.get(lang)
        if v:
            patterns.append({"regex": p["regex"], "out": v})

    # --- data strings ------------------------------------------------------
    # Precedence, most authoritative first. The translation memory used to sit
    # at the TOP, which meant cached ENGINE output outranked CIG's own official
    # translations -- exactly backwards. It only escaped notice because the
    # first run sent the engine solely strings CIG did not cover. TM is a cache
    # of engine results, so it belongs at engine priority, not above the game's
    # own data.
    unresolved: list[str] = []
    for s in sorted(needed):
        if s in dictionary:
            continue
        if s in loc_map and lang in loc_map[s]:      # CIG official, GUID-joined
            dictionary[s] = loc_map[s][lang]
            stats["loc_map"] += 1
        elif s in g_tr:                              # CIG official, name-matched
            dictionary[s] = g_tr[s]
            stats["glossary"] += 1
        elif s in keep or s in never:                # deliberately English
            stats["keep"] += 1
        elif s in g_rev:                             # CIG, single-key support
            dictionary[s] = g_rev[s]
            stats["review"] += 1
        elif s in tm:                                # cached engine output
            dictionary[s] = tm[s]
            stats["tm"] += 1
        else:
            unresolved.append(s)

    # Anything a runtime pattern already handles must NEVER reach the engine.
    # Two reasons, both real:
    #  1. Patterns are deterministic and preserve proper nouns. Google would
    #     translate "Monde Core Daimyo" or "Strata Helmet Shire" as prose and
    #     mangle set/variant names it has no way to recognise.
    #  2. Engine output is written to the translation memory, which is consulted
    #     FIRST on every later build, and the runtime prefers dictionary entries
    #     over patterns. So a bad engine translation would permanently shadow
    #     the correct pattern -- baked in, not just wrong once.
    compiled = [re.compile(p["regex"]) for p in patterns]
    covered = [s for s in unresolved if any(rx.match(s) for rx in compiled)]
    unresolved = [s for s in unresolved if not any(rx.match(s) for rx in compiled)]
    stats["pattern"] = len(covered)

    if unresolved and api_key:
        print(f"  translating {len(unresolved)} remaining strings via engine...")
        got = google_translate(unresolved, GOOGLE_CODE[lang], api_key)
        dictionary.update(got)
        stats["engine"] = len(got)
        # Persist to the translation memory so this never costs anything again.
        tm.update(got)
        tm_path.parent.mkdir(parents=True, exist_ok=True)
        tm_path.write_text(
            json.dumps(dict(sorted(tm.items())), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    else:
        stats["untranslated"] = len(unresolved)

    # --- emit --------------------------------------------------------------
    out_dir = out_root / lang
    out_dir.mkdir(parents=True, exist_ok=True)

    js = (
        "/* generated by build_dicts.py -- do not edit by hand */\n"
        f"window.SC_I18N_LANG={json.dumps(lang)};\n"
        f"window.SC_I18N_DICT={json.dumps(dictionary, ensure_ascii=False)};\n"
        f"window.SC_I18N_PATTERNS={json.dumps(patterns, ensure_ascii=False)};\n"
    )
    (out_dir / f"i18n.{lang}.js").write_text(js, encoding="utf-8")
    # The runtime itself is identical for every language.
    (out_dir / "i18n.js").write_text(
        (HERE / "i18n.js").read_text(encoding="utf-8"), encoding="utf-8"
    )

    # index.html: the source file, untouched apart from two script tags and the
    # lang attribute. Nothing parses or rewrites the tool's own JavaScript.
    html = (src / "index.html").read_text(encoding="utf-8")
    if "i18n.js" in html:
        raise RuntimeError("source index.html already references i18n.js")
    inject = (
        f'<script src="i18n.{lang}.js"></script>\n'
        f'<script src="i18n.js"></script>\n'
    )
    if "</body>" not in html:
        raise RuntimeError("no </body> in source index.html; cannot inject")
    html = html.replace("</body>", inject + "</body>", 1)
    html = re.sub(r'<html\s+lang="[^"]*"', f'<html lang="{lang}"', html, count=1)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    # The data file is shared, not duplicated per language -- it is 2.3MB and
    # the dictionary translates it at render time.
    data_src = src / "blueprint_explorer_data.json"
    data_dst = out_dir / "blueprint_explorer_data.json"
    data_dst.write_bytes(data_src.read_bytes())

    return {"lang": lang, "stats": stats, "dict_size": len(dictionary),
            "patterns": len(patterns), "unresolved": unresolved}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True, help="source repo checkout")
    ap.add_argument("--out", type=Path, default=HERE / "dist")
    ap.add_argument("--lang", action="append", help="limit to these languages")
    ap.add_argument("--api-key", default=os.environ.get("GOOGLE_TRANSLATE_API_KEY"))
    args = ap.parse_args()

    langs = args.lang or LANGS
    reports = []
    for lang in langs:
        print(f"\n=== {lang} ===")
        r = build_language(lang, args.src, args.out, args.api_key)
        reports.append(r)
        s = r["stats"]
        print(f"  dictionary: {r['dict_size']:,} entries, {r['patterns']} patterns")
        print(f"  sources: ui={s['ui']} tm={s['tm']} loc_map={s['loc_map']} "
              f"glossary={s['glossary']} review={s['review']} pattern={s['pattern']} "
              f"keep(English)={s['keep']} engine={s['engine']}")
        if s["untranslated"]:
            print(f"  !! {s['untranslated']:,} strings left in English "
                  f"(no --api-key supplied)")

    (args.out / "build_report.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
