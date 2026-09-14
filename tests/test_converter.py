from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from convert_fmhy_bookmarks import (  # noqa: E402
    Link,
    PageSpec,
    add_nsfw_catalogue,
    build_tree,
    decode_base64_destination,
    documents_from_markdown,
    group_title,
    is_internal_section_link,
    links_from_starred_item,
    load_personal_bookmarks,
    markdown_links,
    parse_bookmark_spec,
    render_bookmarks,
    resolve_base64_gateways,
    SINGLE_PAGE_SPECS,
)


class MarkdownLinkTests(unittest.TestCase):
    def test_balanced_parentheses_in_url(self) -> None:
        links = markdown_links("[Example](https://example.com/a_(b))")
        self.assertEqual(links, [Link("Example", "https://example.com/a_(b)")])

    def test_primary_links_exclude_auxiliary_links(self) -> None:
        body = (
            "**[Main](https://main.example/)** or [Mirror](https://mirror.example/) "
            "- Description / [Discord](https://discord.gg/example)"
        )
        self.assertEqual(
            links_from_starred_item(body, include_auxiliary=False),
            [
                Link("Main", "https://main.example/"),
                Link("Mirror", "https://mirror.example/"),
            ],
        )

    def test_named_group_uses_links_after_separator(self) -> None:
        body = "**Useful Tools** - [One](https://one.example/) / [Two](https://two.example/)"
        self.assertEqual(
            links_from_starred_item(body, include_auxiliary=False),
            [Link("One", "https://one.example/"), Link("Two", "https://two.example/")],
        )

    def test_internal_fmhy_section_links_are_excluded(self) -> None:
        self.assertTrue(
            is_internal_section_link(
                "https://www.reddit.com/r/FREEMEDIAHECKYEAH/wiki/video#wiki_section"
            )
        )

    def test_base64_destination_is_decoded(self) -> None:
        self.assertEqual(
            decode_base64_destination("aHR0cHM6Ly9leGFtcGxlLmNvbS8="),
            "https://example.com/",
        )

    def test_hyphen_in_link_title(self) -> None:
        body = "[PDF24 - Creator](https://www.pdf24.org/) - Free PDF tools."
        links = links_from_starred_item(body, include_auxiliary=False)
        self.assertEqual(links, [Link("PDF24 - Creator", "https://www.pdf24.org/")])

    def test_formatted_link_in_group_title(self) -> None:
        title = group_title("[**My Tool**](https://example.com)")
        self.assertEqual(title, "")

    def test_urlsafe_base64_decoding(self) -> None:
        url = "https://example.com/search?q=test_1&filter=all"
        b64 = base64.urlsafe_b64encode(url.encode()).decode()
        self.assertEqual(decode_base64_destination(b64), url)

    def test_auxiliary_label_qualified_with_base_title(self) -> None:
        body = "[Boorusama](https://github.com/khoadng/Boorusama) / [Discord](https://discord.gg/example)"
        links = links_from_starred_item(body, include_auxiliary=True)
        self.assertEqual(
            links,
            [
                Link("Boorusama", "https://github.com/khoadng/Boorusama"),
                Link("Boorusama (Discord)", "https://discord.gg/example"),
            ],
        )

    def test_connector_word_not_used_as_group_title(self) -> None:
        body = "[CoomerDL](https://emydevs.com/) or [GitHub](https://github.com/Emy69/CoomerDL)"
        links = links_from_starred_item(body, include_auxiliary=True)
        self.assertEqual(
            links,
            [
                Link("CoomerDL", "https://emydevs.com/"),
                Link("CoomerDL (GitHub)", "https://github.com/Emy69/CoomerDL"),
            ],
        )

    def test_em_dash_and_en_dash_separators(self) -> None:
        body_em = "[Tool A](https://a.example/) — Em-dash description"
        body_en = "[Tool B](https://b.example/) – En-dash description"
        self.assertEqual(
            links_from_starred_item(body_em, include_auxiliary=False),
            [Link("Tool A", "https://a.example/")],
        )
        self.assertEqual(
            links_from_starred_item(body_en, include_auxiliary=False),
            [Link("Tool B", "https://b.example/")],
        )


