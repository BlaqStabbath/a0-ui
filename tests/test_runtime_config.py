"""Tests for runtime.config."""
import sys
from unittest import mock

from a0_ui.runtime.config import load_config


def test_load_config_defaults_entry_cmd_to_a0():
    with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(sys, "platform", "linux"):
        config = load_config()

    assert config.entry_cmd == "a0"
    assert config.platform == "linux"


def test_load_config_reads_a0_cli_cmd_env_var():
    with mock.patch.dict("os.environ", {"A0_CLI_CMD": "python -m a0"}, clear=True):
        config = load_config()

    assert config.entry_cmd == "python -m a0"


def test_load_config_reads_a0_webui_url_env_var():
    with mock.patch.dict("os.environ", {"A0_WEBUI_URL": "http://example:9999"}, clear=True):
        config = load_config()

    assert config.webui_url == "http://example:9999"


def test_load_config_reads_a0_container_env_var():
    with mock.patch.dict("os.environ", {"A0_CONTAINER": "my-container"}, clear=True):
        config = load_config()

    assert config.container == "my-container"


def test_load_config_maps_sys_platform_to_canonical_strings():
    with mock.patch.dict("os.environ", {}, clear=True):
        with mock.patch.object(sys, "platform", "linux"):
            assert load_config().platform == "linux"
        with mock.patch.object(sys, "platform", "darwin"):
            assert load_config().platform == "darwin"
        with mock.patch.object(sys, "platform", "win32"):
            assert load_config().platform == "win32"


def test_load_config_passes_through_unknown_platform():
    with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(sys, "platform", "freebsd"):
        assert load_config().platform == "freebsd"


def test_load_config_defaults_debug_to_false():
    with mock.patch.dict("os.environ", {}, clear=True):
        assert load_config().debug is False


def test_load_config_reads_a0_debug_env_var():
    with mock.patch.dict("os.environ", {"A0_DEBUG": "1"}, clear=True):
        assert load_config().debug is True
