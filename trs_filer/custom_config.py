"""Custom app config models."""

import string
from typing import Optional

from foca.models.config import FOCABaseConfig


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


class CustomConfig(FOCABaseConfig):
    """Model for custom configuration parameters.

    Args:
        service: Service config parameters.
        service_info: Service Info config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.

    Attributes:
        service: Service config parameters.
        service_info: Service Info config parameters.
        tool: Tool config parameters.
        version: Version config parameters.
        toolclass: Tool Class config parameters.
    """
    service: ServiceConfig
    service_info: ServiceInfoConfig
    tool: ToolConfig = ToolConfig()
    version: VersionConfig = VersionConfig()
    toolclass: ToolClassConfig = ToolClassConfig()
