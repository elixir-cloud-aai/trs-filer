"""Custom app config models."""

import ipaddress
import math
from typing import Annotated, Literal, Self

from foca.models.config import FOCABaseConfig
from foca.utils.misc import generate_id
from pydantic import Field, field_validator, model_validator


class ServiceConfig(FOCABaseConfig):
    """Model for the public URL of the app.

    The URL is used for building the `url` properties of tools and tool
    versions.

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
    external_host: str | None = None
    external_port: int | None = None
    api_path: str | None = None


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


class ToolMetaVersionConfig(MetaVersionConfig):
    """Model for the meta version configuration of tools.

    Args:
        init: Start index for the versioning. Defaults to `1`.
        increment: Incremental delta for the next version. Defaults to `1`.
        on_version_change: Whether adding, replacing or deleting a version of
            a tool increments the tool's meta version, too. Defaults to
            `True`.

    Attributes:
        init: Start index for the versioning. Defaults to `1`.
        increment: Incremental delta for the next version. Defaults to `1`.
        on_version_change: Whether adding, replacing or deleting a version of
            a tool increments the tool's meta version, too. Defaults to
            `True`.
    """

    on_version_change: bool = True


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
        ...     meta_version=ToolMetaVersionConfig(
        ...         init=1,
        ...         increment=1,
        ...         on_version_change=True
        ...     )
        ... )
        ToolConfig(id=IdConfig(charset='abcdefghijklmnopqrstuvwxyz0123456789',
         length=6), meta_version=ToolMetaVersionConfig(init=1, increment=1,
         on_version_change=True))
    """

    id: IdConfig = Field(default_factory=IdConfig)
    meta_version: ToolMetaVersionConfig = Field(default_factory=ToolMetaVersionConfig)


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
        validation: Deprecated: whether tools must have a stored tool
            class; `True` sets `custom.access_control.tool_classes` to
            `controlled` (cf. `CustomConfig`), with a warning on startup.
            Removed in the next breaking release. Defaults to `False`.

    Attributes:
        id: Unique identifier definition for tool classes.
        meta_version: Version control config params.
        validation: Deprecated: whether tools must have a stored tool class.

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


IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _parse_network(host: str) -> IPNetwork | None:
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

    schemes: list[Literal["http", "https"]] = Field(default=["https"])
    allowed_hosts: list[str] = Field(default=[])
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=10.0, gt=0)
    total_timeout: float = Field(default=30.0, gt=0)
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
    def check_schemes(cls, value: list[str]) -> list[str]:
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
    def normalize_allowed_hosts(cls, value: list[str]) -> list[str]:
        """Normalize allowed hosts.

        IP networks are put in canonical form (without brackets), host names
        in lowercase and without a trailing dot.

        Args:
            value: Allowed hosts.

        Returns:
            Normalized allowed hosts.

        Raises:
            ValueError: An allowed host is empty.
        """
        hosts = []
        for entry in value:
            stripped = entry.strip()
            network = _parse_network(stripped)
            if network is not None:
                hosts.append(str(network))
                continue
            host = stripped.rstrip(".").lower()
            if not host:
                raise ValueError("Allowed hosts must not be empty")
            hosts.append(host)
        return hosts

    @property
    def allowed_networks(self) -> list[IPNetwork]:
        """IP networks of the allowed hosts.

        Returns:
            Allowed IP networks (IP addresses as networks of one address).
        """
        networks = (_parse_network(host) for host in self.allowed_hosts)
        return [network for network in networks if network is not None]


ToolClassesMode = Literal["open", "controlled", "moderated"]


class AccessControlConfig(FOCABaseConfig):
    """Model for access control settings of the app.

    Modelled on the service types of Cloud Registry
    (`custom.access_control.service_types`), with the same modes and the
    same default.

    Args:
        tool_classes: Who may add tool classes: `open` (the default), any
            authenticated user, explicitly (`POST /toolClasses`, `PUT
            /toolClasses/{id}` with new identifiers) or by registering a tool
            with a new tool class; `controlled`, only admins, and tools of
            other users must have a stored tool class; `moderated`, any
            authenticated user, but tool classes of users other than admins
            are pending until an admin approves them, and so are the tools
            that have them (see `trs_filer.ga4gh.trs.tool_classes`).
        max_unused_tool_classes: How many tool classes that no tool has a
            user other than an admin may have added (as
            `max_unused_service_types` of Cloud Registry): further ones are
            refused (`409 Conflict`); unlimited if `None`, only admins add
            tool classes if `0`. Defaults to `10`.

    Attributes:
        tool_classes: Who may add tool classes.
        max_unused_tool_classes: How many unused tool classes a user other
            than an admin may have added.

    Raises:
        pydantic.ValidationError: `tool_classes` is not `open`, `controlled`
            or `moderated`, or `max_unused_tool_classes` is not a
            non-negative integer or `None`.

    Example:
        >>> AccessControlConfig(tool_classes='moderated')
        AccessControlConfig(tool_classes='moderated', max_unused_tool_classes=10)
    """

    tool_classes: ToolClassesMode = "open"
    max_unused_tool_classes: Annotated[int, Field(ge=0)] | None = 10


