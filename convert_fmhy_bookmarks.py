#!/usr/bin/env python3
"""Convert FMHY Markdown into a browser-importable bookmarks HTML file."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import re
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import httpx


DEFAULT_SOURCE = "https://fmhy.net/single-page.md"
DEFAULT_OUTPUT = "bookmarks.html"
DEFAULT_BASE64_SOURCE = "https://rentry.co/FMHYB64"
DEFAULT_NSFW_SOURCE = "https://rentry.org/NSFW-Checkpoint"
DEFAULT_PERSONAL_SOURCE = "personal.md"
DEFAULT_PERSONAL_FOLDER = "Personal"


@dataclass(frozen=True, slots=True)
class PageSpec:
    filename: str
    title: str


# Order matches FMHY's official single-page endpoint.
PAGE_MAP = {
    "privacy.md": "Adblocking / Privacy",
    "ai.md": "Artificial Intelligence",
    "mobile.md": "Android / iOS",
    "audio.md": "Music / Podcasts / Radio",
    "beginners-guide.md": "Beginners Guide",
    "developer-tools.md": "Developer Tools",
    "downloading.md": "Downloading",
    "educational.md": "Educational",
    "file-tools.md": "File Tools",
    "gaming-tools.md": "Gaming Tools",
    "gaming.md": "Gaming / Emulation",
    "image-tools.md": "Image Tools",
    "internet-tools.md": "Internet Tools",
    "linux-macos.md": "Linux / macOS",
    "misc.md": "Miscellaneous",
    "non-english.md": "Non-English",
    "reading.md": "Books / Comics / Manga",
    "social-media-tools.md": "Social Media Tools",
    "storage.md": "Storage",
    "system-tools.md": "System Tools",
    "text-tools.md": "Text Tools",
    "torrenting.md": "Torrenting",
    "unsafe.md": "Unsafe Sites",
    "video-tools.md": "Video Tools",
    "video.md": "Movies / TV / Anime",
}
PAGE_SPECS = tuple(PageSpec(fn, title) for fn, title in PAGE_MAP.items())
PAGE_BY_FILENAME = {spec.filename: spec for spec in PAGE_SPECS}

DOCUMENT_START_RE = re.compile(
    r"(?m)(?=^\*\*\*\s*$\n^\*\*\*\s*$\n"
    r"^\*\*\[◄◄ Back to Wiki Index\]\([^\n]+\)\*\*\s*$)"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
STARRED_RE = re.compile(r"^\s*[*+-]\s+(?:⭐|🌟)\ufe0f?\s*(.+)$")
LIST_ITEM_RE = re.compile(r"^\s*[*+-]\s+(.+)$")
INVISIBLE_RE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
CONNECTOR_WORDS = {"or", "and", "via", "to", "for", "with"}

GENERIC_AUXILIARY_LABELS = {
    "about", "add features", "discord", "documentation", "docs", "github",
    "guide", "info", "issues", "limits", "matrix", "note", "reddit",
    "source", "status", "subreddit", "telegram", "wiki", "x",
}


@dataclass(frozen=True, slots=True)
class Link:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class ResolutionStats:
    resolved_gateways: int = 0
    decoded_destinations: int = 0
    unresolved_gateways: int = 0


def decode_text(data: bytes) -> str:
    return data.decode("utf-8-sig")


def fetch_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    req_headers = {"User-Agent": "fmhy-bookmarks-converter/2.0"} | (headers or {})
    response = httpx.get(url, headers=req_headers, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.content


def documents_from_zip(data: bytes) -> list[tuple[PageSpec, str]]:
    output: list[tuple[PageSpec, str]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        for spec in PAGE_SPECS:
            suffix = f"/docs/{spec.filename}"
            matches = [name for name in names if name.endswith(suffix)]
            if len(matches) != 1:
                raise ValueError(
                    f"Expected one {suffix!r} entry in archive, found {len(matches)}"
                )
            output.append((spec, decode_text(archive.read(matches[0]))))
    return output


def documents_from_directory(directory: Path) -> list[tuple[PageSpec, str]]:
    docs_dir = directory / "docs" if (directory / "docs").is_dir() else directory
    missing = [s.filename for s in PAGE_SPECS if not (docs_dir / s.filename).is_file()]
    if missing:
        raise ValueError(f"Source directory is missing: {', '.join(missing)}")
    return [
        (spec, (docs_dir / spec.filename).read_text(encoding="utf-8-sig"))
        for spec in PAGE_SPECS
    ]


def documents_from_markdown(text: str, source_name: str) -> list[tuple[PageSpec, str]]:
    starts = [m.start() for m in DOCUMENT_START_RE.finditer(text)]
    if starts:
        chunks = [
            text[starts[i] : starts[i + 1] if i + 1 < len(starts) else None]
            for i in range(len(starts))
        ]
        specs_by_title = {spec.title.casefold(): spec for spec in PAGE_SPECS}
        result: list[tuple[PageSpec, str]] = []
        for i, chunk in enumerate(chunks):
            heading_match = re.search(r"^#\s+(.+)$", chunk, re.M)
            title = clean_heading(heading_match.group(1)) if heading_match else f"Page {i + 1}"
            spec = specs_by_title.get(title.casefold())
            if not spec:
                slug = re.sub(r"[^\w]+", "-", title.lower()).strip("-")
                spec = PageSpec(f"{slug}.md", title)
            result.append((spec, chunk))
        return result

    filename = Path(urlsplit(source_name).path).name
    if spec := PAGE_BY_FILENAME.get(filename):
        return [(spec, text)]

    raise ValueError(
        "Markdown source does not contain the expected FMHY documents. "
        "Use the official single-page Markdown, repository ZIP, docs directory, "
        "or one recognised FMHY page file."
    )


def load_documents(source: str) -> list[tuple[PageSpec, str]]:
    path = Path(source)
    if path.is_dir():
        return documents_from_directory(path)
    if path.is_file():
        data = path.read_bytes()
    elif urlsplit(source).scheme in {"http", "https"}:
        data = fetch_bytes(source)
    else:
        raise FileNotFoundError(f"Source not found: {source}")

    if data.startswith(b"PK\x03\x04"):
        return documents_from_zip(data)
    return documents_from_markdown(decode_text(data), source)


def find_closing(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 1
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def markdown_links(text: str) -> list[Link]:
    links: list[Link] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("[", cursor)
        if start < 0:
            break
        if start > 0 and text[start - 1] == "!":
            cursor = start + 1
            continue
        label_end = find_closing(text, start, "[", "]")
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            cursor = start + 1
            continue
        target_end = find_closing(text, label_end + 1, "(", ")")
        if target_end is None:
            cursor = label_end + 1
            continue

        raw_label = text[start + 1 : label_end]
        raw_target = text[label_end + 2 : target_end].strip()
        if raw_target.startswith("<") and ">" in raw_target:
            target = raw_target[1 : raw_target.index(">")]
        else:
            target = raw_target.split(maxsplit=1)[0] if raw_target else ""
        title = clean_label(raw_label)
        if title and target.startswith(("http://", "https://")):
            links.append(Link(title, html.unescape(target)))
        cursor = target_end + 1
    return links


def clean_label(value: str) -> str:
    value = INVISIBLE_RE.sub("", value)
    value = HTML_TAG_RE.sub("", value)
    value = re.sub(r"[*_`~]", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def clean_heading(value: str) -> str:
    links = markdown_links(value)
    if links and value.lstrip().startswith("["):
        value = links[0].title
    value = clean_label(value)
    value = re.sub(r"^[►▷]+\s*", "", value)
    return value.strip() or "General"


def decode_base64_destination(value: str) -> str | None:
    candidate = "".join(value.split())
    for _ in range(3):
        normalized = candidate.translate(str.maketrans("-_", "+/"))
        try:
            decoded = base64.b64decode(
                normalized + "=" * (-len(normalized) % 4), validate=True
            ).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        decoded = decoded.strip()
        if decoded.startswith(("http://", "https://")):
            return decoded
        candidate = decoded
    return None


def read_source_bytes(source: str, headers: dict[str, str] | None = None) -> bytes:
    path = Path(source)
    if path.is_file():
        return path.read_bytes()
    if urlsplit(source).scheme in {"http", "https"}:
        return fetch_bytes(source, headers=headers)
    raise FileNotFoundError(f"Source not found: {source}")


def load_base64_mappings(source: str) -> dict[str, list[str]]:
    soup = BeautifulSoup(decode_text(read_source_bytes(source)), "html.parser")
    mappings: dict[str, list[str]] = {}
    current_id: str | None = None
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "code"]):
        if el.name.startswith("h") and el.get("id"):
            current_id = el["id"]
        elif el.name == "code" and current_id:
            if dest := decode_base64_destination(el.get_text()):
                mappings.setdefault(current_id, []).append(dest)
    if not mappings:
        raise ValueError("No decodable FMHY Base64 mappings were found")
    return mappings


def base58_decode(value: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in value:
        number = number * 58 + alphabet.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return b"\0" * (len(value) - len(value.lstrip("1"))) + raw


def decrypt_privatebin(payload: dict, secret: str, password: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as error:
        raise ValueError(
            "NSFW backup decryption requires the 'cryptography' package"
        ) from error

    spec = payload["adata"][0]
    salt = base64.b64decode(spec[1])
    key = hashlib.pbkdf2_hmac(
        "sha256",
        base58_decode(secret).rjust(32, b"\0") + password.encode("utf-8"),
        salt,
        spec[2],
        dklen=spec[3] // 8,
    )
    adata = json.dumps(payload["adata"], separators=(",", ":")).encode()
    plaintext = AESGCM(key).decrypt(
        base64.b64decode(spec[0]),
        base64.b64decode(payload["ct"]),
        adata,
    )
    if spec[7] == "zlib":
        plaintext = zlib.decompress(plaintext, -15)
    return json.loads(plaintext.decode("utf-8"))["paste"]


def nsfw_markdown_from_checkpoint(checkpoint_html: str) -> str:
    soup = BeautifulSoup(checkpoint_html, "html.parser")
    destinations = [
        dest
        for code in soup.find_all("code")
        if (dest := decode_base64_destination(code.get_text()))
    ]
    pw_match = re.search(r"\(PW:\s*([^)<\s]+)\)", checkpoint_html, re.I)
    password = html.unescape(pw_match.group(1)) if pw_match else ""

    pb_urls = [
        d for d in destinations
        if urlsplit(d).hostname in {"paste.to", "privatebin.net"} and urlsplit(d).fragment
    ]
    if not pb_urls:
        raise ValueError("No decryptable NSFW catalogue backup was found")

    parsed = urlsplit(pb_urls[0])
    fetch_url = pb_urls[0].split("#", 1)[0]
    payload = json.loads(
        decode_text(
            fetch_bytes(fetch_url, headers={"X-Requested-With": "JSONHttpRequest"})
        )
    )
    return decrypt_privatebin(payload, parsed.fragment, password)


def load_nsfw_markdown(source: str) -> str:
    text = decode_text(read_source_bytes(source))
    if "<html" not in text[:500].lower() and "<!doctype html" not in text[:500].lower():
        return text
    return nsfw_markdown_from_checkpoint(text)


def is_internal_section_link(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if host == "reddit.com" and "/r/freemediaheckyeah/wiki/" in path:
        return True
    if host in {"fmhy.net", "fmhy.pages.dev", "fmhyclone.pages.dev"} and parsed.fragment:
        return True
    return False


def split_description(text: str) -> tuple[str, str]:
    sep_pattern = re.compile(r"\s+[-–—]\s+")
    for match in sep_pattern.finditer(text):
        sep_start, sep_end = match.span()
        prefix_part = text[:sep_start]
        if prefix_part.count("[") == prefix_part.count("]") and prefix_part.count("(") == prefix_part.count(")"):
            return text[:sep_start], text[sep_end:]
    return text, ""


def group_title(prefix: str, links: Iterable[Link] | None = None) -> str:
    without_links = re.sub(r"\[.*?\]\(.*?\)", "", prefix)
    title = clean_label(without_links).strip(" ,/|:-")
    return "" if title.casefold() in CONNECTOR_WORDS else title


def links_from_item(body: str, include_auxiliary: bool) -> list[Link]:
    body = re.sub(r"^(?:⭐|🌟|🌐|↪)\ufe0f?\s*", "", body)
    prefix, details = split_description(body)
    prefix_links = markdown_links(prefix)

    if include_auxiliary:
        selected = markdown_links(body)
        group = group_title(prefix)
    elif prefix_links:
        selected = [
            link
            for link in prefix_links
            if link.title.casefold() not in GENERIC_AUXILIARY_LABELS
        ]
        group = ""
    else:
        selected = markdown_links(details)
        group = group_title(prefix) or clean_label(prefix).strip(" ,/|:-")

    result: list[Link] = []
    seen_urls: set[str] = set()
    base_title = next(
        (
            link.title
            for link in selected
            if not link.title.isdigit()
            and link.title.casefold() not in GENERIC_AUXILIARY_LABELS
        ),
        group or "Resource",
    )
    parent = group if (group and group.casefold() not in CONNECTOR_WORDS) else base_title

    for link in selected:
        if is_internal_section_link(link.url) or link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        title = link.title
        if title.isdigit():
            title = f"{base_title} (mirror {title})"
        elif parent and title.casefold() in GENERIC_AUXILIARY_LABELS:
            title = f"{parent} ({title})"
        result.append(Link(title=title, url=link.url))
    return result


def links_from_starred_item(body: str, include_auxiliary: bool) -> list[Link]:
    return links_from_item(body, include_auxiliary)


BookmarkTree = dict[str, dict[str, list[Link]]]


def _parse_sections(
    markdown: str, min_level: int, all_items: bool, include_auxiliary: bool
) -> dict[str, list[Link]]:
    sections: dict[str, list[Link]] = {}
    current: str | None = "General" if min_level == 1 else None
    for line in markdown.splitlines():
        if (h := HEADING_RE.match(line)) and len(h.group(1)) >= min_level:
            if min_level == 1 and len(h.group(1)) > 1:
                continue
            current = clean_heading(h.group(2))
        elif current is not None:
            item = LIST_ITEM_RE.match(line) if all_items else STARRED_RE.match(line)
            if item and (links := links_from_item(item.group(1), include_auxiliary)):
                sections.setdefault(current, []).extend(links)
    return sections


def build_tree(
    documents: Iterable[tuple[PageSpec, str]], include_auxiliary: bool = False
) -> BookmarkTree:
    tree: BookmarkTree = {}
    for spec, markdown in documents:
        if sections := _parse_sections(markdown, 1, False, include_auxiliary):
            tree[spec.title] = sections
    return tree


def add_nsfw_catalogue(
    tree: BookmarkTree, markdown: str, include_auxiliary: bool = False
) -> None:
    if sections := _parse_sections(markdown, 2, True, include_auxiliary):
        tree["NSFW"] = sections


def resolve_base64_gateways(
    tree: BookmarkTree, mappings: dict[str, list[str]]
) -> ResolutionStats:
    resolved = decoded = unresolved = 0
    for sections in tree.values():
        for section, links in sections.items():
            updated: list[Link] = []
            for link in links:
                parsed = urlsplit(link.url)
                host = (parsed.hostname or "").lower()
                if host not in {"rentry.co", "rentry.org"} or parsed.path.lower() != "/fmhyb64":
                    updated.append(link)
                    continue
                destinations = mappings.get(parsed.fragment, [])
                if not destinations:
                    unresolved += 1
                    updated.append(link)
                    continue
                resolved += 1
                for index, destination in enumerate(destinations, start=1):
                    title = link.title if index == 1 else f"{link.title} (decoded {index})"
                    updated.append(Link(title, destination))
                    decoded += 1
            sections[section] = updated
    return ResolutionStats(resolved, decoded, unresolved)


def render_bookmarks(tree: BookmarkTree) -> str:
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for page, sections in tree.items():
        lines.append(f"    <DT><H3>{html.escape(page)}</H3>")
        lines.append("    <DL><p>")
        for section, links in sections.items():
            lines.append(f"        <DT><H3>{html.escape(section)}</H3>")
            lines.append("        <DL><p>")
            for link in links:
                lines.append(
                    f'            <DT><A HREF="{html.escape(link.url, quote=True)}">'
                    f"{html.escape(link.title)}</A>"
                )
            lines.append("        </DL><p>")
        lines.append("    </DL><p>")
    lines.append("</DL><p>")
    return "\n".join(lines) + "\n"


def count_tree(tree: BookmarkTree) -> tuple[int, int, int]:
    pages = len(tree)
    sections = sum(len(val) for val in tree.values())
    bookmarks = sum(len(links) for val in tree.values() for links in val.values())
    return pages, sections, bookmarks


def parse_bookmark_spec(spec: str) -> tuple[str, Link]:
    section = "General"
    raw = spec.strip()
    if ":" in raw and not raw.startswith(("http://", "https://")):
        prefix, rest = raw.split(":", 1)
        if not rest.startswith("//"):
            section = clean_heading(prefix)
            raw = rest.strip()
    if "|" in raw:
        title_part, url_part = raw.split("|", 1)
        title, url = clean_label(title_part), url_part.strip()
    elif "=" in raw and not raw.startswith(("http://", "https://")):
        title_part, url_part = raw.split("=", 1)
        title, url = clean_label(title_part), url_part.strip()
    else:
        url = raw
        parsed = urlsplit(url if url.startswith(("http://", "https://")) else f"https://{url}")
        host = parsed.hostname or url
        title = host.removeprefix("www.")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return section, Link(title=title or "Bookmark", url=url)


def load_personal_bookmarks(
    source: str | None = None, inline_specs: list[str] | None = None
) -> dict[str, list[Link]]:
    sections: dict[str, list[Link]] = {}
    if source:
        path = Path(source)
        if path.is_file():
            content = decode_text(path.read_bytes())
        elif urlsplit(source).scheme in {"http", "https"}:
            content = decode_text(fetch_bytes(source))
        else:
            raise FileNotFoundError(f"Personal bookmarks file not found: {source}")
        sections = _parse_sections(content, min_level=1, all_items=True, include_auxiliary=True)
    if inline_specs:
        for spec in inline_specs:
            section, link = parse_bookmark_spec(spec)
            sections.setdefault(section, []).append(link)
    return sections


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert starred FMHY recommendations to bookmark HTML."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_SOURCE,
        help="Single-page Markdown URL/file, FMHY repository ZIP, or docs directory",
    )
    parser.add_argument(
        "--personal",
        nargs="?",
        const=DEFAULT_PERSONAL_SOURCE,
        default=None,
        help="Path or URL to personal bookmarks Markdown file (auto-loaded from personal.md if present)",
    )
    parser.add_argument(
        "--no-personal",
        action="store_true",
        help="Do not include personal bookmarks even if personal.md exists",
    )
    parser.add_argument(
        "--add-bookmark",
        action="append",
        dest="bookmarks",
        default=[],
        help="Add custom bookmark (format: 'URL', 'Title|URL', or 'Section:Title|URL')",
    )
    parser.add_argument(
        "--personal-folder",
        default=DEFAULT_PERSONAL_FOLDER,
        help="Name of top-level personal bookmarks folder (default: 'Personal')",
    )
    parser.add_argument(
        "--base64-source",
        default=DEFAULT_BASE64_SOURCE,
        help="Rendered FMHYB64 mapping page URL or local HTML file",
    )
    parser.add_argument(
        "--nsfw-source",
        default=DEFAULT_NSFW_SOURCE,
        help="Official NSFW checkpoint URL or decrypted local Markdown file",
    )
    parser.add_argument(
        "--keep-base64-gateways",
        action="store_true",
        help="Do not replace FMHYB64 gateway links with decoded destinations",
    )
    parser.add_argument(
        "--skip-nsfw",
        action="store_true",
        help="Do not add the complete external NSFW catalogue",
    )
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT, help="Output HTML path")
    parser.add_argument(
        "--include-auxiliary",
        action="store_true",
        help="Also include notes, social profiles, source repositories, and other links on starred lines",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        documents = load_documents(args.source)
        tree = build_tree(documents, include_auxiliary=args.include_auxiliary)

        personal_source = args.personal
        if personal_source is None and not args.no_personal and Path(DEFAULT_PERSONAL_SOURCE).is_file():
            personal_source = DEFAULT_PERSONAL_SOURCE
        if (personal_source and not args.no_personal) or args.bookmarks:
            personal_sections = load_personal_bookmarks(
                source=personal_source if not args.no_personal else None,
                inline_specs=args.bookmarks,
            )
            if personal_sections:
                tree = {args.personal_folder: personal_sections, **tree}

        if not args.skip_nsfw:
            add_nsfw_catalogue(
                tree,
                load_nsfw_markdown(args.nsfw_source),
                include_auxiliary=True,
            )
        resolution = ResolutionStats()
        if not args.keep_base64_gateways:
            resolution = resolve_base64_gateways(
                tree, load_base64_mappings(args.base64_source)
            )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_bookmarks(tree), encoding="utf-8")
    except (OSError, ValueError, zipfile.BadZipFile, httpx.HTTPError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    pages, sections, bookmarks = count_tree(tree)
    print(
        f"Wrote {bookmarks} bookmarks in {sections} sections and {pages} "
        f"top-level folders to {output}"
    )
    print(
        f"Decoded {resolution.resolved_gateways} Base64 gateway occurrences "
        f"into {resolution.decoded_destinations} destinations; "
        f"{resolution.unresolved_gateways} gateways could not be resolved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
