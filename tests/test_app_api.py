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


def test_check_a0_ready_reports_running_container_and_available_webui():
    from a0_ui.app import check_a0_ready

    inspect_result = mock.MagicMock(returncode=0, stdout="true\n", stderr="")
    response = mock.MagicMock()
    response.status = 200
    response.__enter__.return_value = response

    with (
        mock.patch.dict(
            "os.environ",
            {
                "A0_CONTAINER": "agent-zero-test",
                "A0_WEBUI_URL": "http://127.0.0.1:5080",
            },
            clear=True,
        ),
        mock.patch("shutil.which", return_value="/usr/bin/docker"),
        mock.patch("subprocess.run", return_value=inspect_result) as run,
        mock.patch("urllib.request.urlopen", return_value=response) as urlopen,
    ):
        result = check_a0_ready()

    assert result == {"ok": True, "running": True, "webui_ready": True}
    run.assert_called_once_with(
        ["docker", "inspect", "-f", "{{.State.Running}}", "agent-zero-test"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert urlopen.call_args.args[0].full_url == "http://127.0.0.1:5080"


def test_check_a0_ready_does_not_report_ready_until_docker_is_running():
    from a0_ui.app import check_a0_ready

    inspect_result = mock.MagicMock(returncode=0, stdout="false\n", stderr="")

    with (
        mock.patch.dict("os.environ", {"A0_CONTAINER": "agent-zero-test"}, clear=True),
        mock.patch("shutil.which", return_value="/usr/bin/docker"),
        mock.patch("subprocess.run", return_value=inspect_result),
        mock.patch("urllib.request.urlopen") as urlopen,
    ):
        result = check_a0_ready()

    assert result["ok"] is False
    assert result["running"] is False
    assert result["webui_ready"] is False
    urlopen.assert_not_called()


def test_restart_cli_restarts_terminal_bridge():
    from a0_ui import app

    bridge = mock.MagicMock()
    original = app._terminal_bridge[0]
    app._terminal_bridge[0] = bridge
    try:
        result = app.restart_cli()
    finally:
        app._terminal_bridge[0] = original

    assert result == {"ok": True}
    bridge.restart.assert_called_once_with()


def test_get_logs_includes_wrapper_events_when_docker_is_unavailable():
    from a0_ui import app

    with app._wrapper_events_lock:
        app._wrapper_events.clear()
    app._record_event("test wrapper event")

    with mock.patch("shutil.which", return_value=None):
        logs = app.get_logs()

    assert "=== wrapper events ===" in logs
    assert "test wrapper event" in logs
    assert "=== docker logs ===" in logs
    assert "docker not found on PATH" in logs


def test_get_logs_mixes_wrapper_events_and_container_logs():
    from a0_ui import app

    with app._wrapper_events_lock:
        app._wrapper_events.clear()
    app._record_event("restart requested")

    docker_logs = mock.MagicMock(returncode=0, stdout="container stdout\n", stderr="container stderr\n")
    docker_ls = mock.MagicMock(returncode=0, stdout="run.html\n", stderr="")
    docker_tail = mock.MagicMock(returncode=0, stdout="html log tail\n", stderr="")

    with (
        mock.patch.dict("os.environ", {"A0_CONTAINER": "agent-zero-test"}, clear=True),
        mock.patch("shutil.which", return_value="/usr/bin/docker"),
        mock.patch("subprocess.run", side_effect=[docker_logs, docker_ls, docker_tail]),
    ):
        logs = app.get_logs()

    assert logs.index("=== wrapper events ===") < logs.index("=== docker logs")
    assert "restart requested" in logs
    assert "container stdout" in logs
    assert "container stderr" in logs
    assert "=== run.html (last 40) ===" in logs
    assert "html log tail" in logs
