"""Custom app config models."""

import ipaddress
import math
import string
from typing import List, Literal, Optional, Union

from foca.models.config import FOCABaseConfig
from pydantic import Field, conint, validator


class ServiceConfig(FOCABaseConfig):
    """Model for service configuration parameters for constructing tool
    and version `url` properties.

    Args:
        url_prefix: URL scheme of application.
        host_name: Name of application host.
        external_port: Port at which application is served.
        api_path: Base path at which API endpoints can be reached.

    Attributes:
        url_prefix: URL scheme of application.
        host_name: Name of application host.
        external_port: Port at which application is served.
        api_path: Base path at which API endpoints can be reached.

    Example:
        >>> ServiceConfig(
        ...     url_prefix='https',
        ...     external_host='trs-filer-alex.c03.k8s-popup.csc.fi',
        ...     external_port=443,
        ...     api_path='ga4gh/trs/v2'
        ... )
        ServiceConfig(url_prefix='https', external_host='trs-filer-alex.c03.k8
        s-popup.csc.fi', external_port=443, api_path='ga4gh/trs/v2')
    """
    url_prefix: str = "https"
    external_host: Optional[str] = None
    external_port: Optional[int] = None
    api_path: Optional[str] = None


class ServiceInfoTypeConfig(FOCABaseConfig):
    """Model for service info type config parameters.

    Args:
        group: Service info configuration group.
        artifact: Service info configuration artifact.
        version: Service info configuration version.

    Attributes:
        group: Service info configuration group.
        artifact: Service info configuration artifact.
        version: Service info configuration version.

    Example:
        >>> ServiceInfoTypeConfig(
        ...     group='TEMP_GROUP',
        ...     artifact='TEMP_ARTIFACT',
        ...     version='v1'
        ... )
        ServiceInfoTypeConfig(group='TEMP_GROUP', artifact='TEMP_ARTIFACT', ve
        rsion='v1')
    """
    group: str = "TEMP_GROUP"
    artifact: str = "TEMP_ARTIFACT"
    version: str = "v1"


class OrganisationConfig(FOCABaseConfig):
    """Model for organisation config parameters.

    Args:
        name: Maintainer parent organisation for the service. Set to `null`
            as default.
        url: Webpage URL with contact information for the parent organisation.
            Set to `null` as default.

    Attributes:
        name: Maintainer parent organisation for the service. Set to `null`
            as default.
        url: Webpage URL with contact information for the parent organisation.
            Set to `null` as default.

    Example:
        >>> OrganisationConfig(
        ...     name='Parent organization',
        ...     url='parent/abc'
        ... )
        OrganisationConfig(name='Parent organization', url='parent/abc')
    """
    name: Optional[str] = None
    url: Optional[str] = None


class ServiceInfoConfig(FOCABaseConfig):
    """Model for service info config parameters.

    Args:
        id: Unique identifier for the service. If `null`, new identifier will
            be created.
        name: Name for the service.
        type: Version control parameters for the service artifacts.
        description: Short hand description for the service usage.
        organization: Information regarding the parent organisation responsible
            for maintaining the service.
        contactUrl: Webpage URL with contact information for the service.
        documentationUrl: Webpage URL with documentation details for the
            service.
        createdAt: Service version creation timestamp.
        updatedAt: Service version last update timestamp.
        environment: Service deployment enviroment name.
        version: Service release stable version.

    Attributes:
        id: Unique identifier for the service. If `null`, new identifier will
            be created.
        name: Name for the service.
        type: Version control parameters for the service artifacts.
        description: Short hand description for the service usage.
        organization: Information regarding the parent organisation responsible
            for maintaining the service.
        contactUrl: Webpage URL with contact information for the service.
        documentationUrl: Webpage URL with documentation details for the
            service.
        createdAt: Service version creation timestamp.
        updatedAt: Service version last update timestamp.
        environment: Service deployment enviroment name.
        version: Service release stable version.

    Example:
        >>> ServiceInfoTypeConfig(
        ...     id='TEMPID1',
        ...     name='TEMP_STUB',
        ...     type=ServiceInfoTypeConfig(
        ...         group='TEMP_GROUP',
        ...         artifact='TEMP_ARTIFACT',
        ...         version='v1'
        ...     ),
        ...     description='Description of service.',
        ...     organization=OrganisationConfig(
        ...         name='Parent organization',
        ...         url='parent/abc'
        ...     ),
        ...     contactUrl='contact/abc',
        ...     documentationUrl='docs/abc',
        ...     createdAt='2020-01-01',
        ...     updatedAt='2020-01-01',
        ...     environment='ENV',
        ...     version='0.0.0'
        ... )
        ServiceInfoConfig(id='TEMPID1', name='TEMP_STUB', type=ServiceInfoType
        Config(group='TEMP_GROUP', artifact='TEMP_ARTIFACT', version='v1'), de
        scription='Description of service.', organization=OrganisationConfig(n
        ame='Parent organization', url='parent/abc'), contactUrl='contact/abc'
        , documentationUrl='docs/abc', createdAt='2020-01-01', updatedAt='2020
        -01-01', environment='ENV', version='0.0.0')
    """
    id: str
    name: Optional[str] = None
    type: ServiceInfoTypeConfig = ServiceInfoTypeConfig()
    description: Optional[str] = None
    organization: OrganisationConfig = OrganisationConfig()
    contactUrl: Optional[str] = None
    documentationUrl: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    environment: Optional[str] = None
    version: Optional[str] = None


