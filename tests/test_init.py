"""Tests for safe mode integration."""
from unittest import mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from aiohttp.web_request import Request
from importlib import import_module
from pytest_homeassistant_custom_component.common import load_fixture
from pytest_socket import enable_socket

w1k_Portal = import_module('custom_components.w1000-energy-monitor').w1k_Portal


def resp_file(name):
    async def handler(_):
        return web.Response(text=load_fixture(name))

    return handler


testdata = [
    ("good", 14293.749, 14326.234),
    ("missing_start", None, 14172.722),
    ("missing_last", None, None),
]


@pytest.mark.parametrize("name,first,last", testdata)
async def test_w1k_api(name, first, last, aiohttp_client, hass):
    """Test entry setup and unload."""
    enable_socket()

    async def profile_data(_: Request):
        return web.Response(
            headers={"Content-Type": "application/json"},
            text=load_fixture("import_" + name + ".json"),
        )

    app = web.Application()
    app.router.add_get("/Account/Login", resp_file("login.html"))
    app.router.add_post("/Account/Login", resp_file("loginPost.html"))
    app.router.add_get("/ProfileData/ProfileData", profile_data)

    mock_client: TestClient = await aiohttp_client(app)
    mock_recorder = mock.Mock()

    url = "http://127.0.0.1:" + str(mock_client.server.port)
    print(w1k_Portal)
    portal = w1k_Portal(hass, "user1", "pass2", url, "import")

    # replace mocks
    hass.data["recorder_instance"] = mock_recorder
    portal.session = mock_client.session

    await portal.update()
    assert last == portal.get_data("import").get("state")
    if first is None:
        mock_recorder.async_import_statistics.assert_not_called()
    else:
        for stat in mock_recorder.async_import_statistics.call_args.args[1]:
            assert stat.get("state") >= first
            assert stat.get("state") <= last
