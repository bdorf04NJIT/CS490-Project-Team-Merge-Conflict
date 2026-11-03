"""Short Google Maps link checks never contact Google during automated tests."""

from urllib.request import Request

import pytest

from app.adapters.short_maps_links import (
    ShortMapsLinkError,
    _GoogleRedirectsOnly,
    is_short_maps_link,
    resolve_short_maps_link,
)

SHORT = "https://maps.app.goo.gl/AbCdEfGH"
LONG = "https://www.google.com/maps/place/Cafe/data=!4m2!1s0x89c259:0xa4969e07"


class FakeResponse:
    def __init__(self, url):
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, url, calls):
        self.url = url
        self.calls = calls

    def open(self, request, timeout):
        self.calls.append((request.get_method(), timeout))
        return FakeResponse(self.url)


def test_real_google_short_link_pattern():
    assert is_short_maps_link(SHORT)
    assert is_short_maps_link("https://goo.gl/maps/AbCdEfGH")
    assert not is_short_maps_link(LONG)
    assert not is_short_maps_link("https://maps.app.goo.gl.attacker.invalid/AbCdEfGH")
    assert not is_short_maps_link("http://maps.app.goo.gl/AbCdEfGH")


def test_long_maps_link_does_not_make_http_request():
    assert resolve_short_maps_link(LONG, opener_factory=lambda: pytest.fail("network call")) == LONG


def test_short_link_resolves_using_head():
    calls = []
    result = resolve_short_maps_link(SHORT, opener_factory=lambda: FakeOpener(LONG, calls))
    assert result == LONG
    assert calls == [("HEAD", 8)]


def test_head_not_resolved_falls_back_to_get():
    calls = []
    counter = iter([SHORT, LONG])
    result = resolve_short_maps_link(SHORT, opener_factory=lambda: FakeOpener(next(counter), calls))
    assert result == LONG
    assert calls == [("HEAD", 8), ("GET", 8)]


def test_failed_expansion_reports_actionable_error_without_network_leak():
    with pytest.raises(ShortMapsLinkError, match="copy the full Google Maps place URL"):
        resolve_short_maps_link(SHORT, opener_factory=lambda: FakeOpener(SHORT, []))


@pytest.mark.parametrize(
    "url",
    [
        "http://www.google.com/maps/place/Cafe",
        "https://www.google.com.evil.invalid/maps/place/Cafe",
        "https://127.0.0.1/internal",
        "https://www.google.com:444/maps/place/Cafe",
        "https://user@www.google.com/maps/place/Cafe",
        "https://evil.invalid",
    ],
)
def test_redirects_to_other_hosts_or_nonstandard_authorities_are_blocked(url):
    handler = _GoogleRedirectsOnly()
    request = Request(SHORT, method="HEAD")
    with pytest.raises(ShortMapsLinkError):
        handler.redirect_request(request, None, 302, "Found", {}, url)


def test_redirect_limit_blocks_loops():
    handler = _GoogleRedirectsOnly()
    request = Request(SHORT, method="HEAD")
    for _ in range(5):
        request = handler.redirect_request(request, None, 302, "Found", {}, SHORT)
    with pytest.raises(ShortMapsLinkError):
        handler.redirect_request(request, None, 302, "Found", {}, SHORT)
