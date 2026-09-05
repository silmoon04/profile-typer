"""Wayland keyboard access through the user's RemoteDesktop permission portal."""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from uuid import uuid4

from profile_typer.engine import replay

DESTINATION = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
INTERFACE = "org.freedesktop.portal.RemoteDesktop"


class Portal:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="wayland-portal", daemon=True)
        self.thread.start()
        self.bus = None
        self.session = None
        self.revoked = threading.Event()
        self.closed = False

    def _run(self, coroutine, *, timeout=180):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as error:
            future.cancel()
            raise RuntimeError("The desktop permission portal did not respond.") from error

    async def _message(self, interface, member, signature="", body=None, path=PATH):
        from dbus_next import Message, MessageType
        reply = await asyncio.wait_for(self.bus.call(Message(destination=DESTINATION, path=path, interface=interface,
                                                             member=member, signature=signature, body=body or [])), 10)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"Desktop portal rejected {member}: {reply.error_name}. "
                               "Use a desktop with the RemoteDesktop portal (GNOME or KDE), or an X11 session.")
        return reply.body

    async def _request(self, member, signature, body, stop):
        from dbus_next import Message, MessageType, Variant
        token = "typer_" + uuid4().hex
        body[-1]["handle_token"] = Variant("s", token)
        sender = self.bus.unique_name.lstrip(":").replace(".", "_")
        request_path = f"{PATH}/request/{sender}/{token}"
        future = self.loop.create_future()

        def response(message):
            if (message.message_type == MessageType.SIGNAL and message.path == request_path
                    and message.interface == "org.freedesktop.portal.Request" and message.member == "Response"):
                if not future.done():
                    future.set_result(message.body)

        rule = f"type='signal',interface='org.freedesktop.portal.Request',path='{request_path}'"
        self.bus.add_message_handler(response)
        await self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                    interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[rule]))
        try:
            await self._message(INTERFACE, member, signature, body)
            while not future.done():
                if stop.is_set():
                    await self._message("org.freedesktop.portal.Request", "Close", path=request_path)
                    raise RuntimeError("Desktop keyboard permission was cancelled.")
                await asyncio.sleep(0.05)
            code, values = future.result()
            if code != 0:
                raise RuntimeError("Desktop keyboard permission was declined or cancelled.")
            return {name: value.value for name, value in values.items()}
        finally:
            self.bus.remove_message_handler(response)
            await self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                        interface="org.freedesktop.DBus", member="RemoveMatch", signature="s", body=[rule]))

    async def _prepare(self, stop):
        from dbus_next import Variant
        from dbus_next.aio import MessageBus
        self.bus = await MessageBus().connect()
        result = await self._request("CreateSession", "a{sv}", [{"session_handle_token": Variant("s", "typer_" + uuid4().hex)}], stop)
        self.session = result["session_handle"]
        await self._request("SelectDevices", "oa{sv}", [self.session, {"types": Variant("u", 1)}], stop)
        result = await self._request("Start", "osa{sv}", [self.session, "", {}], stop)
        if not result.get("devices", 0) & 1:
            raise RuntimeError("The desktop did not grant keyboard access.")

        def session_closed(message):
            if message.path == self.session and message.interface == "org.freedesktop.portal.Session" and message.member == "Closed":
                self.revoked.set()

        self.bus.add_message_handler(session_closed)
        from dbus_next import Message
        await self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
                                    member="AddMatch", signature="s",
                                    body=[f"type='signal',interface='org.freedesktop.portal.Session',path='{self.session}'"]))

    def prepare(self, stop):
        try:
            self._run(self._prepare(stop))
        except Exception:
            self.close()
            raise

    def press(self, keysym, dwell_ms=0, stop=None):
        async def send():
            await self._message(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu", [self.session, {}, keysym, 1])
            try:
                deadline = self.loop.time() + dwell_ms / 1000
                while self.loop.time() < deadline and not (stop is not None and stop.is_set()):
                    await asyncio.sleep(min(0.02, deadline - self.loop.time()))
            finally:
                await self._message(INTERFACE, "NotifyKeyboardKeysym", "oa{sv}iu", [self.session, {}, keysym, 0])
        self._run(send(), timeout=25)

    async def _close(self):
        if self.bus is not None:
            try:
                if self.session:
                    await self._message("org.freedesktop.portal.Session", "Close", path=self.session)
            finally:
                self.bus.disconnect()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self._run(self._close(), timeout=12)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.loop.close()


class WaylandPort:
    def __init__(self, portal):
        self.portal = portal

    def prepare(self, target):
        if target is not None:
            raise RuntimeError("Wayland requires choosing the destination manually during the countdown.")

    def cancelled(self):
        return self.portal.revoked.is_set()

    def insert(self, character, *, dwell_ms=0, stop=None):
        keysym = {"\n": 0xFF0D, "\t": 0xFF09}.get(character)
        if keysym is None:
            codepoint = ord(character)
            keysym = codepoint if codepoint <= 0xFF else 0x01000000 | codepoint
        self.portal.press(keysym, dwell_ms, stop)

    def backspace(self, *, dwell_ms=0, stop=None):
        self.portal.press(0xFF08, dwell_ms, stop)

    def close(self):
        self.portal.close()


class WaylandTypingBackend:
    requires_preparation = True
    minimize_for_countdown = True
    desktop_note = "Wayland: allow keyboard access, then choose the destination. Stop via this app or the desktop sharing indicator."

    def __init__(self):
        self.portal = None

    def targets(self):
        return []

    def escape_pressed(self):
        return False

    def prepare(self, stop):
        self.portal = Portal()
        self.portal.prepare(stop)

    def release(self):
        if self.portal is not None:
            self.portal.close()
            self.portal = None

    def type(self, text, target, settings, stop, progress):
        if self.portal is None:
            raise RuntimeError("Desktop keyboard permission has not been granted.")
        try:
            return replay(text, WaylandPort(self.portal), settings, stop, progress, target=target)
        finally:
            self.release()
