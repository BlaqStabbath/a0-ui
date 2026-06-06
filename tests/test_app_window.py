from unittest import mock


def test_main_serves_wrapper_from_local_http_server_not_file_origin():
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
    assert kwargs["url"].endswith("a0_ui/web/index.html")
    assert not kwargs["url"].startswith("file://")

    start.assert_called_once()
    start_kwargs = start.call_args.kwargs
    assert start_kwargs["private_mode"] is False
    assert start_kwargs["storage_path"].endswith(".local/share/a0-ui/webview")