class IoSchemaConfig(FOCABaseConfig):
    """Model for GA4GH I/O Schema files (experimental).

    I/O Schemas are files of type `OTHER` named `ga4gh-io.schema.json` (see
    `trs_filer.io_schema` and `docs/io-schema.md`); they are stored and
    served like other files with either setting.

    Args:
        validation: Whether I/O Schema files are checked on registration,
            against the vendored meta-schema of the GA4GH I/O Profile 0.3.0;
            invalid ones are rejected with `400 Bad Request`. Defaults to
            `False`.
        timeout: Time limit of checking an I/O Schema file, in seconds
            (validation takes time that grows with the size of schemas);
            files not checked within it are rejected. Defaults to `10`.

    Attributes:
        validation: Whether I/O Schema files are checked on registration.
        timeout: Time limit of checking an I/O Schema file, in seconds.

    Raises:
        pydantic.ValidationError: The time limit is not positive, or not
            finite.

    Example:
        >>> IoSchemaConfig(validation=True)
        IoSchemaConfig(validation=True, timeout=10.0)
    """

    validation: bool = False
    timeout: float = Field(default=10.0, gt=0, allow_inf_nan=False)


class S3StorageConfig(FOCABaseConfig):
    """Model for the connection to S3-compatible object storage.

    Only the S3 API is used, so any S3-compatible server or service works.
    Credentials are never part of the config: they are taken from the
    environment by boto3's default credential chain (e.g., the variables
    `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, from a Secret).

    Args:
        bucket: Name of the bucket, which must exist.
        endpoint_url: URL of the S3 API (e.g., `https://s3.example.org`);
            if not set, boto3's default (AWS, or the environment variable
            `AWS_ENDPOINT_URL_S3` or `AWS_ENDPOINT_URL`).
        region: Region of the bucket; if not set, boto3's default (e.g., the
            environment variable `AWS_REGION`).
        prefix: Prefix of the keys of the objects (e.g., `trs-filer/`), so
            that a bucket can be shared.
        addressing_style: Addressing of the bucket: `path`
            (`<endpoint>/<bucket>/<key>`, which most self-hosted servers
            need), `virtual` (`<bucket>.<endpoint>/<key>`) or `auto`
            (boto3's choice).
        presigned_urls: Whether files are served via presigned URLs of the
            objects instead of through the app (see `docs/configuration.md`).
        presigned_url_expiry: Validity of presigned URLs, in seconds (at
            most 7 days, the limit of the S3 API).
        connect_timeout: Timeout for connecting to the S3 API, in seconds.
        read_timeout: Timeout for each read from a connection, in seconds.

    Attributes:
        bucket: Name of the bucket.
        endpoint_url: URL of the S3 API.
        region: Region of the bucket.
        prefix: Prefix of the keys of the objects.
        addressing_style: Addressing of the bucket.
        presigned_urls: Whether files are served via presigned URLs.
        presigned_url_expiry: Validity of presigned URLs, in seconds.
        connect_timeout: Timeout for connecting to the S3 API, in seconds.
        read_timeout: Timeout for each read from a connection, in seconds.

    Raises:
        pydantic.ValidationError: The bucket is empty, the endpoint URL is
            not an HTTP(S) URL, the validity of presigned URLs is out of
            range, or a timeout is not positive or not finite.

    Example:
        >>> S3StorageConfig(bucket='trs-files', endpoint_url='https://s3.example.org')
        S3StorageConfig(bucket='trs-files', endpoint_url='https://s3.example.org',
         region=None, prefix='', addressing_style='path', presigned_urls=False,
         presigned_url_expiry=300, connect_timeout=5.0, read_timeout=10.0)
    """

    bucket: str = Field(min_length=1)
    endpoint_url: str | None = None
    region: str | None = None
    prefix: str = ""
    addressing_style: Literal["auto", "path", "virtual"] = "path"
    presigned_urls: bool = False
    presigned_url_expiry: Annotated[int, Field(strict=True, ge=1, le=604800)] = 300
    connect_timeout: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    read_timeout: float = Field(default=10.0, gt=0, allow_inf_nan=False)

    @field_validator("endpoint_url")
    @classmethod
    def check_endpoint_url(cls, value: str | None) -> str | None:
        """Check that the endpoint URL is an HTTP(S) URL.

        Args:
            value: Endpoint URL, or `None` for boto3's default.

        Returns:
            The endpoint URL.

        Raises:
            ValueError: The endpoint URL is not an HTTP(S) URL.
        """
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("The endpoint URL must start with http:// or https://")
        return value


