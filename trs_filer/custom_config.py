"""Custom app config models."""

import ipaddress
import math
from typing import Annotated, List, Literal, Optional, Union

from foca.models.config import FOCABaseConfig
from foca.utils.misc import generate_id
from pydantic import Field, field_validator


class ServiceConfig(FOCABaseConfig):
    """Model for the public URL of the app, for building the `url` properties
    of tools and tool versions.

    Args:
        url_prefix: URL scheme of application.
        external_host: Name of application host.
        external_port: Port at which application is served.
        api_path: Base path at which API endpoints can be reached.

    Attributes:
        url_prefix: URL scheme of application.
        external_host: Name of application host.
        external_port: Port at which application is served.
        api_path: Base path at which API endpoints can be reached.

    Example:
        >>> ServiceConfig(
        ...     url_prefix='https',
        ...     external_host='trs.example.org',
        ...     external_port=443,
        ...     api_path='ga4gh/trs/v2'
        ... )
        ServiceConfig(url_prefix='https', external_host='trs.example.org', ext
        ernal_port=443, api_path='ga4gh/trs/v2')
    """

    url_prefix: str = "https"
    external_host: Optional[str] = None
    external_port: Optional[int] = None
    api_path: Optional[str] = None


class IdConfig(FOCABaseConfig):
    """Model for generating object identifiers.

    Args:
        charset: The allowed characters (duplicates are ignored); not an
            expression (e.g., `string.ascii_uppercase + string.digits`), as
            in previous versions.
        length: Length of generated identifiers.

    Attributes:
        charset: The allowed characters.
        length: Length of generated identifiers.

    Raises:
        pydantic.ValidationError: The character set is empty or an
            expression, or the length is not positive.

    Example:
        >>> IdConfig(
        ...     charset='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
        ...     length=6
        ... )
        IdConfig(charset='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=6)
    """

    charset: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    length: int = Field(default=6, gt=0)

    @field_validator("charset")
    @classmethod
    def check_charset(cls, value: str) -> str:
        """Check that identifiers can be generated from the character set.

        Uses the checks of FOCA's `generate_id()`, so that invalid character
        sets fail on startup instead of on requests.

        Args:
            value: Character set.

        Returns:
            The character set.

        Raises:
            ValueError: The character set is empty, or an expression.
        """
        try:
            generate_id(charset=value, length=1)
        except TypeError as exc:
            raise ValueError(str(exc)) from exc
        return value


class MetaVersionConfig(FOCABaseConfig):
    """Model for defining meta version control configurations.

    Args:
        init: Start index for the versioning. Defaults to `1`.
        increment: Incremental delta for the next version. Defaults to `1`.

    Attributes:
        init: Start index for the versioning. Defaults to `1`.
        increment: Incremental delta for the next version. Defaults to `1`.
    """

    init: int = 1
    increment: int = 1


class ToolConfig(FOCABaseConfig):
    """Model for tool config parameters.

    Args:
        id: Unique identifier definition for tools.
        meta_version: Version control config params.

    Attributes:
        id: Unique identifier definition for tools.
        meta_version: Version control config params.

    Example:
        >>> ToolConfig(
        ...     id=IdConfig(
        ...         length=6,
        ...         charset='abcdefghijklmnopqrstuvwxyz0123456789'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     )
        ... )
        ToolConfig(id=IdConfig(charset='abcdefghijklmnopqrstuvwxyz0123456789',
         length=6), meta_version=MetaVersionConfig(init=1, increment=1))
    """

    id: IdConfig = Field(default_factory=IdConfig)
    meta_version: MetaVersionConfig = Field(default_factory=MetaVersionConfig)


class VersionConfig(FOCABaseConfig):
    """Model for version config parameters.

    Args:
        id: Unique identifier definition for tool versions.
        meta_version: Version control config params.

    Attributes:
        id: Unique identifier definition for tool versions.
        meta_version: Version control config params.

    Example:
        >>> VersionConfig(
        ...     id=IdConfig(
        ...         length=6,
        ...         charset='abcdefghijklmnopqrstuvwxyz0123456789'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     )
        ... )
        VersionConfig(id=IdConfig(charset='abcdefghijklmnopqrstuvwxyz012345678
        9', length=6), meta_version=MetaVersionConfig(init=1, increment=1))
    """

    id: IdConfig = Field(default_factory=IdConfig)
    meta_version: MetaVersionConfig = Field(default_factory=MetaVersionConfig)


class ToolClassConfig(FOCABaseConfig):
    """Model for tool class config parameters.

    Args:
        id: Unique identifier definition for tool classes.
        meta_version: Version control config params.
        validation: Boolean to check if the class validations are enabled.
            Defaults to `False`.

    Attributes:
        id: Unique identifier definition for tool classes.
        meta_version: Version control config params.
        validation: Boolean to check if the class validations are enabled.
            Defaults to `False`.

    Example:
        >>> ToolClassConfig(
        ...     id=IdConfig(
        ...         length=6,
        ...         charset='abcdefghijklmnopqrstuvwxyz0123456789'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     ),
        ...     validation=False
        ... )
        ToolClassConfig(id=IdConfig(charset='abcdefghijklmnopqrstuvwxyz0123456
        789', length=6), meta_version=MetaVersionConfig(init=1, increment=1),
        validation=False)
    """

    id: IdConfig = Field(default_factory=IdConfig)
    meta_version: MetaVersionConfig = Field(default_factory=MetaVersionConfig)
    validation: bool = False


IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _parse_network(host: str) -> Optional[IPNetwork]:
    """Parse an IP address or network (CIDR notation).

    Args:
        host: Host name, IP address (IPv6 addresses also in brackets) or IP
            network.

    Returns:
        IP network (addresses as networks of one address), or `None` for
        host names.
    """
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return ipaddress.ip_network(host, strict=False)
    except ValueError:
        return None


class RemoteFilesConfig(FOCABaseConfig):
    """Model for retrieving the content of files from their URLs.

    When a tool version is registered with files that have a URL but no
    content, the content is retrieved from the URL and stored; files without
    stored content are retrieved when served as a zip archive.

    Args:
        schemes: Allowed URL schemes: `https` and, if needed, `http`.
        allowed_hosts: Host names (compared case-insensitively, without a
            trailing dot), IP addresses (IPv6 addresses also in brackets)
            and IP networks (CIDR notation) that may be retrieved from even
            though they are not public (e.g., for local setups). Other
            destinations must resolve to public addresses only: loopback,
            private, link-local, reserved and multicast addresses are
            refused.
        connect_timeout: Timeout for connecting to each address of a host,
            in seconds.
        read_timeout: Timeout for each read from a connection, in seconds.
        total_timeout: Timeout for retrieving a file, including redirects,
            in seconds; name resolution isn't limited by the timeouts.
        max_size: Maximum size of retrieved content, in bytes.
        max_redirects: Maximum number of redirects followed per file.

    Attributes:
        schemes: Allowed URL schemes.
        allowed_hosts: Host names, IP addresses and IP networks exempt from
            the destination checks, normalized.
        connect_timeout: Timeout for connecting, in seconds.
        read_timeout: Timeout for each read from a connection, in seconds.
        total_timeout: Timeout for retrieving a file, in seconds.
        max_size: Maximum size of retrieved content, in bytes.
        max_redirects: Maximum number of redirects followed per file.

    Raises:
        pydantic.ValidationError: No scheme is allowed, an allowed host is
            empty, a timeout is out of range or not finite, or a limit is
            out of range or not an integer.

    Example:
        >>> RemoteFilesConfig(allowed_hosts=['files.local', '10.0.0.0/8'])
        RemoteFilesConfig(schemes=['https'], allowed_hosts=['files.local', '1
        0.0.0.0/8'], connect_timeout=5.0, read_timeout=10.0, total_timeout=30
        .0, max_size=1048576, max_redirects=5)
    """

    schemes: List[Literal["http", "https"]] = ["https"]
    allowed_hosts: List[str] = []
    connect_timeout: float = Field(5.0, gt=0)
    read_timeout: float = Field(10.0, gt=0)
    total_timeout: float = Field(30.0, gt=0)
    max_size: Annotated[int, Field(strict=True, gt=0)] = 1048576
    max_redirects: Annotated[int, Field(strict=True, ge=0)] = 5

    @field_validator("connect_timeout", "read_timeout", "total_timeout")
    @classmethod
    def check_timeout(cls, value: float) -> float:
        """Check that a timeout is finite.

        Args:
            value: Timeout, in seconds.

        Returns:
            Timeout, in seconds.

        Raises:
            ValueError: The timeout is not finite.
        """
        if not math.isfinite(value):
            raise ValueError("Timeouts must be finite")
        return value

    @field_validator("schemes")
    @classmethod
    def check_schemes(cls, value: List[str]) -> List[str]:
        """Check that at least one scheme is allowed.

        Args:
            value: Allowed schemes.

        Returns:
            Allowed schemes.

        Raises:
            ValueError: No scheme is allowed.
        """
        if not value:
            raise ValueError("At least one scheme must be allowed")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_allowed_hosts(cls, value: List[str]) -> List[str]:
        """Normalize allowed hosts: IP networks in canonical form (without
        brackets), host names lowercase and without a trailing dot.

        Args:
            value: Allowed hosts.

        Returns:
            Normalized allowed hosts.

        Raises:
            ValueError: An allowed host is empty.
        """
        hosts = []
        for host in value:
            host = host.strip()
            network = _parse_network(host)
            if network is not None:
                hosts.append(str(network))
                continue
            host = host.rstrip(".").lower()
            if not host:
                raise ValueError("Allowed hosts must not be empty")
            hosts.append(host)
        return hosts

    @property
    def allowed_networks(self) -> List[IPNetwork]:
        """IP networks of the allowed hosts.

        Returns:
            Allowed IP networks (IP addresses as networks of one address).
        """
        networks = (_parse_network(host) for host in self.allowed_hosts)
        return [network for network in networks if network is not None]


class CustomConfig(FOCABaseConfig):
    """Model for custom configuration parameters.

    The service info is configured in FOCA's `service_info` section, no longer
    in `custom.service_info`, which is rejected.

    Args:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.

    Attributes:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.
    """

    service: ServiceConfig
    tool: ToolConfig = Field(default_factory=ToolConfig)
    version: VersionConfig = Field(default_factory=VersionConfig)
    toolclass: ToolClassConfig = Field(default_factory=ToolClassConfig)
    remote_files: RemoteFilesConfig = Field(default_factory=RemoteFilesConfig)
