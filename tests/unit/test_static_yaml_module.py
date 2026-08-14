"""Parity checks for `webapp/static/lib/yaml.js` against PyYAML.

The front end has no build step and no npm, so profile import/export ships with a
hand-written YAML subset (see that module's header for what it refuses and why).
The risk that buys is drift: a file the *server* reads with `yaml.safe_load` must
mean the same thing when the *browser* reads it, or an import previews one profile
and saves another.

These tests are the guard. They run the real module in Node and compare it with
PyYAML on the twelve checked-in profiles — the corpus an exported file has to be
diffable against — plus the constructs the corpus does not cover. Node is not a
project dependency, so they skip where it is absent rather than fail; CI has it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
YAML_MODULE = REPO_ROOT / "webapp" / "static" / "lib" / "yaml.js"
PROFILES_DIR = REPO_ROOT / "profiles"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# One document per construct, each valid YAML that PyYAML also reads.
DOCUMENTS = {
    "empty collections": "a: {}\nb: []\nc:\nd: ~\n",
    "quoting": "a: 'it''s'\nb: \"line\\nbreak\"\nc: 'yes'\nd: yes\ne: 12\nf: 1.5\ng: '#hash'\nh: 'a: b'\n",
    "plain scalar folded over lines": "q: this is a long\n  plain scalar folded\n  over lines\nnext: 1\n",
    "block scalars": "lit: |\n  one\n  two\nfold: >\n  one\n  two\nstrip: |-\n  x\n",
    "flow collections": "terms: [a, b, 'c d']\nmap: {id: core, boost: 15, fallback: true}\n",
    "comments": "# lead\na: 1 # trailing\n# between\nb: 'has # inside'\n",
    "nested sequences": "items:\n- name: a\n  terms:\n  - x\n  - y\n- name: b\n  terms: []\n",
    "document marker": "---\na: 1\n",
    "compact nesting": "rows:\n  - - 1\n    - 2\n  - k: v\n",
}

# Constructs the module refuses on purpose. `safe_load` accepts some of them;
# refusing is the stricter, deliberate choice documented in the module header.
REFUSED = {
    "anchor": "a: &x 1\nb: *x\n",
    "tag": "a: !!python/object:os.system []\n",
    "merge key": "a: &base {x: 1}\nb:\n  <<: *base\n",
    "two documents": "a: 1\n---\nb: 2\n",
    "tab indentation": "a:\n\tb: 1\n",
    "unterminated quote": "a: 'oops\n",
    "unclosed flow": "a: [1, 2\n",
}

HARNESS = """
import {{ dumpYaml, parseYaml }} from "{module}";

const input = JSON.parse(process.argv[2]);
const out = {{}};
for (const [name, text] of Object.entries(input)) {{
  try {{
    const parsed = parseYaml(text);
    out[name] = {{ ok: true, parsed, dumped: dumpYaml(parsed) }};
  }} catch (error) {{
    out[name] = {{ ok: false, error: error.message }};
  }}
}}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def run_module(tmp_path_factory: pytest.TempPathFactory):
    """Run the module in Node over a `{name: yaml text}` map.

    The module is copied to `.mjs` because the repository has no `package.json`,
    so Node would otherwise read a `.js` file as CommonJS and refuse its exports.
    """
    workspace = tmp_path_factory.mktemp("yaml-module")
    module_copy = workspace / "yaml.mjs"
    module_copy.write_text(YAML_MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    harness = workspace / "harness.mjs"
    harness.write_text(textwrap.dedent(HARNESS.format(module="./yaml.mjs")), encoding="utf-8")

    def run(documents: dict[str, str]) -> dict[str, dict]:
        completed = subprocess.run(
            ["node", harness.name, json.dumps(documents)],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    return run


@pytest.fixture(scope="module")
def profile_documents() -> dict[str, str]:
    files = sorted(PROFILES_DIR.glob("*.yaml"))
    assert files, "the built-in profiles are the corpus these tests need"
    return {path.name: path.read_text(encoding="utf-8") for path in files}


def test_parsing_a_builtin_profile_matches_pyyaml(run_module, profile_documents) -> None:
    results = run_module(profile_documents)
    parsed = {name: results[name]["parsed"] for name in profile_documents}
    expected = {name: yaml.safe_load(text) for name, text in profile_documents.items()}

    assert parsed == expected


def test_dumping_a_builtin_profile_round_trips_through_pyyaml(run_module, profile_documents) -> None:
    """What the browser writes, the account service has to be able to read."""
    results = run_module(profile_documents)
    reloaded = {name: yaml.safe_load(results[name]["dumped"]) for name in profile_documents}
    expected = {name: yaml.safe_load(text) for name, text in profile_documents.items()}

    assert reloaded == expected


def test_supported_constructs_match_pyyaml(run_module) -> None:
    results = run_module(DOCUMENTS)
    parsed = {name: results[name].get("parsed") for name in DOCUMENTS}
    expected = {name: yaml.safe_load(text) for name, text in DOCUMENTS.items()}

    assert parsed == expected


def test_a_dumped_document_reparses_to_the_same_value(run_module) -> None:
    results = run_module(DOCUMENTS)
    dumped = {name: results[name]["dumped"] for name in DOCUMENTS}
    round_tripped = run_module(dumped)
    parsed = {name: round_tripped[name].get("parsed") for name in DOCUMENTS}
    expected = {name: yaml.safe_load(text) for name, text in DOCUMENTS.items()}

    assert parsed == expected


def test_refused_constructs_are_refused_with_a_readable_message(run_module) -> None:
    results = run_module(REFUSED)

    accepted = [name for name, result in results.items() if result["ok"]]
    assert accepted == []
    # Every message names the line, which is what makes an import error actionable.
    assert all(result["error"].startswith("Line ") for result in results.values())
