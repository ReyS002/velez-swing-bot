from collections import deque
from datetime import date

from bot.calendar_feeds import CalendarFeedService


class MissingBroker:
    def is_configured(self):
        return False


class Response:
    def __init__(self, text="", status_code=200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}


def service():
    return CalendarFeedService(
        MissingBroker(), {"timezone": "America/New_York"}, deque()
    )


def bls_feed():
    return {
        "name": "BLS",
        "url": "https://www.bls.gov/schedule/news_release/bls.ics",
        "kind": "ics",
    }


def test_shared_bls_cache_is_downloaded_once_and_reused(monkeypatch, tmp_path):
    monkeypatch.setenv("BLS_SHARED_CACHE_FILE", str(tmp_path / "bls-calendar.json"))
    monkeypatch.setenv("BLS_SHARED_CACHE_SECONDS", "43200")
    monkeypatch.setenv("BLS_FETCH_RETRY_DELAYS_SECONDS", "0")
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append(url)
        return Response(
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "DTSTART:20260911T083000\n"
            "SUMMARY:Consumer Price Index\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n",
            headers={"ETag": '"calendar-v1"'},
        )

    monkeypatch.setattr("bot.calendar_feeds.requests.get", fake_get)
    first_items, first_source = service()._fetch_macro_feed(
        bls_feed(), date(2026, 9, 1), date(2026, 10, 15)
    )
    second_items, second_source = service()._fetch_macro_feed(
        bls_feed(), date(2026, 9, 1), date(2026, 10, 15)
    )

    assert calls == [bls_feed()["url"]]
    assert first_items == second_items
    assert first_items[0]["title"] == "Consumer Price Index"
    assert first_source["shared"] is True
    assert first_source["cache_status"] == "refreshed"
    assert second_source["cache_status"] == "fresh"
    assert second_source["fallback"] is False


def test_shared_bls_cache_retries_then_uses_monthly_html_fallback(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("BLS_SHARED_CACHE_FILE", str(tmp_path / "bls-calendar.json"))
    monkeypatch.setenv("BLS_SHARED_CACHE_SECONDS", "43200")
    monkeypatch.setenv("BLS_FETCH_RETRY_DELAYS_SECONDS", "0,0")
    calls = []

    def fake_get(url, timeout=None, headers=None):
        calls.append(url)
        if url.endswith("bls.ics"):
            return Response("<html>Access Denied</html>", status_code=403)
        return Response(
            "<html><body><table><tr>"
            "<td>Friday, September 11, 2026</td>"
            "<td>08:30 AM</td>"
            "<td>Consumer Price Index for August 2026</td>"
            "</tr></table></body></html>"
        )

    monkeypatch.setattr("bot.calendar_feeds.requests.get", fake_get)
    items, source = service()._fetch_macro_feed(
        bls_feed(), date(2026, 9, 1), date(2026, 9, 30)
    )

    assert calls.count(bls_feed()["url"]) == 2
    assert calls[-1].endswith("/2026/09_sched_list.htm")
    assert items[0]["title"] == "Consumer Price Index for August 2026"
    assert items[0]["time"] == "08:30 AM"
    assert source["ok"] is True
    assert source["shared"] is True
    assert source["fallback"] is True
    assert source["cache_status"] == "fallback"

    before = list(calls)
    cached_items, cached_source = service()._fetch_macro_feed(
        bls_feed(), date(2026, 9, 1), date(2026, 9, 30)
    )
    assert calls == before
    assert cached_items == items
    assert cached_source["cache_status"] == "fresh"
