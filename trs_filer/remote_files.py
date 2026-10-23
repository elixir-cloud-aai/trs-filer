"""Retrieve the content of files from their URLs.

All retrieval of file content from URLs goes through
:py:func:`fetch_remote_file`, which applies the settings of the
`custom.remote_files` config section (cf.
:py:class:`trs_filer.custom_config.RemoteFilesConfig`): allowed schemes,
allowed destinations, timeouts, a maximum size and a maximum number of
redirects.

Destinations are checked when connecting, by connection classes of
`urllib3` 2.x (cf. `pyproject.toml`) that resolve host names themselves
and connect only to the checked addresses. The total timeout is enforced by
a timer that shuts down the connections of a retrieval when it expires.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
import re
import socket
import threading
from time import monotonic
from types import TracebackType
from typing import Any, Callable, ClassVar, Collection, Optional
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from requests.compat import chardet
from requests.utils import requote_uri
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
)
from urllib3.util import connection

from trs_filer.custom_config import RemoteFilesConfig
from trs_filer.errors.exceptions import RemoteFileError

logger = logging.getLogger(__name__)

# Checks a destination (host name and resolved IP address) before connecting
DestinationCheck = Callable[[str, str], None]

# Shape of URLs that may be retrieved: `http` or `https`, a host (without
# user info) and an optional port, path, query and fragment, without
# whitespace and control characters
_URL_REGEX = (
    r"(?i)https?://[^\s\x00-\x1f\x7f/?#@\\]+"
    r"(?:[/?#][^\s\x00-\x1f\x7f]*)?"
)

# IPv6 prefixes with embedded IPv4 addresses (last 32 bits), checked as
# IPv4 addresses: NAT64 well-known prefix (RFC 6052) and IPv4-compatible
# addresses (deprecated, RFC 4291); 6to4 and Teredo addresses are checked
# via `ipaddress`
# IPv6 networks that aren't public, but not refused by `ipaddress` on all
# supported Python versions: site-local (deprecated, RFC 3879),
# documentation (RFC 9637) and local-use NAT64 (RFC 8215) addresses
_NOT_PUBLIC_IPV6 = (
    ipaddress.IPv6Network("fec0::/10"),
    ipaddress.IPv6Network("3fff::/20"),
    ipaddress.IPv6Network("64:ff9b:1::/48"),
)
_IPV4_EMBEDDING = (
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("::/96"),
)


class InvalidURL(ValueError):
    """A URL is invalid or uses a scheme that is not allowed."""


def check_url(url: object, schemes: Collection[str]) -> None:
    """Check that a URL is a valid HTTP(S) URL with an allowed scheme.

    Args:
        url: URL.
        schemes: Allowed schemes, lowercase (`http`, `https`).

    Raises:
        InvalidURL: The URL is not a string, is not an HTTP(S) URL with a
            host (e.g., has user info, whitespace or control characters, or
            an invalid port), or uses a scheme that is not allowed.
    """
    if not isinstance(url, str) or re.fullmatch(_URL_REGEX, url) is None:
        raise InvalidURL(f"Not an HTTP(S) URL with a host: {url!r}")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidURL(f"Invalid URL: {url!r}") from exc
    if parts.scheme.lower() not in schemes:
        raise InvalidURL(
            f"Scheme '{parts.scheme}' is not allowed (allowed: "
            f"{', '.join(sorted(schemes))})"
        )
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidURL(f"Invalid port: {url!r}") from exc
    if not parts.hostname or port == 0:
        raise InvalidURL(f"Invalid host or port: {url!r}")


class DestinationNotAllowed(Exception):
    """A destination is not allowed by the configuration.

    Not an `OSError`, so that `urllib3` and `requests` neither retry nor wrap
    it.
    """


@dataclass(frozen=True)
class RemoteFile:
    """Content retrieved from a URL.

    Args:
        content: Content.
        encoding: Character encoding declared by the response, if any.

    Attributes:
        content: Content.
        encoding: Character encoding declared by the response, if any.
    """

    content: bytes
    encoding: Optional[str] = None

    @property
    def text(self) -> str:
        """Content decoded as text.

        Returns:
            Content, decoded with the declared encoding. Without a declared
            encoding (or with an unknown one), content is decoded as UTF-8
            if valid, else with the encoding detected by `requests` (as
            `requests.Response.text` does); undecodable bytes are replaced.
        """
        try:
            if self.encoding:
                return self.content.decode(self.encoding, "replace")
        # Unknown (`LookupError`) or malformed (`ValueError`, e.g., with
        # null characters) encodings
        except (LookupError, ValueError):
            pass
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            pass
        detected = chardet.detect(self.content)["encoding"] or "utf-8"
        try:
            return self.content.decode(detected, "replace")
        except LookupError:  # pragma: no cover (detected encodings exist)
            return self.content.decode("utf-8", "replace")


def is_public_address(address: str) -> bool:
    """Check whether an IP address is public.

    Args:
        address: IP address, optionally with an IPv6 zone identifier.

    Returns:
        Whether the address is globally reachable (as per the IANA special
        purpose address registries) and not a multicast address. IPv6
        addresses with embedded IPv4 addresses (IPv4-mapped,
        IPv4-compatible, NAT64, 6to4 and Teredo addresses) are checked as
        their IPv4 addresses (both server and client for Teredo).
    """
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        embedded: list[ipaddress.IPv4Address] = []
        if ip.ipv4_mapped is not None:
            embedded = [ip.ipv4_mapped]
        elif ip.sixtofour is not None:
            embedded = [ip.sixtofour]
        elif ip.teredo is not None:
            embedded = list(ip.teredo)
        elif any(ip in prefix for prefix in _IPV4_EMBEDDING):
            embedded = [ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)]
        if embedded:
            return all(is_public_address(str(ipv4)) for ipv4 in embedded)
        if any(ip in network for network in _NOT_PUBLIC_IPV6):
            return False
    return ip.is_global and not ip.is_multicast


def make_destination_check(config: RemoteFilesConfig) -> DestinationCheck:
    """Make a check of destinations, as configured.

    Args:
        config: Settings for retrieving files.

    Returns:
        Function that raises :py:class:`DestinationNotAllowed` for a host
        name and one of its resolved IP addresses, unless the host name or
        address is allowed explicitly (`allowed_hosts`) or the address is
        public.
    """
    hosts = set(config.allowed_hosts)
    networks = config.allowed_networks

    def check(host: str, address: str) -> None:
        """Check a destination.

        Args:
            host: Host name, as in the URL.
            address: Resolved IP address.

        Raises:
            DestinationNotAllowed: The destination is not allowed.
        """
        if host.rstrip(".").lower() in hosts:
            return
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if any(ip in network for network in networks):
            return
        if not is_public_address(address):
            raise DestinationNotAllowed(
                f"Host '{host}' resolves to address '{address}', which is "
                "not public and not in `allowed_hosts`"
            )

    return check


class _Deadline:
    """Total timeout of a retrieval, enforced by a timer.

    When the timer expires, the registered sockets are shut down, which
    ends blocking reads (also of headers, and within chunks).

    Args:
        timeout: Total timeout, in seconds.

    Attributes:
        end: Deadline, as per `time.monotonic()`.
        expired: Whether the timer has expired.
    """

    def __init__(self, timeout: float) -> None:
        """Construct the deadline; the timer starts on entering it.

        Args:
            timeout: Total timeout, in seconds.
        """
        self.end = monotonic() + timeout
        self.expired = False
        self._sockets: list[socket.socket] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(timeout, self._expire)
        self._timer.daemon = True

    def __enter__(self) -> "_Deadline":
        """Start the timer.

        Returns:
            The deadline.
        """
        self._timer.start()
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Stop the timer.

        Args:
            exc_type: Type of the exception raised, if any.
            exc: Exception raised, if any.
            traceback: Traceback of the exception raised, if any.
        """
        self._timer.cancel()

    def remaining(self) -> float:
        """Get the time remaining until the deadline.

        Returns:
            Remaining time, in seconds.

        Raises:
            RemoteFileError: The deadline has passed.
        """
        remaining = self.end - monotonic()
        if self.expired or remaining <= 0:
            raise RemoteFileError("Retrieval exceeded the total timeout")
        return remaining

    def register(self, sock: socket.socket) -> None:
        """Register a socket, to be shut down when the timer expires.

        Args:
            sock: Connected socket.
        """
        with self._lock:
            self._sockets.append(sock)
            expired = self.expired
        if expired:
            _shutdown(sock)

    def _expire(self) -> None:
        """Shut down the registered sockets."""
        with self._lock:
            self.expired = True
            sockets = list(self._sockets)
        for sock in sockets:
            _shutdown(sock)


