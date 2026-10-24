"""Integration tests."""

from copy import deepcopy
import json

import requests

from tests.mock_data import (
    MOCK_CONTAINER_FILE,
    MOCK_DESCRIPTOR_FILE,
    MOCK_FILES_LIST,
    MOCK_ID,
    MOCK_TEST_FILE,
    MOCK_TOOL,
    MOCK_TOOL_CLASS,
    MOCK_VERSION_NO_ID,
)

base_url = "http://localhost:8080/ga4gh/trs/v2"
headers = {"accept": "*/*", "Content-Type": "application/json"}


def test_post_service_info_not_allowed() -> None:
    """Test that `POST /service-info` is not served (service info is configured)."""
    endpoint = "/service-info"
    response = requests.post(base_url + endpoint, json={}, headers=headers)
    assert response.status_code == 405


def test_get_service_info_success() -> None:
    """Test `GET /service-info` for fetching the configured service info."""
    endpoint = "/service-info"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    service_info = json.loads(response.content)
    assert service_info["id"] == "org.example.trs-filer"
    assert service_info["type"] == {
        "group": "org.ga4gh",
        "artifact": "trs",
        "version": "2.0.1",
    }


def test_post_tool_success() -> None:
    """Test `POST /tools` for create tool objects."""
    endpoint = "/tools"
    response = requests.post(base_url + endpoint, json=MOCK_TOOL, headers=headers)
    assert response.status_code == 200


def test_post_tool_bad_request() -> None:
    """Test `POST /tools` for create tool objects with invalid payload."""
    endpoint = "/tools"
    response = requests.post(base_url + endpoint, json={}, headers=headers)
    assert response.status_code == 400


def test_get_tools_success() -> None:
    """Test `GET /tools` for retrieving tool list."""
    endpoint = "/tools"
    global test_obj_id, test_obj
    global test_obj_version_list, test_version_obj, test_version_obj_id
    response = requests.get(base_url + endpoint, headers=headers)
    obj_list = json.loads(response.content)
    test_obj = obj_list[0]
    test_obj_id = test_obj["id"]
    test_obj_version_list = test_obj["versions"]
    test_version_obj = test_obj_version_list[0]
    test_version_obj_id = test_version_obj["id"]
    assert response.status_code == 200
    assert isinstance(obj_list, list)


def test_get_tools_with_params_success() -> None:
    """Test `GET /tools` for retrieving tool list given param inputs."""
    endpoint = "/tools"
    params = {
        "id": "",
        "alias": "",
        "toolClass": "",
        "descriptorType": "CWL",
        "registry": "",
        "organization": "",
        "name": "",
        "toolname": "",
        "description": "",
        "author": "",
        "checker": False,
        "offset": None,
        "limit": 10,
    }
    response = requests.get(base_url + endpoint, headers=headers, params=params)
    assert response.status_code == 200
    assert isinstance(json.loads(response.content), list)


def test_get_tool_by_id_success() -> None:
    """Test `GET /tools/{id}` for retrieving tool by `id`."""
    endpoint = f"/tools/{test_obj_id}"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == test_obj


