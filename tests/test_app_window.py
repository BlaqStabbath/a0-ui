from unittest import mock


def test_main_loads_wrapper_from_local_http_server():
    from a0_ui import app

    fake_window = mock.MagicMock()

    with (
        mock.patch.object(app, "_parse_args", return_value=mock.MagicMock(debug=False)),
        mock.patch.object(app, "_start_servers"),
        mock.patch.object(app, "_webview_storage_path", return_value="/tmp/a0-ui-test-webview"),
        mock.patch.object(app, "_free_port", return_value=43123),
        mock.patch.object(app.os, "makedirs") as makedirs,
        mock.patch.object(app.webview, "create_window", return_value=fake_window) as create_window,
        mock.patch.object(app.webview, "start") as start,
    ):
        app.main()

    kwargs = create_window.call_args.kwargs
    assert kwargs["url"].endswith("a0_ui/web/index.html")
    assert not kwargs["url"].startswith("file://")
    makedirs.assert_called_once_with("/tmp/a0-ui-test-webview", exist_ok=True)
    start.assert_called_once_with(
        private_mode=False,
        storage_path="/tmp/a0-ui-test-webview",
        http_server=True,
        http_port=43123,
    )
    assert app.webview_settings["ALLOW_FILE_URLS"] is True


def test_webview_storage_path_uses_xdg_data_home(monkeypatch):
    from a0_ui import app

    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")

    assert app._webview_storage_path() == "/tmp/xdg-data/a0-ui/webview"