class StorageConfig(FOCABaseConfig):
    """Model for the storage of the content of files.

    Args:
        backend: Where the content of files registered from now on is stored:
            `mongodb` (the default), with the other data of tools, or `s3`,
            in S3-compatible object storage (`s3`). Files stay where they
            were stored; files in object storage can be read as long as `s3`
            is set, also with backend `mongodb`.
        s3: Connection to S3-compatible object storage; required for backend
            `s3`.

    Attributes:
        backend: Where the content of new files is stored.
        s3: Connection to S3-compatible object storage.

    Raises:
        pydantic.ValidationError: The backend is `s3`, but `s3` is not set.

    Example:
        >>> StorageConfig(backend='s3', s3=S3StorageConfig(bucket='trs-files'))
        StorageConfig(backend='s3', s3=S3StorageConfig(bucket='trs-files', ...))
    """

    backend: Literal["mongodb", "s3"] = "mongodb"
    s3: S3StorageConfig | None = None

    @model_validator(mode="after")
    def check_s3(self) -> "StorageConfig":
        """Check that object storage is configured for backend `s3`.

        Returns:
            The storage config.

        Raises:
            ValueError: The backend is `s3`, but `s3` is not set.
        """
        if self.backend == "s3" and self.s3 is None:
            raise ValueError("custom.storage.s3 must be set for backend 's3'")
        return self


class CustomConfig(FOCABaseConfig):
    """Model for custom configuration parameters.

    The service info is configured in FOCA's `service_info` section, no longer
    in `custom.service_info`, which is rejected. The deprecated
    `toolclass.validation: true` sets `access_control.tool_classes` to
    `controlled` (cf. `apply_tool_class_validation()`).

    Args:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.
        access_control: Access control settings of the app.
        io_schema: Checks of GA4GH I/O Schema files (experimental).
        storage: Storage of the content of files.

    Attributes:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
        remote_files: Parameters for retrieving files from their URLs.
        access_control: Access control settings of the app.
        io_schema: Checks of GA4GH I/O Schema files (experimental).
        storage: Storage of the content of files.
    """

    service: ServiceConfig
    tool: ToolConfig = Field(default_factory=ToolConfig)
    version: VersionConfig = Field(default_factory=VersionConfig)
    toolclass: ToolClassConfig = Field(default_factory=ToolClassConfig)
    remote_files: RemoteFilesConfig = Field(default_factory=RemoteFilesConfig)
    access_control: AccessControlConfig = Field(default_factory=AccessControlConfig)
    io_schema: IoSchemaConfig = Field(default_factory=IoSchemaConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @model_validator(mode="after")
    def apply_tool_class_validation(self) -> Self:
        """Map the deprecated `toolclass.validation` to the mode `controlled`.

        `toolclass.validation: true` required stored tool classes for tools,
        as the mode `controlled` does (cf. `AccessControlConfig`), which
        replaces it: it sets the mode `open` to `controlled`; the app warns
        of it on startup (cf. `trs_filer.app.create_app()`). The message
        doesn't name the values, so that FOCA shows it on startup (FOCA
        leaves out messages that quote invalid values).

        Returns:
            The config, with mode `controlled` if `toolclass.validation` is
            true.

        Raises:
            ValueError: `toolclass.validation` is true with mode `moderated`,
                which would contradict each other.
        """
        if not self.toolclass.validation:
            return self
        if self.access_control.tool_classes == "moderated":
            raise ValueError(
                "the deprecated 'toolclass.validation' can't be combined with "
                "the mode 'moderated' of 'access_control.tool_classes'; remove "
                "'toolclass.validation'"
            )
        self.access_control.tool_classes = "controlled"
        return self
