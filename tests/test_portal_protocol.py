"""Real D-Bus client against a private, non-injecting permission portal fixture."""
import asyncio
import os
import threading

import pytest

pytestmark = [pytest.mark.portal, pytest.mark.skipif(os.environ.get("PROFILE_TYPER_TEST_PORTAL") != "1", reason="requires private dbus-run-session")]


@pytest.fixture
def portal_server():
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    from profile_typer.platforms.wayland import DESTINATION, INTERFACE, PATH

    class Server:
        def __init__(self):
            self.loop = asyncio.new_event_loop()
            self.calls = []
            self.keys = []
            self.deny = False
            self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
            self.thread.start()
            asyncio.run_coroutine_threadsafe(self.start(), self.loop).result(3)

        async def start(self):
            self.bus = await MessageBus().connect()
            await self.bus.request_name(DESTINATION)
            self.bus.add_message_handler(self.handle)

        def handle(self, message):
            if message.message_type != MessageType.METHOD_CALL:
                return None
            if message.interface not in (INTERFACE, "org.freedesktop.portal.Session", "org.freedesktop.portal.Request"):
                return None
            self.calls.append((message.interface, message.member, message.body))
            if message.member in ("CreateSession", "SelectDevices", "Start"):
                options = message.body[-1]
                token = options["handle_token"].value
                sender = message.sender.lstrip(":").replace(".", "_")
                request = f"{PATH}/request/{sender}/{token}"
                values = {}
                code = 0
                if message.member == "CreateSession":
                    values["session_handle"] = Variant("o", PATH + "/session/test/session")
                if message.member == "SelectDevices":
                    assert options["types"].value == 1
                if message.member == "Start":
                    values["devices"] = Variant("u", 1)
                    code = 1 if self.deny else 0
                self.loop.call_later(0.02, lambda: self.bus.send(Message.new_signal(request, "org.freedesktop.portal.Request", "Response", "ua{sv}", [code, values])))
                return Message.new_method_return(message, "o", [request])
            if message.member == "NotifyKeyboardKeysym":
                self.keys.append((message.body[2], message.body[3]))
            return Message.new_method_return(message)

        def close(self):
            self.loop.call_soon_threadsafe(self.bus.disconnect)
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(2)
            self.loop.close()

    server = Server()
    yield server
    server.close()


def test_portal_requests_only_keyboard_and_releases_every_key(portal_server):
    from profile_typer.platforms.wayland import Portal, WaylandPort
    portal = Portal()
    portal.prepare(threading.Event())
    port = WaylandPort(portal)
    try:
        port.prepare(None)
        port.insert("A")
        port.insert("👋")
        port.insert("\n")
        port.backspace()
    finally:
        port.close()
    assert portal_server.keys == [(65, 1), (65, 0), (0x0101F44B, 1), (0x0101F44B, 0),
                                  (0xFF0D, 1), (0xFF0D, 0), (0xFF08, 1), (0xFF08, 0)]
    methods = [call[1] for call in portal_server.calls]
    assert methods[:3] == ["CreateSession", "SelectDevices", "Start"]
    assert methods[-1] == "Close"


def test_permission_denial_never_sends_keys(portal_server):
    from profile_typer.platforms.wayland import Portal
    portal_server.deny = True
    portal = Portal()
    with pytest.raises(RuntimeError, match="declined"):
        portal.prepare(threading.Event())
    assert portal_server.keys == []
    assert portal.closed
