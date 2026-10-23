"""Tests for retrieving the content of files from their URLs.

No network is used: name resolution and connections are replaced by fakes
that serve canned HTTP responses.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import socket
import ssl
import threading
import time
from typing import Any, Iterator, Optional

from pydantic import ValidationError
import pytest
import yaml

from trs_filer import remote_files
from trs_filer.custom_config import CustomConfig, RemoteFilesConfig
from trs_filer.errors.exceptions import RemoteFileError
from trs_filer.remote_files import (
    DestinationNotAllowed,
    InvalidURL,
    check_url,
    _CheckedConnectionMixin,
    _Deadline,
    _make_session,
    _redact,
    RemoteFile,
    fetch_remote_file,
    is_public_address,
    make_destination_check,
)

PUBLIC = "93.184.216.34"
PUBLIC_6 = "2606:2800:220:1:248:1893:25c8:1946"
PRIVATE = "10.0.0.5"


def _response(
    body: bytes = b"content",
    status: str = "200 OK",
    headers: Optional[dict[str, str]] = None,
    length: bool = True,
) -> bytes:
    """Build a raw HTTP response; the connection is closed after it.

    Args:
        body: Body.
        status: Status code and reason phrase.
        headers: Additional headers.
        length: Whether to send `Content-Length`.

    Returns:
        Raw HTTP response.
    """
    lines = [f"HTTP/1.1 {status}", "Connection: close"]
    if length:
        lines.append(f"Content-Length: {len(body)}")
    lines += [f"{name}: {value}" for name, value in (headers or {}).items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


class FakeSocket:
    """Socket serving a canned HTTP response.

    Args:
        response: Raw HTTP response.

    Attributes:
        response: Raw HTTP response.
        sent: Bytes sent.
    """

    def __init__(self, response: bytes) -> None:
        """Construct the socket.

        Args:
            response: Raw HTTP response.
        """
        self.response = response
        self.sent = b""

    def sendall(self, data: bytes) -> None:
        """Record sent bytes.

        Args:
            data: Bytes.
        """
        self.sent += data

    def makefile(self, *args: Any, **kwargs: Any) -> BytesIO:
        """Read the response.

        Args:
            *args: Ignored.
            **kwargs: Ignored.

        Returns:
            Response stream.
        """
        return BytesIO(self.response)

    def settimeout(self, timeout: Any) -> None:
        """Ignore timeouts.

        Args:
            timeout: Ignored.
        """

    def close(self) -> None:
        """Close the socket (no-op)."""

    def shutdown(self, how: int) -> None:
        """Shut down the socket (no-op).

        Args:
            how: Ignored.
        """


class FakeNetwork:
    """Fake name resolution and connections.

    Attributes:
        hosts: IP addresses of host names.
        responses: Raw HTTP responses by IP address (lists are served in
            turn); `OSError` instances are raised on connecting instead.
        connected: Addresses connected to, with timeouts.
        sockets: Sockets created.
    """

    def __init__(self) -> None:
        """Construct the network."""
        self.hosts: dict[str, list[str]] = {}
        self.responses: dict[str, Any] = {}
        self.connected: list[tuple[str, int, Any]] = []
        self.sockets: list[FakeSocket] = []

    def getaddrinfo(self, host: str, port: int, *args: Any, **kwargs: Any):
        """Resolve a host name, or an IP address to itself.

        Args:
            host: Host name or IP address.
            port: Port.
            *args: Ignored.
            **kwargs: Ignored.

        Returns:
            Address infos.

        Raises:
            socket.gaierror: The host name is unknown.
        """
        if host in self.hosts:
            addresses = self.hosts[host]
        elif host in self.responses:
            addresses = [host]
        else:
            raise socket.gaierror(socket.EAI_NONAME, "Name not known")
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]

    def create_connection(
        self, address: tuple[str, int], timeout: Any, **kwargs: Any
    ) -> FakeSocket:
        """Connect to an IP address.

        Args:
            address: IP address and port.
            timeout: Connect timeout.
            **kwargs: Ignored.

        Returns:
            Socket.

        Raises:
            OSError: Connecting fails, as configured.
        """
        self.connected.append((address[0], address[1], timeout))
        response = self.responses[address[0]]
        if isinstance(response, list):
            response = response.pop(0)
        if isinstance(response, BaseException):
            raise response
        sock = FakeSocket(response)
        self.sockets.append(sock)
        return sock


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> FakeNetwork:
    """Fake network for retrieving files.

    Args:
        monkeypatch: Patches of name resolution and connections.

    Returns:
        Fake network.
    """
    fake = FakeNetwork()
    monkeypatch.setattr(remote_files.socket, "getaddrinfo", fake.getaddrinfo)
    monkeypatch.setattr(
        remote_files.connection, "create_connection", fake.create_connection
    )
    return fake


@pytest.fixture
def config() -> RemoteFilesConfig:
    """Config allowing `http`, so that fake responses can be served.

    Returns:
        Settings for retrieving files.
    """
    return RemoteFilesConfig(schemes=["http", "https"])


class TestConfig:
    """Tests for `RemoteFilesConfig`."""

    def test_defaults(self) -> None:
        """Defaults allow `https` only, with limits."""
        config = RemoteFilesConfig()
        assert config.schemes == ["https"]
        assert config.allowed_hosts == []
        assert config.connect_timeout == 5
        assert config.read_timeout == 10
        assert config.total_timeout == 30
        assert config.max_size == 1048576
        assert config.max_redirects == 5

    def test_config_file(self) -> None:
        """The config file has the safe defaults."""
        path = Path(remote_files.__file__).parent / "config.yaml"
        custom = yaml.safe_load(path.read_text())["custom"]
        assert CustomConfig(**custom).remote_files == RemoteFilesConfig()

    def test_allowed_hosts_normalized(self) -> None:
        """Host names are lowercased, networks written canonically."""
        config = RemoteFilesConfig(
            allowed_hosts=[
                " Files.Example. ", "::1", "[fd00::1]", "10.1.2.3/8"
            ]
        )
        assert config.allowed_hosts == [
            "files.example", "::1/128", "fd00::1/128", "10.0.0.0/8"
        ]
        assert [str(net) for net in config.allowed_networks] == [
            "::1/128", "fd00::1/128", "10.0.0.0/8"
        ]

    @pytest.mark.parametrize(
        "values",
        [
            {"schemes": []},
            {"schemes": ["file"]},
            {"schemes": ["ftp"]},
            {"allowed_hosts": [" . "]},
            {"connect_timeout": 0},
            {"read_timeout": -1},
            {"total_timeout": 0},
            {"max_size": 0},
            {"max_redirects": -1},
            {"max_redirects": True},
            {"max_size": 1.9},
            {"total_timeout": float("inf")},
            {"connect_timeout": float("nan")},
        ],
    )
    def test_invalid(self, values: dict[str, Any]) -> None:
        """Invalid settings are rejected.

        Args:
            values: Invalid settings.
        """
        with pytest.raises(ValidationError):
            RemoteFilesConfig(**values)


class TestCheckURL:
    """Tests for `check_url()`."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://files.example.org",
            "https://files.example.org/a.cwl?x=1#y",
            "HTTPS://Files.Example.org:8443/a",
            "https://[2606:2800:220:1::1]/a",
            "http://93.184.216.34/",
        ],
    )
    def test_valid(self, url: str) -> None:
        """HTTP(S) URLs with hosts and allowed schemes are valid.

        Args:
            url: Valid URL.
        """
        check_url(url, schemes=["http", "https"])

    @pytest.mark.parametrize(
        "url",
        [
            None,
            "",
            "files.example.org/a.cwl",
            "file:///etc/hostname",
            "ftp://files.example.org/",
            "https:///a.cwl",
            "https://user@files.example.org/",
            "https://user:secret@files.example.org/",
            "https://files.example.org/a b",
            " https://files.example.org/",
            "https://files.example.org/\x00",
            "https://files.example.org\\@other.example.org/",
            "https://files.example.org:0/",
            "https://files.example.org:99999/",
            "https://files.example.org:x/",
            "https://:443/",
            "https://[::1/",
            "https://a.example\uff20b.example/",
        ],
    )
    def test_invalid(self, url: object) -> None:
        """Other URLs are invalid.

        Args:
            url: Invalid URL.
        """
        with pytest.raises(InvalidURL):
            check_url(url, schemes=["http", "https"])

    def test_scheme_not_allowed(self) -> None:
        """Schemes must be allowed."""
        with pytest.raises(InvalidURL, match="Scheme 'http' is not allowed"):
            check_url("http://files.example.org/", schemes=["https"])