def _shutdown(sock: socket.socket) -> None:
    """Shut down a socket, ignoring errors (e.g., if already closed).

    Args:
        sock: Socket.
    """
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class _CheckedConnectionMixin:
    """Check destinations of connections before connecting.

    Host names are resolved once; connections are only made to the resolved
    addresses, and only if all of them are allowed, so that the checked
    addresses are the ones connected to. Each address is tried with the
    connect timeout, capped at the time remaining until the deadline;
    connected sockets are registered with the deadline. Subclasses set
    :py:attr:`check` and :py:attr:`deadline`.

    Attributes:
        check: Check of destinations.
        deadline: Total timeout of the retrieval.
    """

    check: ClassVar[DestinationCheck]
    deadline: ClassVar[_Deadline]
    # Attributes of `urllib3` connections
    _dns_host: str
    host: str
    port: int
    timeout: Any
    source_address: Any
    socket_options: Any

    def _new_conn(self) -> socket.socket:
        """Resolve the host, check its addresses, and connect.

        Overrides `urllib3.connection.HTTPConnection._new_conn()`, raising
        the same exceptions on failure.

        Returns:
            Connected socket.

        Raises:
            DestinationNotAllowed: An address of the host is not allowed.
            urllib3.exceptions.NameResolutionError: The host name could not
                be resolved.
            urllib3.exceptions.ConnectTimeoutError: Connecting timed out.
            urllib3.exceptions.NewConnectionError: Connecting failed, or the
                host has no addresses.
            RemoteFileError: The deadline has passed.
        """
        # `urllib3` exceptions take the connection; mixed into `urllib3`
        # connections only
        conn: HTTPConnection = self  # type: ignore[assignment]
        try:
            infos = socket.getaddrinfo(
                self._dns_host, self.port, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, conn, exc) from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
        for address in addresses:
            self.check(self.host, address)
        error: Exception = NewConnectionError(
            conn, f"No addresses for host {self.host}"
        )
        for address in addresses:
            timeout = self.deadline.remaining()
            if isinstance(self.timeout, (int, float)):
                timeout = min(self.timeout, timeout)
            try:
                sock = connection.create_connection(
                    (address, self.port),
                    timeout,
                    source_address=self.source_address,
                    socket_options=self.socket_options,
                )
                self.deadline.register(sock)
                return sock
            except socket.timeout as exc:
                error = ConnectTimeoutError(
                    conn, f"Connection to {self.host} timed out"
                )
                error.__cause__ = exc
            except OSError as exc:
                error = NewConnectionError(
                    conn, f"Failed to establish a new connection: {exc}"
                )
                error.__cause__ = exc
        raise error

    def connect(self) -> None:
        """Connect, and register the socket in use with the deadline.

        For HTTPS, `urllib3` replaces the socket of :py:meth:`_new_conn` with
        a TLS socket (detaching the former), which is registered here.
        """
        super().connect()  # type: ignore[misc]
        sock = getattr(self, "sock", None)
        if sock is not None:
            self.deadline.register(sock)


