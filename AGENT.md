# Project Agent Knowledge

## Structure
- `convert_fmhy_bookmarks.py`: Core CLI converter parsing FMHY Markdown, Rentry Base64 gateways, and PrivateBin NSFW checkpoints into Netscape bookmark HTML.
- `personal.md`: Local personal bookmarks source file placed at the top of the bookmarks hierarchy.
- `bookmarks.html`: Generated Netscape bookmark HTML file ready for browser import.
- `pyproject.toml`: Modern Python >=3.12 project specification with `hatchling` build system and dependencies (`httpx`, `beautifulsoup4`, `cryptography`).
- `uv.lock`: Deterministic dependency lockfile managed exclusively via `uv`.
- `tests/test_converter.py`: Unittest suite verifying link extraction, base64 decoding, tree building, and personal bookmark integration.
- `README.md`: User documentation and usage guide.
- `SOURCE.md`: Upstream FMHY snapshot and output statistics record.

## Blunders & Fixes
- Naive `text.split(" - ", 1)` split inside tool names containing hyphens (`[PDF24 - Creator](...) - Description`), dropping the bookmark. Fixed by only splitting on `\s+[-–—]\s+` outside markdown brackets.
- Stripped links left grammatical connector words (`"or"`, `"and"`) in `group_title`, generating bookmarks named `"or (GitHub)"` and `"or (Telegram)"`. Fixed by ignoring connector words and inheriting `base_title`.
- Unparented auxiliary links on lines without prefix text emitted 26 bare bookmarks named `"Discord"` or `"Telegram"`. Fixed by qualifying with `base_title`.
- Markdown formatting inside link brackets (`[**Tool**](...)`) broke string replacement in `group_title`. Fixed by stripping links via regex `re.sub(r"\[.*?\]\(.*?\)", "", prefix)`.
- URL-safe base64 strings containing `-` and `_` raised `binascii.Error` in `decode_base64_destination`. Fixed by normalizing with `candidate.translate(str.maketrans("-_", "+/"))`.
- Dynamically parsing first `# Heading` in single-page chunks misnamed `non-english.md` as `Arabic / العربية` and `storage.md` as `Page 18`. Fixed by matching chunks to `SINGLE_PAGE_SPECS`.

## Non-Obvious Discoveries
- System has `uv` installed, but lacks `pip`; `requirements.txt` was deleted to prevent dual-manifest drift.
- Hatchling requires `[tool.hatch.build.targets.wheel] include = ["convert_fmhy_bookmarks.py"]` for root-level single-file modules.
- Python 3.7+ native `dict` maintains insertion order, making `OrderedDict` completely redundant for Netscape bookmark tree generation.
- The `Personal` folder is placed first by prepending to the dictionary: `tree = {args.personal_folder: personal_sections, **tree}`.