class TestDestinationCheck:
    """Tests for `is_public_address()` and `make_destination_check()`."""

    @pytest.mark.parametrize(
        ("address", "public"),
        [
            (PUBLIC, True),
            (PUBLIC_6, True),
            ("127.0.0.1", False),
            ("::1", False),
            ("10.1.2.3", False),
            ("172.16.0.1", False),
            ("192.168.1.1", False),
            ("169.254.169.254", False),
            ("fe80::1%eth0", False),
            ("fd00::1", False),
            ("100.64.0.1", False),
            ("0.0.0.0", False),
            ("240.0.0.1", False),
            ("224.0.0.1", False),
            ("ff0e::1", False),
            ("::ffff:127.0.0.1", False),
            (f"::ffff:{PUBLIC}", True),
            ("64:ff9b::a9fe:a9fe", False),
            ("64:ff9b::7f00:1", False),
            (f"64:ff9b::{PUBLIC}", True),
            ("::7f00:1", False),
            ("::a00:5", False),
            ("fec0::1", False),
            ("3fff::1", False),
            ("64:ff9b:1::a00:5", False),
            ("2002:7f00:1::", False),
            ("2002:5db8:d822::", True),
            ("2001:0:4136:e378:8000:63bf:80ff:fffe", False),
            ("2001:0:5db8:d822:0:0:a247:2dcb", True),
        ],
    )
    def test_is_public_address(self, address: str, public: bool) -> None:
        """Only global unicast addresses are public.

        Args:
            address: IP address.
            public: Whether the address is public.
        """
        assert is_public_address(address) is public

    def test_allowed_hosts(self) -> None:
        """Allowed host names and networks are exempt from the checks."""
        check = make_destination_check(
            RemoteFilesConfig(allowed_hosts=["files.local", "10.0.0.0/8"])
        )
        check("FILES.LOCAL.", "127.0.0.1")
        check("other.local", "10.2.3.4")
        check("example.org", PUBLIC)
        with pytest.raises(DestinationNotAllowed):
            check("other.local", "192.168.0.1")


