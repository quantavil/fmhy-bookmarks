# FMHY starred bookmarks converter

This project converts FMHY resources into a standard Netscape bookmarks HTML file that Chrome, Chromium, Brave, Edge, Firefox and other browsers can import.

## Output rules

1. Only list items marked with `⭐` or `🌟` are included.
2. There is no `FMHY` wrapper folder.
3. The first folder level is the FMHY page, such as `Artificial Intelligence`.
4. The second folder level is the page's level-one heading, such as `AI Chatbots`.
5. Lower headings are flattened into their nearest level-one section.
6. FMHY internal section-navigation links are excluded.
7. The same URL is retained when it occurs in different contexts.
8. By default, descriptions, social profiles, notes and source links attached to a recommended entry are excluded.
9. The separate official NSFW catalogue is added under a direct `NSFW` folder. Every external catalogue link is included, whether starred, unstarred, primary or auxiliary.
10. `FMHYB64` gateway links are decoded through FMHY's current mapping page and replaced with their direct destinations.
11. Custom personal bookmarks (from `personal.md` or `--add-bookmark`) are placed in a `Personal` folder at the very top of the bookmark tree.

The browser itself may place imported bookmarks inside an automatically created `Imported` folder. Bookmark HTML cannot control that browser behaviour.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

Install dependencies and set up virtual environment:

```bash
uv sync
```

## Generate bookmarks

Run with `uv` (or `python3`):

```bash
uv run convert_fmhy_bookmarks.py
```

Use a downloaded Markdown file:

```bash
uv run convert_fmhy_bookmarks.py single-page.md -o bookmarks.html
```

Use the official repository ZIP:

```bash
uv run convert_fmhy_bookmarks.py main.zip -o bookmarks.html
```

Use a checked-out repository or its `docs` directory:

```bash
uv run convert_fmhy_bookmarks.py /path/to/edit-main
```

Add every auxiliary hyperlink appearing on starred lines in the regular FMHY pages. NSFW auxiliary links are always included:

```bash
uv run convert_fmhy_bookmarks.py --include-auxiliary
```

Exclude the external NSFW catalogue:

```bash
uv run convert_fmhy_bookmarks.py --skip-nsfw
```

Keep the original `FMHYB64` gateway links instead of resolving them:

```bash
uv run convert_fmhy_bookmarks.py --keep-base64-gateways
```

## Personal bookmarks

You can keep your own custom bookmarks organized in a `Personal` folder placed at the very top of the bookmark tree.

### 1. Using `personal.md` (Recommended)

Create or edit `personal.md` in the project root:

```markdown
# Favorites
* [Vibemathed](https://vibemathed.com/) - Interactive math & visualizations

# Development
* [GitHub](https://github.com/)
* [Hugging Face](https://huggingface.co/)
```

`personal.md` is automatically detected and loaded into the top-level `Personal` folder. To specify a custom file or disable personal bookmarks:

```bash
uv run convert_fmhy_bookmarks.py --personal my-links.md
uv run convert_fmhy_bookmarks.py --no-personal
```

### 2. Using `--add-bookmark` via CLI

Add individual bookmarks directly from the command line:

```bash
uv run convert_fmhy_bookmarks.py --add-bookmark "https://vibemathed.com/"
uv run convert_fmhy_bookmarks.py --add-bookmark "Vibemathed|https://vibemathed.com/"
uv run convert_fmhy_bookmarks.py --add-bookmark "Math:Vibemathed|https://vibemathed.com/"
```

## Test

Run the test suite with `uv`:

```bash
uv run python -m unittest discover -s tests -v
```

## Included generated file

`bookmarks.html` was generated from the FMHY source snapshot recorded in `SOURCE.md`. It contains:

The statistics below are regenerated for every release and recorded in `SOURCE.md`.

## Source

The generated bookmark file uses FMHY's official `single-page.md`, `FMHYB64` mapping and NSFW checkpoint sources. Source content remains attributable to the FMHY project and its contributors.
