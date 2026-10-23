"""Custom app config models."""

from typing import Optional

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


class CustomConfig(FOCABaseConfig):
    """Model for custom configuration parameters.

    The service info is configured in FOCA's `service_info` section, no longer
    in `custom.service_info`, which is rejected.

    Args:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.

    Attributes:
        service: Service config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
    """
    service: ServiceConfig
    tool: ToolConfig = Field(default_factory=ToolConfig)
    version: VersionConfig = Field(default_factory=VersionConfig)
    toolclass: ToolClassConfig = Field(default_factory=ToolClassConfig)
