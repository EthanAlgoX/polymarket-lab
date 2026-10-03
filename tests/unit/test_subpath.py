from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.paths.extend(
            value for key, value in attrs if key in {"href", "src", "action"} and value and value[0] == "/"
        )


@pytest.mark.parametrize("prefix", ["", "/polymarket-lab"])
@pytest.mark.parametrize(
    "route", ["/", "/monitor", "/opportunities", "/markets/1", "/paper-trades", "/history", "/settings", "/logs"]
)
def test_reverse_proxy_prefix_covers_every_page_and_static_asset(prefix: str, route: str) -> None:
    # Proxies strip the external prefix before forwarding a request. The ASGI
    # root_path preserves that prefix in all template links and JS API calls.
    with TestClient(app, root_path=prefix) as client:
        response = client.get(prefix + route)
        assert response.status_code == 200
        assert f'<meta name="app-root-path" content="{prefix}">' in response.text
        links = LocalLinks()
        links.feed(response.text)
        assert len(links.paths) >= 18
        assert all(path.startswith(prefix + "/") for path in links.paths)
        assert f'href="{prefix}/#markets"' in response.text
        assert f'href="{prefix}/settings#translation-api"' in response.text
        for path in links.paths:
            if path.startswith(prefix + "/static/"):
                assert client.get(path).status_code == 200


def test_cli_restores_prefix_for_stripped_proxy_requests(tmp_path: Path, unused_tcp_port: int) -> None:
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "app").symlink_to(root / "app", target_is_directory=True)
    environment = {key: value for key, value in os.environ.items() if "DEEPSEEK" not in key.upper()}
    environment.update(
        {
            "PYTHONPATH": str(root),
            "PMS_ROOT_PATH": "/polymarket-lab",
            "PMS_HOST": "127.0.0.1",
            "PMS_PORT": str(unused_tcp_port),
            "PMS_ENABLE_LIVE_SCANNER": "false",
            "PMS_DATABASE_URL": f"sqlite:///{tmp_path / 'proxy.db'}",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "app"],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{unused_tcp_port}", timeout=0.5) as client:
            for _attempt in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert process.poll() is None, "Server exited before becoming ready"
                time.sleep(0.05)
            else:
                pytest.fail("Server did not start within five seconds")
            # These are the paths the upstream receives after Nginx strips
            # /polymarket-lab/. Uvicorn adds root_path back to the ASGI scope.
            response = client.get("/settings")
            assert response.status_code == 200
            assert 'href="/polymarket-lab/opportunities"' in response.text
            assert client.get("/static/js/site-paths.js").status_code == 200
            assert client.get("/api/research").status_code == 200
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.parametrize(
    ("value", "expected"), [("", ""), ("/", ""), ("/polymarket-lab/", "/polymarket-lab"), ("/apps/lab", "/apps/lab")]
)
def test_root_path_normalizes_supported_prefixes(value: str, expected: str) -> None:
    assert Settings(root_path=value).root_path == expected


@pytest.mark.parametrize("value", ["relative", "//other.example", "/a//b", "/../x", "/x?next=y", '/x"y'])
def test_root_path_rejects_ambiguous_or_unsafe_prefixes(value: str) -> None:
    with pytest.raises(ValueError, match="Root path"):
        Settings(root_path=value)


def test_frontend_fetches_and_dynamic_links_keep_the_deployment_prefix() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for frontend subpath checks")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [node, str(root / "tests/frontend/subpath.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
