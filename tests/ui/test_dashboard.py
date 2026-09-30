"""UI boundary: the real dashboard in a headless browser against the real API.

Requires Chromium: `uv run playwright install chromium`. Skipped (with that hint) if absent.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from asteria.api.app import create_app
from asteria.config import Settings
from asteria.context import load_context

playwright = pytest.importorskip("playwright.sync_api")
from axe_playwright_python.sync_playwright import Axe  # noqa: E402
from playwright.sync_api import Browser, Page, Route, expect  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url(built_data_dir: Path) -> Iterator[str]:
    port = _free_port()
    app = create_app(load_context(Settings(data_dir=built_data_dir)))
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not installed ({exc}); run `uv run playwright install chromium`")
        yield b
        b.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.errors = []  # type: ignore[attr-defined]
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))  # type: ignore[attr-defined]
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)  # type: ignore[attr-defined]
    yield pg
    context.close()


def loaded(page: Page, url: str) -> Page:
    page.goto(url)
    expect(page.locator("#tiles .tile")).to_have_count(3)
    expect(page.locator("main")).to_have_attribute("aria-busy", "false")
    return page


def test_dashboard_loads_every_section_without_errors(page: Page, base_url: str) -> None:
    loaded(page, base_url)
    expect(page.locator("#as-of")).to_have_text("2025-12-31")
    expect(page.locator(".tile .badge")).to_have_count(3)
    expect(page.locator("#trend-chart svg")).to_be_visible()
    expect(page.locator("#signal-chart svg")).to_be_visible()
    expect(page.locator("#scatter-chart svg")).to_be_visible()
    expect(page.locator("#assoc-table tbody tr")).to_have_count(5)
    expect(page.locator("#freshness-table tbody tr")).to_have_count(5)
    assert page.errors == []  # type: ignore[attr-defined]


def test_status_is_never_colour_alone(page: Page, base_url: str) -> None:
    loaded(page, f"{base_url}/?grain=year")
    for badge in page.locator(".tile .badge").all():
        assert badge.locator(".icon").count() == 1
        # DOM text, as a screen reader gets it (CSS may display it in upper case)
        label = badge.locator("span:not(.icon)").text_content()
        assert label in {"Met", "Not met", "Not yet observable", "Too few people"}


def test_filters_scope_the_view_and_are_kept_in_the_url(page: Page, base_url: str) -> None:
    loaded(page, base_url)
    page.select_option("#f-objective", "SENIOR_HIRE_12M")
    page.select_option("#f-country", "GR")
    expect(page.locator("main")).to_have_attribute("aria-busy", "false")
    assert "objective=SENIOR_HIRE_12M" in page.url and "country=GR" in page.url
    expect(page.locator("#trend-chart svg")).to_have_attribute("aria-label", _contains("Greece"))
    page.reload()
    expect(page.locator("#f-country")).to_have_value("GR")


def _contains(text: str) -> object:
    import re

    return re.compile(re.escape(text))


def test_empty_slice_shows_a_message_not_a_blank_chart(page: Page, base_url: str) -> None:
    def empty(route: Route) -> None:
        body = route.fetch().json()
        body["points"] = []
        route.fulfill(json=body)

    page.route("**/api/objectives/*/measures*", empty)
    loaded(page, base_url)
    expect(page.locator("#trend-chart .empty")).to_contain_text("No hires in this slice")


def test_pending_only_slice_explains_why(page: Page, base_url: str) -> None:
    def pending(route: Route) -> None:
        body = route.fetch().json()
        for p in body["points"]:
            p.update(rate=None, ci_low=None, ci_high=None, status="pending", confidence=None)
        route.fulfill(json=body)

    page.route("**/api/objectives/*/measures*", pending)
    loaded(page, base_url)
    expect(page.locator("#trend-chart .empty")).to_contain_text("Not yet observable")


def test_unreachable_api_shows_banner_and_retry_recovers(page: Page, base_url: str) -> None:
    page.route("**/api/**", lambda route: route.abort())
    page.goto(base_url)
    expect(page.locator("#banner")).to_be_visible()
    expect(page.locator("#banner-text")).to_contain_text("Cannot reach the API")
    page.unroute("**/api/**")
    page.click("#banner-retry")
    expect(page.locator("#banner")).to_be_hidden()
    expect(page.locator("#tiles .tile")).to_have_count(3)


def test_data_not_built_tells_the_user_what_to_run(page: Page, base_url: str) -> None:
    detail = "asteria.duckdb not found. Build it with `uv run asteria run`, then reload."
    page.route(
        "**/api/health",
        lambda route: route.fulfill(json={"status": "data_missing", "detail": detail}),
    )
    page.goto(base_url)
    expect(page.locator("#banner")).to_be_visible()
    expect(page.locator("#banner-text")).to_contain_text("uv run asteria run")


def test_charts_are_readable_with_the_keyboard(page: Page, base_url: str) -> None:
    loaded(page, f"{base_url}/?grain=year")
    chart = page.locator("#trend-chart svg")
    chart.focus()
    page.keyboard.press("ArrowLeft")
    live = page.locator("#live")
    expect(live).not_to_be_empty()
    first = live.inner_text()
    page.keyboard.press("ArrowLeft")
    expect(live).not_to_have_text(first)
    expect(page.locator("#trend-chart .tooltip")).to_be_visible()


def test_every_chart_has_a_table_view(page: Page, base_url: str) -> None:
    loaded(page, base_url)
    for fig in ["trend", "signal", "scatter"]:
        page.locator(f"#fig-{fig} details summary").click()
        expect(page.locator(f"#{fig}-table table tbody tr").first).to_be_visible()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_no_serious_accessibility_violations(browser: Browser, base_url: str, scheme: str) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
    pg = context.new_page()
    loaded(pg, base_url)
    for fig in ["trend", "signal", "scatter"]:
        pg.locator(f"#fig-{fig} details summary").click()  # audit the tables too
    results = Axe().run(pg)
    serious = [v for v in results.response["violations"] if v["impact"] in ("serious", "critical")]
    context.close()
    assert serious == [], json.dumps(
        [
            {"id": v["id"], "help": v["help"], "nodes": [n["target"] for n in v["nodes"][:3]]}
            for v in serious
        ],
        indent=2,
    )


def test_key_findings_panel_shows_four_findings(page: Page, base_url: str) -> None:
    loaded(page, base_url)
    cards = page.locator("#findings-grid .finding")
    expect(cards).to_have_count(4)
    expect(cards.nth(0)).to_contain_text("78.6%")
    expect(cards.nth(0).locator(".badge")).to_contain_text("Clearly missed")
    expect(cards.nth(1)).to_contain_text("86.8%")
    expect(cards.nth(3)).to_contain_text("0 of 15")


def test_show_me_sets_the_filters_for_that_finding(page: Page, base_url: str) -> None:
    loaded(page, f"{base_url}/?objective=NEW_HIRE_6M&country=GR&grain=month")
    page.get_by_role("button", name="Show finding 1 on the dashboard").click()
    expect(page.locator("#f-objective")).to_have_value("SENIOR_HIRE_12M")
    expect(page.locator("#f-country")).to_have_value("ALL")
    expect(page.locator("#f-grain")).to_have_value("year")
    assert "objective=SENIOR_HIRE_12M" in page.url
    expect(page.locator("#h-understand")).to_be_focused()
    page.get_by_role("button", name="Show finding 4 on the dashboard").click()
    expect(page.locator("#f-signal")).to_have_value("economic_sentiment")
    expect(page.locator("#h-challenge")).to_be_focused()


def test_small_slices_say_why_they_are_not_judged(page: Page, base_url: str) -> None:
    loaded(page, f"{base_url}/?country=IE&segment=Sales&grain=year")
    senior = page.locator("#tiles .tile", has_text="Senior-hire")
    expect(senior.locator(".badge")).to_contain_text("Too few people")
    expect(senior).to_contain_text("30 are needed")
    expect(senior).to_contain_text("Try Business unit: All.")
