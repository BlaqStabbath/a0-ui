from unittest import mock


def test_open_webui_opens_configured_webui_url():
    from a0_ui.app import open_webui

    with (
        mock.patch.dict("os.environ", {"A0_WEBUI_URL": "http://example.test:5080"}, clear=True),
        mock.patch("webbrowser.open", return_value=True) as open_browser,
    ):
        result = open_webui()

    assert result == {"ok": True}
    open_browser.assert_called_once_with("http://example.test:5080")
