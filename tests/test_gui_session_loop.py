from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _labels(at: AppTest) -> list[str]:
    return [b.label for b in at.button]


def test_gui_full_case_lifecycle():
    """Drives the real gui/app.py (no mocks) through investigate -> start a new
    case -> investigate again -> close the case file, using Streamlit's own
    AppTest harness. Runs under the autouse socket-blocking fixture, so every
    agent's real network call fails and is caught internally (returning no
    findings) -- profile_synthesizer.synthesize() degrades to an empty
    Briefing rather than crashing, which is exactly the path this test
    exercises: the GUI's session lifecycle, not agent behavior (covered
    elsewhere).

    Note: st.rerun() ends the script early. A rerun triggered from inside the
    sidebar block (Start a new case / Close the case file) needs two more
    at.run() calls to settle the widget tree; one triggered later in the main
    panel (after a successful investigation) needs only one. A real browser
    client would show only the final settled state either way.
    """
    at = AppTest.from_file("gui/app.py", default_timeout=60)
    at.run()
    assert not at.exception
    assert _labels(at) == ["Investigate"]
    assert at.session_state["session_id"] is None

    at.text_input[1].input("Alice Example")  # "Full name"
    at.button[0].click()
    at.run()
    assert not at.exception
    assert at.session_state["session_id"] is not None
    assert at.session_state["briefing"] is not None
    first_sid = at.session_state["session_id"]
    assert set(_labels(at)) == {"Start a new case", "Close the case file"}
    assert len(at.tabs) == 5

    [b for b in at.button if b.label == "Start a new case"][0].click()
    at.run()
    at.run()  # sidebar-triggered rerun needs a second call to settle
    assert not at.exception
    assert at.session_state["session_id"] is None
    assert at.session_state["briefing"] is None
    assert _labels(at) == ["Investigate"]

    at.text_input[1].input("Bob Example")
    at.button[0].click()
    at.run()
    assert at.session_state["session_id"] is not None
    assert at.session_state["session_id"] != first_sid

    [b for b in at.button if b.label == "Close the case file"][0].click()
    at.run()
    # The success message renders only on the run that processes the click
    # itself (st.button() is only truthy that once) -- check it here, before
    # the extra settling run below would make it disappear again.
    assert not at.exception
    assert at.session_state["session_id"] is None
    assert at.session_state["briefing"] is None
    assert any("Case closed. Session data destroyed." in s.value for s in at.success)

    at.run()  # sidebar-triggered rerun needs a second call to settle the widget tree
    assert _labels(at) == ["Investigate"]


def test_gui_investigate_button_hidden_while_case_open():
    """Regression: the search form must not render while a case is already
    open, so a second submission can never leak an un-purged session."""
    at = AppTest.from_file("gui/app.py", default_timeout=60)
    at.run()
    at.text_input[1].input("Carol Example")
    at.button[0].click()
    at.run()

    assert "Investigate" not in _labels(at)