class TreeTests(unittest.TestCase):
    def test_two_content_levels_and_starred_only(self) -> None:
        source = """
# ► First Section
* ⭐ **[Keep](https://keep.example/)** - Recommended
* [Drop](https://drop.example/) - Not recommended
## ▷ Lower Heading
* ⭐ **[Still First](https://still.example/)** - Recommended
# ► Second Section
* ⭐ **[Other](https://other.example/)** - Recommended
"""
        tree = build_tree([(PageSpec("sample.md", "Top Folder"), source)])
        self.assertEqual(list(tree), ["Top Folder"])
        self.assertEqual(list(tree["Top Folder"]), ["First Section", "Second Section"])
        self.assertEqual(len(tree["Top Folder"]["First Section"]), 2)

        output = render_bookmarks(tree)
        self.assertNotIn("FMHY</H3>", output)
        self.assertNotIn("drop.example", output)
        self.assertEqual(output.count("<DL><p>"), output.count("</DL><p>"))

    def test_nsfw_catalogue_includes_starred_and_unstarred_items(self) -> None:
        tree = build_tree([])
        add_nsfw_catalogue(
            tree,
            """
## Streaming
* ⭐ **[Starred](https://starred.example/)**
* [Unstarred](https://unstarred.example/)
### Images
* [Image](https://image.example/)
""",
        )
        self.assertEqual(list(tree["NSFW"]), ["Streaming", "Images"])
        self.assertEqual(len(tree["NSFW"]["Streaming"]), 2)

    def test_base64_gateway_resolution_retains_missing_mapping(self) -> None:
        tree = build_tree(
            [
                (
                    PageSpec("sample.md", "Top"),
                    """
# Section
* ⭐ [Decoded](https://rentry.co/FMHYB64#known)
* ⭐ [Fallback](https://rentry.co/FMHYB64#missing)
""",
                )
            ]
        )
        stats = resolve_base64_gateways(tree, {"known": ["https://direct.example/"]})
        urls = [link.url for link in tree["Top"]["Section"]]
        self.assertEqual(urls, ["https://direct.example/", "https://rentry.co/FMHYB64#missing"])
        self.assertEqual(stats.resolved_gateways, 1)
        self.assertEqual(stats.unresolved_gateways, 1)

    def test_resilient_page_splitting(self) -> None:
        markdown = (
            "***\n***\n**[◄◄ Back to Wiki Index](https://fmhy.net/)**\n\n"
            "# Page One\n* ⭐ [One](https://one.example/)\n"
            "***\n***\n**[◄◄ Back to Wiki Index](https://fmhy.net/)**\n\n"
            "# Brand New Page\n* ⭐ [Two](https://two.example/)\n"
        )
        docs = documents_from_markdown(markdown, "single-page.md")
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0][0].title, "Page One")
        self.assertEqual(docs[1][0].title, "Brand New Page")

    def test_variation_selector_in_star_emoji(self) -> None:
        source = "# Section\n* ⭐\ufe0f [Starred](https://starred.example/)"
        tree = build_tree([(PageSpec("test.md", "Test"), source)])
        self.assertEqual(len(tree["Test"]["Section"]), 1)

    def test_parse_bookmark_spec(self) -> None:
        sec1, link1 = parse_bookmark_spec("https://vibemathed.com/")
        self.assertEqual(sec1, "General")
        self.assertEqual(link1, Link("vibemathed.com", "https://vibemathed.com/"))

        sec2, link2 = parse_bookmark_spec("Vibemathed|https://vibemathed.com/")
        self.assertEqual(sec2, "General")
        self.assertEqual(link2, Link("Vibemathed", "https://vibemathed.com/"))

        sec3, link3 = parse_bookmark_spec("Favorites:Vibemathed|https://vibemathed.com/")
        self.assertEqual(sec3, "Favorites")
        self.assertEqual(link3, Link("Vibemathed", "https://vibemathed.com/"))

    def test_load_personal_bookmarks(self) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as f:
            f.write("# Math\n* [Vibemathed](https://vibemathed.com/)\n")
            f.flush()
            path = f.name

        try:
            sections = load_personal_bookmarks(
                source=path,
                inline_specs=["Daily:GitHub|https://github.com/"],
            )
            self.assertEqual(list(sections), ["Math", "Daily"])
            self.assertEqual(sections["Math"], [Link("Vibemathed", "https://vibemathed.com/")])
            self.assertEqual(sections["Daily"], [Link("GitHub", "https://github.com/")])
        finally:
            Path(path).unlink(missing_ok=True)

    def test_personal_folder_prepended_at_top(self) -> None:
        source = "# Section\n* ⭐ [Item](https://item.example/)"
        tree = build_tree([(PageSpec("sample.md", "FMHY Category"), source)])
        personal = {"Favorites": [Link("Vibemathed", "https://vibemathed.com/")]}

        # Prepend personal folder
        combined_tree = {"Personal": personal, **tree}
        self.assertEqual(list(combined_tree), ["Personal", "FMHY Category"])

        html = render_bookmarks(combined_tree)
        personal_pos = html.find("<DT><H3>Personal</H3>")
        fmhy_pos = html.find("<DT><H3>FMHY Category</H3>")
        self.assertTrue(0 < personal_pos < fmhy_pos)

    def test_headless_personal_bookmarks_rendered_flat(self) -> None:
        personal = {"General": [Link("Tool", "https://example.com/")]}
        tree = {"Personal": personal}
        html = render_bookmarks(tree)
        self.assertIn("<DT><H3>Personal</H3>", html)
        self.assertNotIn("<DT><H3>General</H3>", html)
        self.assertIn('<DT><A HREF="https://example.com/">Tool</A>', html)

    def test_level2_fallback_when_no_level1_headings(self) -> None:
        source = "## Mockups\n* ⭐ [Shots](https://shots.so/)"
        tree = build_tree([(PageSpec("storage.md", "Storage"), source)])
        self.assertEqual(list(tree["Storage"]), ["Mockups"])
        self.assertEqual(len(tree["Storage"]["Mockups"]), 1)

    def test_single_page_specs_matching_when_exact_count(self) -> None:
        chunk = "***\n***\n**[◄◄ Back to Wiki Index](https://fmhy.net/)**\n\n# Header\n* ⭐ [Link](https://a.com)\n"
        markdown = chunk * len(SINGLE_PAGE_SPECS)
        docs = documents_from_markdown(markdown, "single-page.md")
        self.assertEqual(len(docs), len(SINGLE_PAGE_SPECS))
        self.assertEqual([d[0] for d in docs], list(SINGLE_PAGE_SPECS))


if __name__ == "__main__":
    unittest.main()
