"""Tiny route table used as a web-app style challenge."""

from __future__ import annotations


ROUTES = {
    "/": "home",
    "/health": "ok",
}


def handle_request(path: str) -> str:
    return ROUTES.get(path, "404")
