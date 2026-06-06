from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "a0_ui" / "web" / "index.html").read_text()


def test_toolbar_panel_uses_single_row_with_tabs_left_and_actions_right():
    assert '<div id="toolbar-panel">' in HTML
    assert '<div id="tabs">' in HTML
    assert '<div id="toolbar-actions">' in HTML
    assert HTML.index('<div id="tabs">') < HTML.index('<div id="toolbar-actions">')
    assert "#toolbar-panel" in HTML
    assert "justify-content:space-between" in HTML


def test_redundant_navigation_toolbar_buttons_removed_from_dom_and_handlers():
    assert "btn-logs" not in HTML
    assert "btn-cli" not in HTML
    assert ">View Logs<" not in HTML
    assert ">A0 CLI<" not in HTML


def test_primary_actions_match_slice_004():
    assert 'id="btn-refresh">Refresh</button>' in HTML
    assert 'id="btn-restart">Restart a0</button>' in HTML
    assert 'id="btn-open-browser">Open in browser</button>' in HTML
    assert 'id="status-dot"' in HTML


def test_slice_004_palette_and_active_tab_treatment_are_present():
    assert "--bg:#0F0B1E" in HTML
    assert "--accent:#7C3AED" in HTML
    assert "--secondary:#3B82F6" in HTML
    assert "--panel-hi:#1E1B4B" in HTML
    assert "linear-gradient(135deg,var(--panel-hi),var(--bg))" in HTML
    assert ".tab.active" in HTML
    assert "border-bottom:2px solid var(--accent)" in HTML
    assert "background:var(--active-fill)" in HTML


def test_terminal_pane_has_zero_padding_and_no_border():
    assert "#cli-pane{background:var(--bg);padding:0;border:0}" in HTML
    assert "#cli-pane .xterm{height:100%;width:100%;border:0}" in HTML
    assert "#cli-pane .xterm-screen{height:100%;width:100%;border:0}" in HTML
