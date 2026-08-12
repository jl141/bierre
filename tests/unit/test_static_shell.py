"""Guards on the front-end shell that no Python test would otherwise catch.

The front end has no build step and no JavaScript test runner, so nothing except
a browser notices a mistyped `import` path or a `<link>` that points at a file
that was renamed. These checks are cheap, they run in the existing CI, and each
one maps to a requirement of the UI PRD's §3.4 module layout or its §7.6 markup
fixes.

What is deliberately *not* here: behaviour. Rendering, routing and capability
gating belong in the browser-level tests WS-I adds.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parents[2] / "webapp" / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# `webapp/static/**/*.js`, but not the vendored favicon folder.
JS_FILES = sorted(path for path in STATIC_DIR.rglob("*.js") if "favicon_io" not in path.parts)

EXPECTED_MODULES = (
    "app.js",
    "lib/api.js",
    "lib/dom.js",
    "lib/format.js",
    "lib/router.js",
    "lib/storage.js",
    "lib/store.js",
    "views/search.js",
    "views/results.js",
    "views/settings.js",
    "components/nav.js",
    "components/account-menu.js",
    "components/footer.js",
    "components/status.js",
    "components/profile-dialog.js",
    "css/tokens.css",
    "css/base.css",
    "css/components.css",
    "css/layout.css",
)

IMPORT_PATTERN = re.compile(r"""\bfrom\s+["'](\.[^"']+)["']""")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*")


def _code(path: Path) -> str:
    """Source with comments removed, so the checks below read code, not prose.

    Several modules document *why* they avoid an API by naming it.
    """
    source = _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8"))
    return "\n".join(_LINE_COMMENT.sub("", line) for line in source.splitlines())


class _Index(HTMLParser):
    """Collects just enough of `index.html` to assert on its shape."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs_by_tag: dict[str, list[dict[str, str]]] = {}
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        self.tags.append(tag)
        self.attrs_by_tag.setdefault(tag, []).append(attributes)
        if "id" in attributes:
            self.ids.add(attributes["id"])


@pytest.fixture(scope="module")
def index_source() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index(index_source: str) -> _Index:
    parser = _Index()
    parser.feed(index_source)
    return parser


@pytest.mark.parametrize("relative_path", EXPECTED_MODULES)
def test_the_module_layout_is_present(relative_path: str) -> None:
    assert (STATIC_DIR / relative_path).is_file()


def test_the_entry_point_is_loaded_as_a_module(index: _Index) -> None:
    """Without `type="module"` every `import` below it is a syntax error."""
    scripts = index.attrs_by_tag["script"]

    assert [script for script in scripts if script.get("type") == "module"] == scripts


@pytest.mark.parametrize("path", JS_FILES, ids=lambda path: path.name)
def test_every_relative_import_resolves(path: Path) -> None:
    """No bundler means a typo'd path is a blank page, not a build failure."""
    missing = [
        target
        for target in IMPORT_PATTERN.findall(_code(path))
        if not (path.parent / target).resolve().is_file()
    ]

    assert missing == []


def test_every_referenced_asset_exists(index: _Index) -> None:
    referenced = [attrs["href"] for attrs in index.attrs_by_tag["link"]]
    referenced += [attrs["src"] for attrs in index.attrs_by_tag["script"]]
    missing = [href for href in referenced if not (STATIC_DIR / href.lstrip("/")).is_file()]

    assert missing == []


def test_the_head_contains_every_link(index: _Index) -> None:
    """They sat before `<head>` and browsers silently hoisted them (§7.6)."""
    head_open = index.tags.index("head")
    first_link = index.tags.index("link")

    assert head_open < first_link


def test_the_page_describes_itself(index: _Index) -> None:
    metas = {attrs.get("name"): attrs.get("content", "") for attrs in index.attrs_by_tag["meta"]}

    assert metas.get("description")


@pytest.mark.parametrize("tag", ["header", "nav", "main", "footer"])
def test_the_shell_uses_landmarks(index: _Index, tag: str) -> None:
    assert tag in index.tags


def test_the_router_outlet_is_a_skip_link_target(index: _Index, index_source: str) -> None:
    main = index.attrs_by_tag["main"][0]

    assert main.get("id") == "main"
    assert main.get("tabindex") == "-1"
    assert 'href="#main"' in index_source


def test_a_scriptless_browser_is_told_why_nothing_works(index: _Index) -> None:
    assert "noscript" in index.tags


@pytest.mark.parametrize("relationship", ["aria-labelledby", "aria-describedby"])
def test_both_dialogs_name_and_describe_themselves(index: _Index, relationship: str) -> None:
    """A `<dialog>` with no accessible name is announced as just "dialog"."""
    dialogs = index.attrs_by_tag["dialog"]
    assert len(dialogs) == 2

    for dialog in dialogs:
        assert dialog[relationship] in index.ids


@pytest.mark.parametrize("path", JS_FILES, ids=lambda path: path.name)
def test_no_module_builds_markup_from_strings(path: Path) -> None:
    """`lib/dom.js`'s `h()` exists so third-party paper metadata is never parsed
    as HTML. One `innerHTML` re-opens the injection this removed."""
    source = _code(path)

    assert "innerHTML" not in source
    assert "outerHTML" not in source
    assert "document.write" not in source


def test_the_access_token_cannot_reach_a_storage_api() -> None:
    """`lib/api.js` owns the token and is the only module that could leak it.

    WS-F asserts the same property from the browser; this is the static half,
    and it fails the moment someone reaches for a convenient cache.
    """
    source = _code(STATIC_DIR / "lib" / "api.js")

    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "document.cookie =" not in source


@pytest.mark.parametrize("path", JS_FILES, ids=lambda path: path.name)
def test_only_the_storage_module_talks_to_localstorage(path: Path) -> None:
    """One namespaced, try/catch-wrapped accessor, so a quota error or Safari's
    private mode cannot take a view down (§3.4)."""
    if path.name == "storage.js":
        pytest.skip("the module under discussion")

    assert "localStorage" not in _code(path)
