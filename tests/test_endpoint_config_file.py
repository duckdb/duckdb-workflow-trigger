from pathlib import Path

from release_dispatcher.config import load_endpoints


def test_repository_endpoints_file_includes_required_hooks():
    endpoints = load_endpoints(Path("endpoints.yml"))

    hooks = {endpoint.hook for endpoint in endpoints}

    assert {"core_ready", "client_ready"} <= hooks
