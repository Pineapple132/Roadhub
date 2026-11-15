"""Builds roadhub/i18n_data.py from the translation tables (prefix of the German text → languages).

Usage: python tools/build_i18n.py <folder with tables>
Each table is a .py file with a list E of tuples (beginning of the German text, en, ru, tr, pl).
The beginning of the text is resolved against the texts in the program so the full text does not have to be maintained twice."""

from __future__ import annotations

import ast
import glob
import os
import pprint
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = ("theme.py", "mapdata.py", "__init__.py", "sii.py", "saves.py", "i18n.py", "i18n_data.py")


def program_strings() -> set[str]:
    found: set[str] = set()
    for path in sorted(glob.glob(os.path.join(ROOT, "roadhub", "*.py"))):
        if path.endswith(SKIP):
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                found.add("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in inner:
                found.add(node.value)
    return found


def main(folder: str) -> int:
    known = program_strings()
    catalog: dict[str, tuple] = {}
    problems = 0
    for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
        ns: dict = {}
        exec(open(path, encoding="utf-8").read(), ns)
        for row in ns["E"]:
            prefix, *texts = row
            if len(texts) != 4:
                print(f"{os.path.basename(path)}: falsche Spaltenzahl bei {prefix[:40]!r}")
                problems += 1
                continue
            if prefix in known:
                full = prefix
            else:
                cands = [k for k in known if k.startswith(prefix)]
                if len(cands) != 1:
                    print(f"{os.path.basename(path)}: {len(cands)} Treffer für {prefix[:60]!r}")
                    problems += 1
                    continue
                full = cands[0]
            n = full.count("{}")
            for lang, text in zip(("en", "ru", "tr", "pl"), texts):
                numbered = re.findall(r"\{(\d+)\}", text)
                plain = text.count("{}")
                if (plain != n) and not (numbered and plain == 0 and len(set(numbered)) == n):
                    print(f"{os.path.basename(path)}: Platzhalter {lang} bei {full[:50]!r}: {plain}/{n}")
                    problems += 1
            catalog[full] = tuple(texts)
    out = os.path.join(ROOT, "roadhub", "i18n_data.py")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write('"""Übersetzungskatalog (erzeugt von tools/build_i18n.py). Spalten: en, ru, tr, pl."""\n\n')
        fh.write("CATALOG = ")
        fh.write(pprint.pformat(catalog, width=110, sort_dicts=False))
        fh.write("\n")
    print(f"{len(catalog)} Einträge, {problems} Probleme")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
