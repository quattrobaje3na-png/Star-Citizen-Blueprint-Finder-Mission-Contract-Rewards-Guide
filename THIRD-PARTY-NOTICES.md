# Third-party notices

This repository redistributes work from the projects below. Their licence terms
are reproduced in full as required.

---

## Star Citizen Localization (community project)

**Source:** https://github.com/Dymerz/StarCitizen-Localization
**Copyright:** © 2025 Corentin Urbain "Dymerz"
**Licence:** MIT

### What is used, and where

`i18n/glossaries/community_de.json` and `i18n/glossaries/community_fr.json`
contain English → German and English → French string pairs derived from that
project's `global.ini` files (roughly 48,900 and 59,300 pairs respectively).

Those pairs are used to translate **mission titles only** — see
`COMMUNITY_FIELDS` in `i18n/build_dicts.py`. Item names deliberately do not use
them, because the project's item strings lag Cloud Imperium's own English and
would show players the wrong item or the wrong ammo capacity.

The resulting translations are shipped in `i18n/dist/de/i18n.de.js` and
`i18n/dist/fr/i18n.fr.js`, each of which carries this notice in its own header,
and are credited visibly on the German and French pages of
citizen-starter-guide.com.

Japanese and Chinese use **no** work from this project — it does not cover those
languages — and are therefore not credited to it.

### Licence text

```
MIT License

Copyright (c) 2025 Corentin Urbain "Dymerz"

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Star Citizen game data

**Source:** Cloud Imperium Games — `Data.p4k` → `Data/Localization/<lang>/global.ini`

`i18n/glossaries/glossary_*.json` and `i18n/glossaries/loc_key_map.json` are
derived from the localization files shipped with the game client. They contain
official in-game names for items, ships, components and locations, used so that
this tool matches the wording players actually see.

Star Citizen®, Roberts Space Industries® and Cloud Imperium® are registered
trademarks of Cloud Imperium Rights LLC. This is an unofficial fan project and
is not affiliated with, endorsed or sponsored by Cloud Imperium Games.
