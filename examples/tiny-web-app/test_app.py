from app import handle_request


def test_existing_routes() -> None:
    assert handle_request("/") == "home"
    assert handle_request("/health") == "ok"


def test_about_route_challenge() -> None:
    assert handle_request("/about") == "about tiny app"
