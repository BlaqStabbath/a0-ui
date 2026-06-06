from unittest import mock


def test_main_loads_wrapper_from_file_url():
    from a0_ui import app

    fake_window = mock.MagicMock()

    with (
        mock.patch.object(app, "_parse_args", return_value=mock.MagicMock(debug=False)),
        mock.patch.object(app, "_start_servers"),
        mock.patch.object(app.webview, "create_window", return_value=fake_window) as create_window,
        mock.patch.object(app.webview, "start") as start,
    ):
        app.main()

    kwargs = create_window.call_args.kwargs
    assert kwargs["url"].startswith("file://")
    assert kwargs["url"].endswith("a0_ui/web/index.html")
    start.assert_called_once_with()
    assert app.webview_settings["ALLOW_FILE_URLS"] is True
