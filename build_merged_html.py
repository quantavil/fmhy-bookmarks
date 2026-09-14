#!/usr/bin/env python3
"""Rebuild merged bookmarks HTML after editing personal.md.

Keeps the FMHY part of bookmarks.html byte-identical and replaces only the
top-level Personal folder with the current personal.md content.

Usage:
    uv run build_merged_html.py
    uv run build_merged_html.py --personal personal.md --base bookmarks.html -o bookmarks-new.html
"""

from __future__ import annotations

import argparse
import html as ihtml
import re
from pathlib import Path

from convert_fmhy_bookmarks import load_personal_bookmarks

TOP_PAGE_RE = re.compile(r"^    <DT><H3>.*?</H3>$", re.M)


def render_personal_block(source: str, flat: bool = True) -> str:
    sections = load_personal_bookmarks(source=source)
    out = ["    <DT><H3>Personal</H3>", "    <DL><p>"]
    if flat:
        # No subfolders: all links directly under Personal, in file order.
        for links in sections.values():
            for link in links:
                out.append(
                    f'        <DT><A HREF="{ihtml.escape(link.url, quote=True)}">'
                    f"{ihtml.escape(link.title)}</A>"
                )
    else:
        for section, links in sections.items():
            out.append(f"        <DT><H3>{ihtml.escape(section)}</H3>")
            out.append("        <DL><p>")
            for link in links:
                out.append(
                    f'            <DT><A HREF="{ihtml.escape(link.url, quote=True)}">'
                    f"{ihtml.escape(link.title)}</A>"
                )
            out.append("        </DL><p>")
    out.append("    </DL><p>")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--personal", default="personal.md")
    parser.add_argument("--base", default="bookmarks.html")
    parser.add_argument("-o", "--output", default="bookmarks-new.html")
    parser.add_argument("--no-flat", action="store_true",
                        help="Keep personal.md sections as subfolders under Personal")
    args = parser.parse_args()

    base = Path(args.base).read_text(encoding="utf-8")
    tops = list(TOP_PAGE_RE.finditer(base))
    if not tops or "Personal" not in tops[0].group(0):
        raise SystemExit("error: base HTML has no leading Personal top-level folder")

    merged = base[: tops[0].start()] + render_personal_block(args.personal, flat=not args.no_flat) + base[tops[1].start():]
    Path(args.output).write_text(merged, encoding="utf-8")

    n_base = len(re.findall(r"<A HREF", base))
    n_new = len(re.findall(r"<A HREF", merged))
    print(f"Wrote {n_new} bookmarks ({n_new - n_base:+d} vs {args.base}) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