class IdConfig(FOCABaseConfig):
    """Model for defining unique identifier for tools on TRS Filer.

    Args:
        charset: A string of allowed characters or an expression evaluating to
            a string of allowed characters.
        length: Length of returned string.

    Attributes:
        charset: A string of allowed characters or an expression evaluating to
            a string of allowed characters.
        length: Length of returned string.

    Example:
        >>> IdConfig(
        ...     charset='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
        ...     length=6
        ... )
        IdConfig(charset='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', length=6)
    """

    length: int = 6
    charset: str = string.ascii_uppercase + string.digits


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
        ...         charset='string.ascii_lowercase + string.digits'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     )
        ... )
        ToolConfig(id=IdConfig(length=6, charset='string.ascii_lowercase + str
        ing.digits'), meta_version=MetaVersionConfig(init=1, increment=1))
    """
    id: IdConfig = IdConfig()
    meta_version: MetaVersionConfig = MetaVersionConfig()


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
        ...         charset='string.ascii_lowercase + string.digits'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     )
        ... )
        VersionConfig(id=IdConfig(length=6, charset='string.ascii_lowercase +
        string.digits'), meta_version=MetaVersionConfig(init=1, increment=1))
    """
    id: IdConfig = IdConfig()
    meta_version: MetaVersionConfig = MetaVersionConfig()


class ToolClassConfig(FOCABaseConfig):
    """Model for version config parameters.

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
        ...         charset='string.ascii_lowercase + string.digits'
        ...     ),
        ...     meta_version=MetaVersionConfig(
        ...         init=1,
        ...         increment=1
        ...     ),
        ...     validation=False
        ... )
        ToolClassConfig(id=IdConfig(length=6, charset='string.ascii_lowercase
        + string.digits'), meta_version=MetaVersionConfig(init=1, increment=1)
        , validation=False)
    """
    id: IdConfig = IdConfig()
    meta_version: MetaVersionConfig = MetaVersionConfig()
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
    max_size: conint(strict=True, gt=0) = 1048576  # type: ignore[valid-type]
    max_redirects: conint(strict=True, ge=0) = 5  # type: ignore[valid-type]

    @validator("connect_timeout", "read_timeout", "total_timeout")
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

    @validator("schemes")
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

    @validator("allowed_hosts")
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

    Args:
        service: Service config parameters.
        service_info: Service Info config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.

    Attributes:
        service: Service config parameters.
        service_info: Service Info config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.
    """
    service: ServiceConfig
    service_info: ServiceInfoConfig
    tool: ToolConfig = ToolConfig()
    version: VersionConfig = VersionConfig()
    toolclass: ToolClassConfig = ToolClassConfig()
    remote_files: RemoteFilesConfig = RemoteFilesConfig()