class TestRemoteFile:
    """Tests for `RemoteFile`."""

    @pytest.mark.parametrize(
        ("encoding", "text"),
        [
            (None, "grüß"),
            ("utf-8", "grüß"),
            ("latin-1", "grÃ¼Ã\x9f"),
            ("no-such-encoding", "grüß"),
            ("utf-8\x00", "grüß"),
        ],
    )
    def test_text(self, encoding: Optional[str], text: str) -> None:
        """Content is decoded with the declared encoding, or UTF-8.

        Args:
            encoding: Declared encoding.
            text: Expected text.
        """
        file = RemoteFile(content="grüß".encode(), encoding=encoding)
        assert file.text == text

    def test_text_detected(self) -> None:
        """Content that isn't UTF-8, without declared encoding, is decoded
        with the detected encoding.
        """
        text = "Grüße aus Zürich, schöne Grüße und viele Äpfel. " * 4
        file = RemoteFile(content=text.encode("latin-1"))
        assert file.text == text

    def test_text_undetected(self) -> None:
        """Content of undetected encoding is decoded as UTF-8, replacing
        undecodable bytes.
        """
        assert RemoteFile(content=b"\xff\xfe\x00").text


class TestFetchRemoteFile:
    """Tests for `fetch_remote_file()`."""

    def test_success(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Content is retrieved from public destinations, with timeouts.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.hosts["files.example.org"] = [PUBLIC]
        network.responses[PUBLIC] = _response(
            headers={"Content-Type": "text/plain; charset=utf-8"}
        )
        file = fetch_remote_file("http://files.example.org/a.cwl", config)
        assert file == RemoteFile(content=b"content", encoding="utf-8")
        assert network.connected == [(PUBLIC, 80, config.connect_timeout)]
        request = network.sockets[0].sent
        assert request.startswith(b"GET /a.cwl HTTP/1.1\r\n")
        assert b"Host: files.example.org\r\n" in request
        assert b"Accept-Encoding: identity\r\n" in request

    def test_requoted(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Characters that URLs only allow percent-encoded are encoded.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.responses[PUBLIC] = [
            _response(
                status="302 Found",
                headers={"Location": "/b c.cwl"},
                body=b"",
            ),
            _response(),
        ]
        file = fetch_remote_file(f"http://{PUBLIC}/a b.cwl", config)
        assert file.content == b"content"
        assert network.sockets[0].sent.startswith(b"GET /a%20b.cwl ")
        assert network.sockets[1].sent.startswith(b"GET /b%20c.cwl ")

    def test_success_without_length(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Content without declared length is read up to the limit.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.responses[PUBLIC] = _response(length=False)
        file = fetch_remote_file(f"http://{PUBLIC}/", config)
        assert file.content == b"content"

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/hostname",
            "ftp://files.example.org/a.cwl",
            "gopher://files.example.org/",
            "http://files.example.org/a.cwl",
            "https://user:secret@files.example.org/a.cwl",
            "https:///a.cwl",
            "not a url",
        ],
    )
    def test_scheme_or_url_refused(
        self, network: FakeNetwork, url: str
    ) -> None:
        """URLs of other schemes than `https` (default), and invalid URLs,
        are refused without connecting.

        Args:
            network: Fake network.
            url: Refused URL.
        """
        network.hosts["files.example.org"] = [PUBLIC]
        network.responses[PUBLIC] = _response()
        with pytest.raises(RemoteFileError):
            fetch_remote_file(url, RemoteFilesConfig())
        assert network.connected == []

    @pytest.mark.parametrize(
        "addresses",
        [
            ["127.0.0.1"],
            ["169.254.169.254"],
            [PRIVATE],
            [PUBLIC, PRIVATE],
            ["::1"],
            ["224.0.0.1"],
        ],
    )
    def test_destination_refused(
        self,
        network: FakeNetwork,
        config: RemoteFilesConfig,
        addresses: list[str],
    ) -> None:
        """Hosts resolving to any address that isn't public are refused
        without connecting.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            addresses: Resolved addresses.
        """
        network.hosts["files.example.org"] = addresses
        for address in addresses:
            network.responses[address] = _response()
        for url in (
            "http://files.example.org/a.cwl",
            "https://files.example.org/a.cwl",
        ):
            with pytest.raises(RemoteFileError):
                fetch_remote_file(url, config)
        assert network.connected == []

    def test_https_checked(
        self,
        network: FakeNetwork,
        config: RemoteFilesConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`https` connections are checked like `http` ones and made to
        public destinations; TLS errors fail retrieval.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            monkeypatch: Patch of TLS handshakes.
        """
        hostnames = []

        def wrap_socket(self: ssl.SSLContext, sock: Any, **kwargs: Any):
            """Fail the TLS handshake.

            Args:
                self: TLS context.
                sock: Socket.
                **kwargs: Arguments, e.g., the server host name.

            Raises:
                ssl.SSLError: Always.
            """
            hostnames.append(kwargs.get("server_hostname"))
            raise ssl.SSLError("handshake failed")

        monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
        network.hosts["files.example.org"] = [PUBLIC]
        network.responses[PUBLIC] = _response()
        with pytest.raises(RemoteFileError):
            fetch_remote_file("https://files.example.org/a.cwl", config)
        assert network.connected == [(PUBLIC, 443, config.connect_timeout)]
        assert hostnames == ["files.example.org"]

    def test_connection_classes(self, config: RemoteFilesConfig) -> None:
        """Sessions use connection classes that check destinations.

        Args:
            config: Settings for retrieving files.
        """
        deadline = _Deadline(timeout=1)
        with _make_session(config, deadline) as session:
            assert session.trust_env is False
            for scheme in ("http", "https"):
                adapter = session.get_adapter(f"{scheme}://example.org")
                pool_class = adapter.poolmanager.pool_classes_by_scheme[scheme]
                conn_class = pool_class.ConnectionCls
                assert issubclass(conn_class, _CheckedConnectionMixin)
                assert conn_class.deadline is deadline
                conn_class.check("example.org", PUBLIC)
                with pytest.raises(DestinationNotAllowed):
                    conn_class.check("example.org", "127.0.0.1")

    def test_ip_literal_refused(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """URLs with private IP addresses are refused.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.responses[PRIVATE] = _response()
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PRIVATE}/", config)
        assert network.connected == []

    def test_allowed_host(self, network: FakeNetwork) -> None:
        """Allowed hosts may resolve to addresses that aren't public.

        Args:
            network: Fake network.
        """
        network.hosts["files.local"] = [PRIVATE]
        network.responses[PRIVATE] = _response()
        config = RemoteFilesConfig(
            schemes=["http"], allowed_hosts=["files.local"]
        )
        assert fetch_remote_file(
            "http://files.local/a.cwl", config
        ).content == b"content"

    def test_redirect(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Redirects are followed, also relative ones.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.hosts["a.example.org"] = [PUBLIC]
        network.hosts["b.example.org"] = [PUBLIC_6]
        network.responses[PUBLIC] = _response(
            status="302 Found",
            headers={"Location": "http://b.example.org/start"},
            body=b"",
        )
        network.responses[PUBLIC_6] = [
            _response(
                status="301 Moved Permanently",
                headers={"Location": "/b.cwl"},
                body=b"",
            ),
            _response(body=b"redirected"),
        ]
        file = fetch_remote_file("http://a.example.org/a.cwl", config)
        assert file.content == b"redirected"
        assert [address for address, _, _ in network.connected] == [
            PUBLIC, PUBLIC_6, PUBLIC_6
        ]
        assert network.sockets[-1].sent.startswith(b"GET /b.cwl ")

    def test_redirect_to_refused_destination(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Redirects to destinations that aren't public are refused.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.hosts["files.example.org"] = [PUBLIC]
        network.hosts["internal.example.org"] = [PRIVATE]
        network.responses[PUBLIC] = _response(
            status="302 Found",
            headers={"Location": "http://internal.example.org/"},
            body=b"",
        )
        network.responses[PRIVATE] = _response()
        with pytest.raises(RemoteFileError):
            fetch_remote_file("http://files.example.org/a.cwl", config)
        assert [address for address, _, _ in network.connected] == [PUBLIC]

    @pytest.mark.parametrize(
        "location", ["file:///etc/hostname", f"https://{PUBLIC}/"]
    )
    def test_redirect_to_refused_scheme(
        self, network: FakeNetwork, location: str
    ) -> None:
        """Redirects to schemes that aren't allowed are refused.

        Args:
            network: Fake network.
            location: Redirect location.
        """
        network.responses[PUBLIC] = _response(
            status="307 Temporary Redirect",
            headers={"Location": location},
            body=b"",
        )
        config = RemoteFilesConfig(schemes=["http"])
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)
        assert len(network.connected) == 1

    @pytest.mark.parametrize(
        "location", ["http://[x/", "//[", "http://a]b/"]
    )
    def test_redirect_malformed(
        self, network: FakeNetwork, config: RemoteFilesConfig, location: str
    ) -> None:
        """Malformed redirect locations fail.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            location: Redirect location.
        """
        network.responses[PUBLIC] = _response(
            status="302 Found", headers={"Location": location}, body=b""
        )
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)

    def test_content_length_not_ascii(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """`Content-Length` values that aren't ASCII digits are ignored by
        the size check.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        response = _response(length=False).replace(
            b"Connection: close", "Content-Length: \u00b2".encode("latin-1")
            + b"\r\nConnection: close"
        )
        network.responses[PUBLIC] = response
        file = fetch_remote_file(f"http://{PUBLIC}/", config)
        assert file.content == b"content"

    def test_timeouts_capped(
        self,
        network: FakeNetwork,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Connect and read timeouts are capped at the remaining time.

        Args:
            network: Fake network.
            monkeypatch: Patch of the clock.
        """
        times = [0.0, 1.0, 1.5]
        monkeypatch.setattr(
            remote_files, "monotonic",
            lambda: times.pop(0) if len(times) > 1 else times[0],
        )
        network.responses[PUBLIC] = _response()
        config = RemoteFilesConfig(
            schemes=["http"], total_timeout=3, connect_timeout=5
        )
        assert fetch_remote_file(
            f"http://{PUBLIC}/", config
        ).content == b"content"
        assert network.connected == [(PUBLIC, 80, 1.5)]

    def test_total_timeout_redirects(
        self,
        network: FakeNetwork,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The total timeout covers redirects.

        Args:
            network: Fake network.
            monkeypatch: Patch of the clock.
        """
        times = [0.0, 1.0, 1.0, 100.0]
        monkeypatch.setattr(
            remote_files, "monotonic",
            lambda: times.pop(0) if len(times) > 1 else times[0],
        )
        network.responses[PUBLIC] = _response(
            status="302 Found", headers={"Location": "/again"}, body=b""
        )
        config = RemoteFilesConfig(schemes=["http"], total_timeout=3)
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)
        assert len(network.connected) == 1

    def test_too_many_redirects(self, network: FakeNetwork) -> None:
        """At most the maximum number of redirects are followed.

        Args:
            network: Fake network.
        """
        network.responses[PUBLIC] = _response(
            status="302 Found",
            headers={"Location": "/again"},
            body=b"",
        )
        config = RemoteFilesConfig(schemes=["http"], max_redirects=2)
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)
        assert len(network.connected) == 3

    @pytest.mark.parametrize("length", [True, False])
    def test_too_large(self, network: FakeNetwork, length: bool) -> None:
        """Content larger than the maximum size is refused, with and without
        declared length.

        Args:
            network: Fake network.
            length: Whether the length is declared.
        """
        network.responses[PUBLIC] = _response(body=b"x" * 11, length=length)
        config = RemoteFilesConfig(schemes=["http"], max_size=10)
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)
        network.responses[PUBLIC] = _response(body=b"x" * 10, length=length)
        assert fetch_remote_file(
            f"http://{PUBLIC}/", config
        ).content == b"x" * 10

    @pytest.mark.parametrize(
        "encoding", ["gzip", "deflate", "br", "x-custom"]
    )
    def test_content_encoding_refused(
        self, network: FakeNetwork, config: RemoteFilesConfig, encoding: str
    ) -> None:
        """Encoded content (e.g., compressed) is refused.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            encoding: Content encoding.
        """
        network.responses[PUBLIC] = _response(
            headers={"Content-Encoding": encoding}
        )
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)

    def test_content_encoding_identity(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Content with identity encoding is accepted.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.responses[PUBLIC] = _response(
            headers={"Content-Encoding": "Identity"}
        )
        assert fetch_remote_file(
            f"http://{PUBLIC}/", config
        ).content == b"content"

    @pytest.mark.parametrize(
        "status",
        [
            "404 Not Found",
            "500 Internal Server Error",
            "300 Multiple Choices",
            "302 Found",
            "304 Not Modified",
        ],
    )
    def test_error_status(
        self, network: FakeNetwork, config: RemoteFilesConfig, status: str
    ) -> None:
        """Responses other than `2xx` fail.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            status: Response status.
        """
        network.responses[PUBLIC] = _response(status=status)
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)

    def test_unknown_host(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Host names that can't be resolved fail.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        with pytest.raises(RemoteFileError):
            fetch_remote_file("http://unknown.example.org/", config)

    @pytest.mark.parametrize(
        "error", [socket.timeout("timed out"), ConnectionRefusedError()]
    )
    def test_connect_error(
        self,
        network: FakeNetwork,
        config: RemoteFilesConfig,
        error: OSError,
    ) -> None:
        """Connect timeouts and errors fail, after trying all addresses.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            error: Error on connecting.
        """
        network.hosts["files.example.org"] = [PUBLIC, PUBLIC_6]
        network.responses[PUBLIC] = error
        network.responses[PUBLIC_6] = error
        with pytest.raises(RemoteFileError):
            fetch_remote_file("http://files.example.org/", config)
        assert len(network.connected) == 2

    def test_connect_fallback(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Other addresses are tried if connecting fails.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.hosts["files.example.org"] = [PUBLIC, PUBLIC_6]
        network.responses[PUBLIC] = ConnectionRefusedError()
        network.responses[PUBLIC_6] = _response()
        assert fetch_remote_file(
            "http://files.example.org/", config
        ).content == b"content"

    def test_no_addresses(
        self, network: FakeNetwork, config: RemoteFilesConfig
    ) -> None:
        """Host names without addresses fail.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
        """
        network.hosts["files.example.org"] = []
        with pytest.raises(RemoteFileError):
            fetch_remote_file("http://files.example.org/", config)

    def test_read_timeout(
        self,
        network: FakeNetwork,
        config: RemoteFilesConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Read timeouts fail.

        Args:
            network: Fake network.
            config: Settings for retrieving files.
            monkeypatch: Patch of reading responses.
        """
        network.responses[PUBLIC] = _response()

        class TimeoutStream(BytesIO):
            """Stream that times out on reading."""

            def readline(self, *args: Any, **kwargs: Any) -> bytes:
                """Time out on reading.

                Args:
                    *args: Ignored.
                    **kwargs: Ignored.

                Raises:
                    socket.timeout: Always.
                """
                raise socket.timeout("timed out")

        def timeout(*args: Any, **kwargs: Any) -> BytesIO:
            """Return a stream that times out.

            Args:
                *args: Ignored.
                **kwargs: Ignored.

            Returns:
                Stream.
            """
            return TimeoutStream()

        monkeypatch.setattr(FakeSocket, "makefile", timeout)
        with pytest.raises(RemoteFileError):
            fetch_remote_file(f"http://{PUBLIC}/", config)

    def test_reason_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Reasons are logged, and kept as descriptions.

        Args:
            caplog: Captured logs.
        """
        with pytest.raises(RemoteFileError) as exc_info:
            fetch_remote_file("ftp://files.example.org/", RemoteFilesConfig())
        reason = exc_info.value.description
        assert reason.startswith("InvalidURL: Not an HTTP(S) URL")
        assert [record.getMessage() for record in caplog.records] == [
            "Could not retrieve file from URL 'ftp://files.example.org/': "
            f"{reason!r}"
        ]


@pytest.fixture
def slow_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[bytes]]:
    """Server sending responses slowly, over a local socket pair.

    Name resolution is faked; connections are made to one end of a socket
    pair, to whose other end a thread writes the parts of the response, one
    every 50 ms, while the connection is open.

    Args:
        monkeypatch: Patches of name resolution and connections.

    Yields:
        Parts of the response to send; set by the test.
    """
    parts: list[bytes] = []
    threads: list[threading.Thread] = []
    ends: list[socket.socket] = []

    def send(end: socket.socket) -> None:
        """Send the parts of the response, slowly.

        Args:
            end: Socket to send to.
        """
        try:
            for part in parts:
                end.sendall(part)
                time.sleep(0.05)
        except OSError:
            pass

    def connect(address: tuple[str, int], timeout: Any, **kwargs: Any):
        """Connect to a socket pair.

        Args:
            address: Ignored.
            timeout: Socket timeout.
            **kwargs: Ignored.

        Returns:
            Client end of the socket pair.
        """
        client, server = socket.socketpair()
        client.settimeout(timeout)
        ends.extend([client, server])
        thread = threading.Thread(target=send, args=(server,), daemon=True)
        threads.append(thread)
        thread.start()
        return client

    fake = FakeNetwork()
    fake.hosts["slow.example.org"] = [PUBLIC]
    monkeypatch.setattr(remote_files.socket, "getaddrinfo", fake.getaddrinfo)
    monkeypatch.setattr(remote_files.connection, "create_connection", connect)
    yield parts
    for end in ends:
        end.close()
    for thread in threads:
        thread.join(timeout=5)


class TestConnect:
    """Tests for registering connections with the deadline."""

    def test_connect_registers_socket(self) -> None:
        """Sockets in use after connecting (e.g., TLS sockets replacing the
        sockets connected to) are registered with the deadline.
        """
        registered = []

        class Deadline:
            """Deadline recording registered sockets."""

            def register(self, sock: Any) -> None:
                """Record a socket.

                Args:
                    sock: Socket.
                """
                registered.append(sock)

        class Connection:
            """Connection that replaces its socket on connecting."""

            sock: Any = None

            def connect(self) -> None:
                """Set a replacement socket."""
                self.sock = "tls-socket"

        class Checked(_CheckedConnectionMixin, Connection):
            """Checked connection."""

            deadline = Deadline()  # type: ignore[assignment]

        Checked().connect()
        assert registered == ["tls-socket"]


class TestRedact:
    """Tests for `_redact()`."""

    @pytest.mark.parametrize(
        ("url", "redacted"),
        [
            ("https://h.example/a", "'https://h.example/a'"),
            ("https://u:p@h.example/a@b", "'https://***@h.example/a@b'"),
            ("https://h.example/a\nb", "'https://h.example/a\\nb'"),
        ],
    )
    def test_redact(self, url: str, redacted: str) -> None:
        """User info is redacted, control characters are escaped.

        Args:
            url: URL.
            redacted: Expected redacted URL.
        """
        assert _redact(url) == redacted


class TestTotalTimeout:
    """Tests for the total timeout, with slowly sending servers."""

    @pytest.mark.parametrize(
        "length", [True, False], ids=["length", "no-length"]
    )
    def test_slow_body(self, slow_server: list[bytes], length: bool) -> None:
        """Bodies sent slowly fail at the total timeout, also within reads
        and without declared length.

        Args:
            slow_server: Parts of the response to send.
            length: Whether to send `Content-Length`.
        """
        headers = _response(body=b"x" * 100, length=length)[:-100]
        slow_server.extend([headers] + [b"x"] * 100)
        config = RemoteFilesConfig(
            schemes=["http"], read_timeout=1, total_timeout=0.3
        )
        start = time.monotonic()
        with pytest.raises(RemoteFileError) as exc_info:
            fetch_remote_file("http://slow.example.org/", config)
        assert time.monotonic() - start < 2
        assert "total timeout" in exc_info.value.description

    def test_slow_headers(self, slow_server: list[bytes]) -> None:
        """Headers sent slowly fail at the total timeout.

        Args:
            slow_server: Parts of the response to send.
        """
        slow_server.extend(bytes([byte]) for byte in _response())
        config = RemoteFilesConfig(
            schemes=["http"], read_timeout=1, total_timeout=0.3
        )
        start = time.monotonic()
        with pytest.raises(RemoteFileError):
            fetch_remote_file("http://slow.example.org/", config)
        assert time.monotonic() - start < 2

    def test_within_timeout(self, slow_server: list[bytes]) -> None:
        """Responses sent within the total timeout succeed.

        Args:
            slow_server: Parts of the response to send.
        """
        slow_server.extend([_response(body=b"abc")[:-3], b"a", b"bc"])
        config = RemoteFilesConfig(schemes=["http"], total_timeout=5)
        assert fetch_remote_file(
            "http://slow.example.org/", config
        ).content == b"abc"


class TestDeadline:
    """Tests for `_Deadline`."""

    def test_register_after_expiry(self) -> None:
        """Sockets registered after expiry are shut down at once."""
        client, server = socket.socketpair()
        try:
            with _Deadline(timeout=0.01) as deadline:
                time.sleep(0.2)
                assert deadline.expired
                deadline.register(client)
                assert client.recv(1) == b""
            with pytest.raises(RemoteFileError):
                deadline.remaining()
        finally:
            client.close()
            server.close()

    def test_shutdown_closed_socket(self) -> None:
        """Closed sockets are ignored when the timer expires."""
        client, server = socket.socketpair()
        client.close()
        server.close()
        with _Deadline(timeout=0.01) as deadline:
            deadline.register(client)
            time.sleep(0.2)
        assert deadline.expired
