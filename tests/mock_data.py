"""Mock data for testing."""

from copy import deepcopy

MOCK_ID = "mock_id"
MOCK_ID_ONE_CHAR = "A"
CHARSET_EXPRESSION = 'string.digits'
INDEX_CONFIG = {
    'keys': [('id', 1)]
}
COLLECTION_CONFIG = {
    'indexes': [INDEX_CONFIG],
}
DB_CONFIG = {
    'collections': {
        'service_info': COLLECTION_CONFIG,
        'tools': COLLECTION_CONFIG,
        'files': COLLECTION_CONFIG,
    },
}
MONGO_CONFIG = {
    'host': 'mongodb',
    'port': 27017,
    'dbs': {
        'trsStore': DB_CONFIG,
    },
}
TOOL_VERSION_CONFIG = {
    "id": {
        "charset": CHARSET_EXPRESSION,
        "length": 6,
    },
    "meta_version": {
        "init": 1,
        "increment": 1,
    },
}
TOOL_VERSION_CONFIG_CHARSET_LITERAL = deepcopy(TOOL_VERSION_CONFIG)
TOOL_VERSION_CONFIG_CHARSET_LITERAL['id']['charset'] = MOCK_ID_ONE_CHAR
TOOL_VERSION_CONFIG_ONE_ID = deepcopy(TOOL_VERSION_CONFIG_CHARSET_LITERAL)
TOOL_VERSION_CONFIG_ONE_ID['id']['length'] = 1
SERVICE_CONFIG = {
    "url_prefix": "http",
    "external_host": "1.2.3.4",
    "external_port": 80,
    "api_path": "ga4gh/trs/v2",
}
SERVICE_INFO_CONFIG = {
    "contactUrl": "mailto:support@example.com",
    "createdAt": "2019-06-04T12:58:19Z",
    "description": "This service provides...",
    "documentationUrl": "https://docs.myservice.example.com",
    "environment": "test",
    "id": "org.ga4gh.myservice",
    "name": "My project",
    "organization": {
        "name": "My organization",
        "url": "https://example.com"
    },
    "type": {
        "artifact": "beacon",
        "group": "org.ga4gh",
        "version": "1.0.0"
    },
    "updatedAt": "2019-06-04T12:58:19Z",
    "version": "1.0.0"
}
ENDPOINT_CONFIG = {
    "tool": TOOL_VERSION_CONFIG,
    "version": TOOL_VERSION_CONFIG,
    "service": SERVICE_CONFIG,
    "service_info": SERVICE_INFO_CONFIG,
}
ENDPOINT_CONFIG_CHARSET_LITERAL = deepcopy(ENDPOINT_CONFIG)
ENDPOINT_CONFIG_CHARSET_LITERAL['tool'] = TOOL_VERSION_CONFIG_CHARSET_LITERAL
ENDPOINT_CONFIG_CHARSET_LITERAL['version'] = (
    TOOL_VERSION_CONFIG_CHARSET_LITERAL
)
ENDPOINT_CONFIG_ONE_ID = deepcopy(ENDPOINT_CONFIG)
ENDPOINT_CONFIG_ONE_ID['tool'] = TOOL_VERSION_CONFIG_ONE_ID
ENDPOINT_CONFIG_ONE_ID['version'] = TOOL_VERSION_CONFIG_ONE_ID
HEADERS_PAGINATION = {
    'next_page': None,
    'last_page': None,
    'self_link': None,
    'current_offset': None,
    'current_limit': None,
}
HEADERS_SERVICE_INFO = {
    'Content-type': 'application/json',
    'Location': (
        f"{SERVICE_CONFIG['url_prefix']}://{SERVICE_CONFIG['external_host']}:"
        f"{SERVICE_CONFIG['external_port']}/{SERVICE_CONFIG['api_path']}/"
        "service-info"
    )
}
MOCK_FILES = [
    {
        "fileWrapper": {
            "checksum": [
                {
                    "checksum": "ea2a5db69bd20a42976838790bc29294df3af02b",
                    "type": "sha1"
                }
            ],
            "content": "string",
            "url": "sfdlmedl"
        },
        "toolFile": {
            "file_type": "TEST_FILE",
            "path": "string"
        }
    },
]
MOCK_FILES_CONTENT_URL_MISSING = deepcopy(MOCK_FILES)
del MOCK_FILES_CONTENT_URL_MISSING[0]['fileWrapper']['content']
del MOCK_FILES_CONTENT_URL_MISSING[0]['fileWrapper']['url']
MOCK_FILES_CHECKSUM_MISSING = deepcopy(MOCK_FILES)
del MOCK_FILES_CHECKSUM_MISSING[0]['fileWrapper']['checksum']
MOCK_IMAGES = [
    {
        "checksum": [
            {
                "checksum": (
                    "77af4d6b9913e693e8d0b4b294fa62ade6054e6b2f1f"
                    "fb617ac955dd63fb0182"
                ),
                "type": "sha256"
            }
        ],
        "image_name": "string",
        "image_type": "Docker",
        "registry_host": "string",
        "size": 0,
        "updated": "string"
    }
]
MOCK_VERSION_NO_ID = {
    "author": [
        "string"
    ],
    "descriptor_type": [
        "CWL"
    ],
    "files": MOCK_FILES,
    "images": MOCK_IMAGES,
    "included_apps": [
        "https://bio.tools/tool/mytum.de/SNAP2/1",
        "https://bio.tools/bioexcel_seqqc"
    ],
    "is_production": True,
    "meta_version": "string",
    "name": "string",
    "signed": True,
    "verified_source": [
        "string"
    ]
}
MOCK_VERSION_ID = deepcopy(MOCK_VERSION_NO_ID)
MOCK_VERSION_ID['id'] = MOCK_ID
MOCK_TOOL_NO_VERSION = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "has_checker": True,
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "toolclass": {
        "description": "string",
        "id": "string",
        "name": "string"
    },
}
MOCK_TOOL = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "has_checker": True,
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "toolclass": {
        "description": "string",
        "id": "string",
        "name": "string"
    },
    "versions": [
        MOCK_VERSION_NO_ID,
    ],
}
MOCK_TOOL_VERSION_ID = {
    "aliases": [
        "630d31c3-381e-488d-b639-ce5d047a0142",
        "dockstore.org:630d31c3-381e-488d-b639-ce5d047a0142",
        "bio.tools:630d31c3-381e-488d-b639-ce5d047a0142"
    ],
    "checker_url": "string",
    "description": "string",
    "has_checker": True,
    "meta_version": "0.0.0",
    "name": "string",
    "organization": "string",
    "toolclass": {
        "description": "string",
        "id": "string",
        "name": "string"
    },
    "versions": [
        MOCK_VERSION_ID,
    ],
}
MOCK_TOOL_DUPLICATE_VERSION_IDS = deepcopy(MOCK_TOOL)
MOCK_TOOL_DUPLICATE_VERSION_IDS['versions'] = [
    MOCK_VERSION_ID,
    MOCK_VERSION_ID,
]