def test_get_tool_by_id_obj_not_found() -> None:
    """Test `GET /tools/{id}` for retrieving tool given invalid `id`."""
    endpoint = f"/tools/{MOCK_ID}"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_id_versions_success() -> None:
    """Test `GET /tools/{id}/versions` for retrieving version listing given
    the tool `id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == test_obj_version_list


def test_get_tool_version_by_id_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}` for retrieving version
    object given the tool `id` and `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == test_version_obj


def test_get_tool_version_by_id_obj_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}` for retrieving version
    object given invalid tool `id` or `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{MOCK_ID}"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_descriptor_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/descriptor` for
    retrieving descriptor given tool `id`, `version_id` and `type`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}/CWL/descriptor"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == MOCK_DESCRIPTOR_FILE["file_wrapper"]


def test_get_tool_descriptor_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/descriptor` for
    retrieving descriptor given invalid params.
    """
    endpoint = f"/tools/{MOCK_ID}/versions/{MOCK_ID}/CWL/descriptor"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_descriptor_given_relative_path_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/descriptor/
    {relative_path}` for retrieving descriptor given relative file_path.
    """
    relative_path = MOCK_DESCRIPTOR_FILE["tool_file"]["path"]
    endpoint = (
        f"/tools/{test_obj_id}/versions/{test_version_obj_id}/CWL/descriptor/"
        f"{relative_path}"
    )
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == MOCK_DESCRIPTOR_FILE["file_wrapper"]


def test_get_tool_descriptor_given_relative_path_obj_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/descriptor/
    {relative_path}` for retrieving descriptor given invalid relative
    file_path.
    """
    relative_path = "temp"
    endpoint = (
        f"/tools/{test_obj_id}/versions/{test_version_obj_id}/CWL/descriptor/"
        f"{relative_path}"
    )
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_tests_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/tests` for
    retrieving test json given tool `id`, `version_id` and `type`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}/CWL/tests"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == [MOCK_TEST_FILE["file_wrapper"]]


def test_get_tool_tests_obj_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/tests` for
    retrieving test json given invalid params.
    """
    endpoint = f"/tools/{MOCK_ID}/versions/{MOCK_ID}/CWL/tests"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_files_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/files` for
    retrieving file list given tool `id`, `version_id` and `type`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}/CWL/files"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == MOCK_FILES_LIST


def test_get_tool_files_obj_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/{type}/files` for
    retrieving file list given invalid params.
    """
    endpoint = f"/tools/{MOCK_ID}/versions/{MOCK_ID}/CWL/files"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_container_files_success() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/containerfile` for
    retrieving container file list given tool `id` and `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}/containerfile"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.content) == [MOCK_CONTAINER_FILE["file_wrapper"]]


def test_get_tool_container_files_obj_not_found() -> None:
    """Test `GET /tools/{id}/versions/{version_id}/containerfile` for
    retrieving container file list given invalid params.
    """
    endpoint = f"/tools/{MOCK_ID}/versions/{MOCK_ID}/containerfile"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_get_tool_classes_success() -> None:
    """Test `GET /toolClasses` for retrieving tool classes."""
    endpoint = "/toolClasses"
    response = requests.get(base_url + endpoint, headers=headers)
    assert response.status_code == 200
    assert isinstance(json.loads(response.content), list)


def test_tool_put_success() -> None:
    """Test `PUT /tools/{id}` for updating tool data given tool `id`."""
    endpoint = f"/tools/{test_obj_id}"
    response = requests.put(base_url + endpoint, json=MOCK_TOOL, headers=headers)
    assert response.status_code == 200


def test_tool_put_malformed_request() -> None:
    """Test `PUT /tools/{id}` for updating tool data given tool `id` and
    invalid json.
    """
    endpoint = f"/tools/{test_obj_id}"
    response = requests.put(base_url + endpoint, json={}, headers=headers)
    assert response.status_code == 400


def test_tool_version_post_success() -> None:
    """Test `POST /tools/{id}/versions` for adding tool version data given tool `id`."""
    endpoint = f"/tools/{test_obj_id}/versions"
    response = requests.post(
        base_url + endpoint, json=MOCK_VERSION_NO_ID, headers=headers
    )
    assert response.status_code == 200


def test_tool_version_post_malformed_request() -> None:
    """Test `POST /tools/{id}/versions` for adding tool version data given
    tool `id` and invalid json.
    """
    endpoint = f"/tools/{test_obj_id}/versions"
    response = requests.post(base_url + endpoint, json="", headers=headers)
    assert response.status_code == 400


def test_tool_version_put_success() -> None:
    """Test `PUT /tools/{id}/versions/{version_id}` for updating tool version
    data given tool `id` and `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}"
    response = requests.put(
        base_url + endpoint, json=MOCK_VERSION_NO_ID, headers=headers
    )
    assert response.status_code == 200


def test_tool_version_put_malformed_request() -> None:
    """Test `PUT /tools/{id}/versions/{version_id}` for updating tool version
    data given invalid json.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}"
    response = requests.put(base_url + endpoint, json="", headers=headers)
    assert response.status_code == 400


def test_tool_version_delete_success() -> None:
    """Test `DELETE /tools/{id}/versions/{version_id}` for deleting tool
    version data given tool `id` and `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 200


def test_tool_version_delete_obj_not_found() -> None:
    """Test `DELETE /tools/{id}/versions/{version_id}` for deleting tool
    version data given invalid `version_id`.
    """
    endpoint = f"/tools/{test_obj_id}/versions/{test_version_obj_id}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_tool_delete_success() -> None:
    """Test `DELETE /tools/{id}` for deleting tool data given tool `id`."""
    endpoint = f"/tools/{test_obj_id}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 200


def test_tool_delete_obj_not_found() -> None:
    """Test `DELETE /tools/{id}` for deleting tool data given invalid tool `id`."""
    endpoint = f"/tools/{test_obj_id}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 404


def test_tool_class_post_success() -> None:
    """Test `POST /toolClasses` for creating tool classes."""
    endpoint = "/toolClasses"
    mock_tool_class = deepcopy(MOCK_TOOL_CLASS)
    mock_tool_class.pop("id")
    response = requests.post(base_url + endpoint, json=mock_tool_class, headers=headers)
    assert response.status_code == 200
    global tool_class_id
    tool_class_id = json.loads(response.content)


def test_tool_class_post_malformed_request() -> None:
    """Test `POST /toolClasses` for creating tool classes given invalid payload."""
    endpoint = "/toolClasses"
    response = requests.post(base_url + endpoint, json="", headers=headers)
    assert response.status_code == 400


def test_tool_class_put_success() -> None:
    """Test `PUT /toolClasses` for creating tool classes given tool_class `id`."""
    endpoint = f"/toolClasses/{tool_class_id}"
    mock_tool_class = deepcopy(MOCK_TOOL_CLASS)
    mock_tool_class.pop("id")
    response = requests.put(base_url + endpoint, json=mock_tool_class, headers=headers)
    assert response.status_code == 200


def test_tool_class_put_malformed_request() -> None:
    """Test `PUT /toolClasses` for creating tool classes  given tool_class
    `id` and invalid payload.
    """
    endpoint = f"/toolClasses/{tool_class_id}"
    response = requests.put(base_url + endpoint, json="", headers=headers)
    assert response.status_code == 400


def test_tool_class_delete_success() -> None:
    """Test `DELETE /toolClasses/{id}` for deleting tool class data given
    tool_class `id`.
    """
    endpoint = f"/toolClasses/{tool_class_id}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 200


def test_tool_class_delete_obj_not_found() -> None:
    """Test `DELETE /toolClasses/{id}` for deleting tool class data given
    invalid tool_class `id`.
    """
    endpoint = f"/toolClasses/{MOCK_ID + MOCK_ID}"
    response = requests.delete(base_url + endpoint, headers=headers)
    assert response.status_code == 404