class _CheckedHTTPConnection(_CheckedConnectionMixin, HTTPConnection):
    """HTTP connection that checks its destination."""


class _CheckedHTTPSConnection(_CheckedConnectionMixin, HTTPSConnection):
    """HTTPS connection that checks its destination."""


class _CheckedAdapter(HTTPAdapter):
    """Transport adapter whose connections check their destinations."""

    def __init__(
        self,
        check: DestinationCheck,
        deadline: _Deadline,
        **kwargs: Any,
    ) -> None:
        """Construct the adapter.

        Args:
            check: Check of destinations.
            deadline: Total timeout of the retrieval.
            **kwargs: Arguments of `requests.adapters.HTTPAdapter`.
        """
        self._check = check
        self._deadline = deadline
        super().__init__(**kwargs)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the pool manager, with checked connections.

        Connection pools are created per adapter, with connection classes
        that use the adapter's check and deadline.

        Args:
            *args: Positional arguments of the parent method.
            **kwargs: Keyword arguments of the parent method.
        """
        super().init_poolmanager(*args, **kwargs)
        attributes = {
            "check": staticmethod(self._check),
            "deadline": self._deadline,
        }
        http = type("CheckedHTTPConnection", (_CheckedHTTPConnection,), attributes)
        https = type("CheckedHTTPSConnection", (_CheckedHTTPSConnection,), attributes)
        self.poolmanager.pool_classes_by_scheme = {
            "http": type(
                "CheckedHTTPConnectionPool",
                (HTTPConnectionPool,),
                {"ConnectionCls": http},
            ),
            "https": type(
                "CheckedHTTPSConnectionPool",
                (HTTPSConnectionPool,),
                {"ConnectionCls": https},
            ),
        }


def _make_session(config: RemoteFilesConfig, deadline: _Deadline) -> requests.Session:
    """Make an HTTP session for retrieving a file.

    Proxies of the environment are not used, so that destinations can be
    checked.

    Args:
        config: Settings for retrieving files.
        deadline: Total timeout of the retrieval.

    Returns:
        Session with checked connections.
    """
    session = requests.Session()
    session.trust_env = False
    adapter = _CheckedAdapter(
        check=make_destination_check(config),
        deadline=deadline,
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _redact(url: str) -> str:
    """Redact user info of a URL, for logging.

    Args:
        url: URL.

    Returns:
        URL without user info, quoted with control characters escaped.
    """
    scheme, separator, rest = url.partition("://")
    if separator:
        ends = [index for index in map(rest.find, "/?#") if index >= 0]
        at = rest.rfind("@", 0, min(ends, default=len(rest)))
        if at >= 0:
            url = f"{scheme}{separator}***@{rest[at + 1 :]}"
    return repr(url)


def _read_limited(response: requests.Response, max_size: int) -> bytes:
    """Read the body of a response, up to a maximum size.

    Args:
        response: Streamed response.
        max_size: Maximum size, in bytes.

    Returns:
        Body.

    Raises:
        RemoteFileError: The body is larger than the maximum size.
    """
    encoding = response.headers.get("Content-Encoding", "identity")
    if encoding.strip().lower() not in ("", "identity"):
        raise RemoteFileError(f"Content encoding '{encoding}' is not supported")
    declared = response.headers.get("Content-Length", "")
    if declared.isascii() and declared.isdigit() and int(declared) > max_size:
        raise RemoteFileError(
            f"Content of {declared} bytes exceeds the maximum size of {max_size} bytes"
        )
    body = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        body.extend(chunk)
        if len(body) > max_size:
            raise RemoteFileError(
                f"Content exceeds the maximum size of {max_size} bytes"
            )
    return bytes(body)


def fetch_remote_file(url: str, config: RemoteFilesConfig) -> RemoteFile:
    """Retrieve the content of a file from its URL, as configured.

    The URL, and the URL of every redirect, must use an allowed scheme and
    be valid (cf. :py:func:`check_url`); its host must resolve to
    allowed addresses only. Redirects are followed up to the maximum number;
    responses other than `2xx` fail. Retrieval, including redirects, must
    finish within the total timeout; name resolution is not limited by it.

    Args:
        url: URL of the file.
        config: Settings for retrieving files.

    Returns:
        Retrieved content.

    Raises:
        RemoteFileError: The content could not be retrieved, or retrieval is
            not allowed by the configuration.
    """
    deadline = _Deadline(timeout=config.total_timeout)
    try:
        with deadline:
            file = _fetch(url=url, config=config, deadline=deadline)
        # Connections shut down at the deadline may look like complete
        # responses (without `Content-Length`)
        deadline.remaining()
        return file
    except RemoteFileError as exc:
        reason: object = exc.description
    # `ValueError` includes `InvalidURL` and errors on
    # malformed URLs and headers; `OSError` includes the exceptions of
    # `requests` (e.g., timeouts) and TLS errors of lower layers
    except (DestinationNotAllowed, ValueError, OSError) as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if deadline.expired:
            reason = f"Retrieval exceeded the total timeout ({reason})"
    logger.error(f"Could not retrieve file from URL {_redact(url)}: {reason!r}")
    raise RemoteFileError(str(reason))


def _fetch(url: str, config: RemoteFilesConfig, deadline: _Deadline) -> RemoteFile:
    """Retrieve the content of a file from its URL (cf.
    :py:func:`fetch_remote_file`).

    Args:
        url: URL of the file.
        config: Settings for retrieving files.
        deadline: Total timeout of the retrieval.

    Returns:
        Retrieved content.

    Raises:
        RemoteFileError: Too many redirects, a response other than `2xx`,
            content larger than the maximum size, or the total timeout
            exceeded.
        DestinationNotAllowed: A host resolves to an address that is not
            allowed.
        ValueError: A URL is invalid or uses a scheme that is not allowed
            (:py:class:`InvalidURL`), or a redirect location is malformed.
        requests.RequestException: The request failed, e.g., timed out
            (an `OSError`).
    """
    # Characters that URLs only allow percent-encoded (e.g., spaces) are
    # encoded, as `requests` would do
    current = requote_uri(url)
    with _make_session(config, deadline) as session:
        for _ in range(config.max_redirects + 1):
            check_url(current, schemes=config.schemes)
            remaining = deadline.remaining()
            # Requests are only made to URLs of the checked shape (also
            # checked by `check_url()`), in this branch, so that static
            # analysis recognizes them as checked
            if re.fullmatch(_URL_REGEX, current):
                response = session.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(
                        min(config.connect_timeout, remaining),
                        min(config.read_timeout, remaining),
                    ),
                    headers={"Accept-Encoding": "identity"},
                )
            else:  # pragma: no cover (refused by `check_url()`)
                raise InvalidURL(f"Not an HTTP(S) URL: {current!r}")
            with response:
                if response.is_redirect:
                    current = requote_uri(
                        urljoin(current, response.headers["Location"])
                    )
                    continue
                if not 200 <= response.status_code < 300:
                    raise RemoteFileError(f"Response status {response.status_code}")
                return RemoteFile(
                    content=_read_limited(response, config.max_size),
                    encoding=response.encoding,
                )
    raise RemoteFileError(f"More than {config.max_redirects} redirects")
