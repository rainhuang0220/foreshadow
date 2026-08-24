from __future__ import annotations

import hashlib
import json

from foreshadow.clock import Clock


def graphql_cache_key(document: str, variables: dict) -> str:
    blob = document + json.dumps(
        variables, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def rest_cache_key(url: str, params: dict | None = None) -> str:
    blob = url + json.dumps(
        params or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class HttpCache:
    """Same-day GraphQL body cache and REST ETag store."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or Clock()
        self._graphql: dict[tuple[str, str], dict] = {}
        self._etags: dict[str, str] = {}
        self._bodies: dict[str, bytes] = {}

    def get_graphql(self, key: str) -> dict | None:
        return self._graphql.get((self._clock.today().isoformat(), key))

    def put_graphql(self, key: str, body: dict) -> None:
        self._graphql[(self._clock.today().isoformat(), key)] = body

    def get_etag(self, key: str) -> str | None:
        return self._etags.get(key)

    def get_rest_body(self, key: str) -> bytes | None:
        return self._bodies.get(key)

    def put_rest(self, key: str, etag: str, body: bytes) -> None:
        self._etags[key] = etag
        self._bodies[key] = body
