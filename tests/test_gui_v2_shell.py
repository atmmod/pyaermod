"""Tier T0 tests for the GUI shell's session bookkeeping (``gui_v2.app``).

Which session a page gets, when a session counts as in use and when a
client counts as deleted are plain functions of the tab's storage and
the client, so they are tested here without a NiceGUI server. The clients
are stand-ins shaped like NiceGUI 3.0's, which have no public
``is_deleted``: the package allows NiceGUI 3.0 and the in-process GUI
tests (``test_gui_v2_smoke.py``) need 3.4, so this file is what the
minimum-dependencies CI leg runs.
"""

from __future__ import annotations

import pytest

from pyaermod.gui_v2 import app as app_module
from pyaermod.gui_v2.session import Session


class _Client:
    """A NiceGUI 3.0 client as the shell sees it: a tab id and delete handlers."""

    def __init__(self, tab_id):
        self.tab_id = tab_id
        self._deleted = False
        self.handlers = []

    def on_delete(self, handler):
        self.handlers.append(handler)

    def delete(self):
        self._deleted = True
        for handler in self.handlers:
            handler()


@pytest.fixture(autouse=True)
def _no_owners(monkeypatch):
    monkeypatch.setattr(app_module, "_OWNERS", {})


def _build_page(client, tab):
    """What index() does with the session once the socket is connected."""
    session = app_module._session_for(client, tab)
    app_module._claim(session, client)
    app_module._keep_in_use(session, client, tab)
    return session


def test_a_new_tab_gets_a_new_session():
    tab: dict = {}
    s = _build_page(_Client("A"), tab)
    assert tab["session"] is s and s.tab_id == "A"


def test_a_reload_gets_the_same_session():
    tab: dict = {}
    first, reload = _Client("A"), _Client("A")
    s = _build_page(first, tab)
    assert _build_page(reload, tab) is s


def test_duplicated_tab_forks_while_the_original_lives():
    original, duplicate = _Client("A"), _Client("B")
    tab_a: dict = {}
    s = _build_page(original, tab_a)
    tab_b = dict(tab_a)                         # NiceGUI copies the storage
    forked = _build_page(duplicate, tab_b)
    assert forked is not s and forked.tab_id == "B" and tab_b["session"] is forked
    assert tab_a["session"] is s and s.tab_id == "A"


def test_a_session_whose_pages_are_all_deleted_is_adopted():
    original, later = _Client("A"), _Client("B")
    tab: dict = {}
    s = _build_page(original, tab)
    original.delete()
    assert id(s) not in app_module._OWNERS
    assert _build_page(later, dict(tab)) is s
    assert s.tab_id == "B"


def test_a_deleted_owner_does_not_count_before_its_handlers_run():
    # Between NiceGUI marking a client deleted and running its handlers.
    original, later = _Client("A"), _Client("B")
    tab: dict = {}
    s = _build_page(original, tab)
    original._deleted = True
    assert _build_page(later, dict(tab)) is s


@pytest.mark.parametrize("client, deleted", [
    (type("New", (), {"is_deleted": True})(), True),       # NiceGUI >= 3.13
    (type("New", (), {"is_deleted": False})(), False),
    (type("Old", (), {"_deleted": True})(), True),         # NiceGUI 3.0 - 3.12
    (type("Old", (), {"_deleted": False})(), False),
    (object(), False),
])
def test_is_deleted_works_on_every_supported_nicegui(client, deleted):
    assert app_module._is_deleted(client) is deleted


def test_using_the_session_refreshes_the_tab_storage(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(app_module.time, "time", lambda: clock["now"])
    tab: dict = {}
    client = _Client("A")
    s = _build_page(client, tab)
    assert tab[app_module.LAST_USED_KEY] == 1000.0      # building the page counts
    clock["now"] += 10
    s.set_control(title_one="edited")
    assert tab[app_module.LAST_USED_KEY] == 1000.0      # at most once a minute
    clock["now"] += app_module._TOUCH_INTERVAL_S
    s.set_control(title_one="edited again")
    assert tab[app_module.LAST_USED_KEY] == clock["now"]
    client.delete()                                     # the page is gone: no more writes
    clock["now"] += 10 * app_module._TOUCH_INTERVAL_S
    s.new()
    assert tab[app_module.LAST_USED_KEY] == 1000.0 + 10 + app_module._TOUCH_INTERVAL_S


def test_the_page_leaves_no_observers_behind():
    s = Session()
    tab: dict = {"session": s}
    s.tab_id = "A"
    clients = [_Client("A") for _ in range(3)]
    for c in clients:
        _build_page(c, tab)
    assert len(s._observers) == 3
    for c in clients:
        c.delete()
    assert s._observers == [] and app_module._OWNERS == {}


def _raised_in(filename: str, exc: BaseException) -> BaseException:
    """``exc`` with a traceback whose innermost frame is in ``filename``."""
    try:
        exec(compile("raise exc", filename, "exec"), {"exc": exc})
    except BaseException as caught:
        return caught
    raise AssertionError("not raised")  # pragma: no cover


def _record(exc):
    import logging
    return logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                             "Exception in ASGI application\n", None,
                             (type(exc), exc, exc.__traceback__) if exc else None)


UPLOAD_PY = "/site-packages/nicegui/elements/upload.py"


def test_a_cancelled_upload_is_dropped_from_uvicorns_log():
    """Closing the Open dialog mid-upload is not an error (NiceGUI 3.17)."""
    from starlette.requests import ClientDisconnect
    keep = app_module._UPLOAD_FILTER.filter
    cancelled = _raised_in(UPLOAD_PY, ClientDisconnect())
    assert keep(_record(cancelled)) is False
    # Starlette's middleware wraps it in an exception group.
    assert keep(_record(BaseExceptionGroup("unhandled errors in a TaskGroup", [cancelled]))) is False


def test_every_other_error_record_is_kept():
    from starlette.requests import ClientDisconnect
    keep = app_module._UPLOAD_FILTER.filter
    assert keep(_record(None))
    assert keep(_record(_raised_in("/site-packages/nicegui/page.py", ClientDisconnect())))
    assert keep(_record(_raised_in(UPLOAD_PY, AttributeError("no attribute 'name'"))))
    two = BaseExceptionGroup("two", [_raised_in(UPLOAD_PY, ClientDisconnect()), ValueError("x")])
    assert keep(_record(two))


def test_the_filter_is_installed_once(monkeypatch):
    import logging
    uvicorn_error = logging.getLogger("uvicorn.error")
    monkeypatch.setattr(uvicorn_error, "filters", [])
    app_module._quiet_cancelled_uploads()
    app_module._quiet_cancelled_uploads()
    assert uvicorn_error.filters == [app_module._UPLOAD_FILTER]
