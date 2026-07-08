from pathlib import Path

from release_dispatcher.config import load_endpoints


def test_repository_endpoints_file_parses():
    endpoints = load_endpoints(Path("endpoints.yml"))

    assert [(endpoint.hook, endpoint.name) for endpoint in endpoints] == [("core_ready", "python")]
