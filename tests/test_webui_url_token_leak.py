import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = REPO_ROOT / "webui"


def _read(relative: str) -> str:
    """Read a file under the repo root as text."""
    return (REPO_ROOT / relative).read_text()


class TestWebuiGetTokenIgnoresUrl:
    """webui/js/api.js getToken must resolve the token only from localStorage."""

    def test_get_token_region_has_no_url_read(self) -> None:
        content = _read("webui/js/api.js")
        start = content.index("export function getToken")
        next_export = content.index("export ", start + 1)
        region = content[start:next_export]
        assert "URLSearchParams" not in region
        assert "location.search" not in region
        assert "params.get" not in region

    def test_get_token_still_reads_localstorage(self) -> None:
        content = _read("webui/js/api.js")
        start = content.index("export function getToken")
        next_export = content.index("export ", start + 1)
        region = content[start:next_export]
        assert "localStorage.getItem" in region
        assert "starfarer_game_token" in region


class TestWebuiMainDoesNotIngestUrlToken:
    """webui/js/main.js must not derive the token from the URL."""

    def test_main_never_reads_token_query_param(self) -> None:
        content = _read("webui/js/main.js")
        assert re.search(r"params\.get\(\s*['\"]token['\"]\s*\)", content) is None

    def test_main_does_not_import_set_token(self) -> None:
        content = _read("webui/js/main.js")
        import_line = next(
            line for line in content.splitlines() if "from \"./api.js\"" in line
        )
        assert "setToken" not in import_line

    def test_main_strips_token_query_param(self) -> None:
        content = _read("webui/js/main.js")
        assert "history.replaceState" in content
        assert re.search(r"searchParams\.delete\(\s*['\"]token['\"]\s*\)", content) is not None

    def test_main_strip_url_token_is_exported(self) -> None:
        content = _read("webui/js/main.js")
        assert "export function stripUrlToken" in content
        assert content.index("stripUrlToken();") < content.index(
            "new URLSearchParams(window.location.search)"
        )


class TestReadmeNoLongerInstructsUrlToken:
    """README must not tell users to open the webui with a token in the URL."""

    def test_readme_omits_game_and_token_url(self) -> None:
        readme = _read("README.md")
        assert "?game=<game_id>&token=" not in readme
        assert "?game=<id>&token=" not in readme

    def test_readme_instructs_localstorage_token(self) -> None:
        readme = _read("README.md")
        assert "starfarer_game_token" in readme
        assert "localStorage.setItem" in readme
