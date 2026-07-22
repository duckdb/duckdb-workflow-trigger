from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from release_dispatcher.config import Endpoint
from release_dispatcher.models import ReleaseState


@dataclass(frozen=True)
class DispatchRequest:
    endpoint: Endpoint
    url: str
    body: dict[str, Any]


class GitHubDispatcher:
    def __init__(
        self,
        *,
        token: str,
        dry_run: bool = False,
        api_base: str = "https://api.github.com",
        session: requests.Session | None = None,
    ) -> None:
        self.token = token
        self.dry_run = dry_run
        self.api_base = api_base.rstrip("/")
        self.session = session or requests.Session()

    def build_request(self, endpoint: Endpoint, state: ReleaseState) -> DispatchRequest:
        url = (
            f"{self.api_base}/repos/{endpoint.owner}/{endpoint.repo}"
            f"/actions/workflows/{endpoint.workflow}/dispatches"
        )
        body = {
            "ref": endpoint.ref,
            "inputs": endpoint.render_inputs(state),
        }
        return DispatchRequest(endpoint=endpoint, url=url, body=body)

    def dispatch(self, endpoint: Endpoint, state: ReleaseState) -> DispatchRequest:
        request = self.build_request(endpoint, state)
        if self.dry_run:
            print(f"DRY RUN: would dispatch {endpoint.name} to {request.url}")
            print(json.dumps(request.body, indent=2, sort_keys=True))
            return request

        response = self.session.post(
            request.url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=request.body,
            timeout=30,
        )
        response.raise_for_status()
        return request
