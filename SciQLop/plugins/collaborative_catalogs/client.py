from typing import List, Optional
from datetime import datetime, timedelta, timezone
from PySide6.QtCore import QObject
from SciQLop.components.sciqlop_logging import getLogger
from cocat import DB
from wire_websocket import AsyncWebSocketClient
from wire_file import AsyncFileClient
from SciQLop.components.storage import user_data_dir
from SciQLop.core.sciqlop_application import sciqlop_event_loop, sciqlop_app
import asyncio
import httpx
import traceback
from urllib.parse import urlparse
import jwt

log = getLogger(__name__)

_RECONNECT_INITIAL_BACKOFF = 1.0   # seconds
_RECONNECT_MAX_BACKOFF = 30.0      # seconds


def _ensure_logged_in(self):
    if not self.logged_in:
        if not self.login():
            log.error("Cannot perform action, not logged in")
            return False
    return True


def ensure_login(func):
    if asyncio.iscoroutinefunction(func):
        async def wrapper(self, *args, **kwargs):
            if not _ensure_logged_in(self):
                return None
            return await func(self, *args, **kwargs)

        return wrapper
    else:
        def wrapper(self, *args, **kwargs):
            if not _ensure_logged_in(self):
                return None
            return func(self, *args, **kwargs)

        return wrapper


def _ensure_room_joined(self):
    if self._client is None:
        return False
    return True


def ensure_room_joined(func):
    if asyncio.iscoroutinefunction(func):
        async def wrapper(self, *args, **kwargs):
            if not _ensure_room_joined(self):
                log.error("Cannot perform action, you must join a room first")
                return None
            return await func(self, *args, **kwargs)

        return wrapper
    else:
        def wrapper(self, *args, **kwargs):
            if not _ensure_room_joined(self):
                log.error("Cannot perform action, you must join a room first")
                return None
            return func(self, *args, **kwargs)

        return wrapper


class Client(QObject):

    def __init__(self, url: str = "https://sciqlop.lpp.polytechnique.fr/cocat/", room_id: Optional[str] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._url = url[:-1] if url.endswith("/") else url
        p = urlparse(self._url)
        self._host = f"{p.scheme}://{p.hostname}"
        self._port = p.port or (443 if p.scheme == "https" else 80)
        self._prefix = p.path[1:] + "/" if p.path else ""
        self._db = DB()
        self._room_id = room_id
        self._client: Optional[AsyncWebSocketClient] = None
        self._cookies = httpx.Cookies()
        self._file = None
        self._task: Optional[asyncio.Task] = None
        self._close_event = asyncio.Event()
        self._connecting_event = asyncio.Event()
        self._connected = False
        self._ever_connected = False

    @property
    def logged_in(self) -> bool:
        token = self._cookies.get("fastapiusersauth")
        if token is None:
            return False
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            exp = payload.get("exp")
            if exp is None:
                return False
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            if exp_datetime < datetime.now(tz=timezone.utc) + timedelta(minutes=5):
                return False
            return True
        except jwt.PyJWTError:
            return False

    def login(self):
        if self.logged_in:
            return True
        from .settings import CollaborativeCatalogsSettings
        settings = CollaborativeCatalogsSettings()
        username, password = settings.username, settings.password
        if not username or not password:
            log.info("No credentials configured for %s", self._url)
            return False
        if self._room_id is None:
            self._room_id = username.split("@")[0]
        data = {"username": username, "password": password}
        try:
            response = httpx.post(f"{self._url}/auth/jwt/login", data=data)
        except Exception as e:
            log.error("Cannot reach CoCat server at %s: %s", self._url, e)
            return False
        cookie = response.cookies.get("fastapiusersauth")
        if cookie:
            self._cookies.set("fastapiusersauth", cookie)
            log.info("Successfully logged in to %s", self._url)
            return True
        log.info("Login rejected by %s", self._url)
        return False

    def logout(self):
        self._cookies.delete("fastapiusersauth")

    @property
    @ensure_login
    @ensure_room_joined
    def db(self):
        return self._db

    @property
    def room_id(self):
        return self._room_id

    @ensure_login
    def list_rooms(self) -> List[str]:
        response = httpx.get(f"{self._url}/rooms", cookies=self._cookies)
        if response.status_code == 200:
            data = response.json()
            return data.get("rooms", [])
        return []

    async def join_room(self, room_id: Optional[str] = None) -> bool:
        if room_id:
            self._room_id = room_id
        if self._connected:
            await self.leave_room()
        self._connecting_event.clear()
        self._close_event.clear()
        self._ever_connected = False
        self._task = asyncio.create_task(self._run())
        await self._connecting_event.wait()
        if not self._connected:
            log.error("Failed to join room %r", self._room_id)
            return False
        return True

    async def leave_room(self):
        if self._task:
            self._close_event.set()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
            self._task = None
            self._close_event = asyncio.Event()

    async def _run(self):
        """Keep the room connected, reconnecting with exponential backoff after a
        dropped connection, until ``leave_room`` sets ``_close_event``. The initial
        connection is not retried: if it never succeeds, the loop gives up so the
        caller (``join_room``) reports failure instead of spinning forever."""
        backoff = _RECONNECT_INITIAL_BACKOFF
        try:
            while not self._close_event.is_set():
                if _ensure_logged_in(self):
                    try:
                        await self._connect_session()
                        backoff = _RECONNECT_INITIAL_BACKOFF
                    except Exception as e:
                        log.error("CoCat room %r connection error: %s", self._room_id, e)
                        log.debug(traceback.format_exc())
                else:
                    log.error("CoCat room %r: not logged in", self._room_id)

                if not self._ever_connected or self._close_event.is_set():
                    break
                log.info("CoCat room %r disconnected; reconnecting in %ss",
                         self._room_id, backoff)
                await self._sleep_or_close(backoff)
                backoff = min(backoff * 2, _RECONNECT_MAX_BACKOFF)
        finally:
            self._task = None
            self._connected = False
            self._connecting_event.set()  # unblock join_room even on initial failure

    async def _connect_session(self):
        """A single websocket+file session. Returns when the socket closes; raises
        if the connection drops. Sets ``_connecting_event`` as soon as it is up so
        ``join_room`` unblocks while the session keeps running in the background."""
        local_file = user_data_dir("collaborative_catalogs") / self._room_id
        try:
            async with (AsyncWebSocketClient(f"/{self._prefix}room/{self._room_id}", doc=self._db.doc,
                                             host=self._host, port=self._port,
                                             cookies=self._cookies) as client,
                        AsyncFileClient("file",
                                        doc=self._db.doc,
                                        path=local_file) as file):
                self._client = client
                self._file = file
                self._connected = True
                self._ever_connected = True
                log.info("Connected to CoCat room %r", self._room_id)
                self._connecting_event.set()
                await self._close_event.wait()
        finally:
            self._client = None
            self._file = None
            self._connected = False

    async def _sleep_or_close(self, timeout: float):
        """Wait up to ``timeout`` seconds, returning early if a close is requested."""
        try:
            await asyncio.wait_for(self._close_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
