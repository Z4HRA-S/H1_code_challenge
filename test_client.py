import pytest
import httpx
from unittest.mock import AsyncMock

from client import GroupOperation


def assert_node_result(result):
    assert set(result) == {"node", "state", "success"}
    assert isinstance(result["node"], str)
    assert result["state"] in {
        "created",
        "deleted",
        "not_created",
        "not_deleted",
        "unknown",
    }
    assert isinstance(result["success"], bool)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, http_method, path, status_code",
    [
        ("create", "post", "/v1/group/", 201),
        ("delete", "request", "/v1/group/", 200),
        ("get", "get", "/v1/group/g1/", 200),
    ],
)
async def test_send_request(method, http_method, path, status_code, monkeypatch):
    operation = GroupOperation("g1")

    async def fake_post(self, url, json):
        assert url == "http://node1/v1/group/"
        assert json == {"groupId": "g1"}
        return httpx.Response(status_code)

    async def fake_delete(self, method, url, json):
        assert method == "DELETE"
        assert url == "http://node1/v1/group/"
        assert json == {"groupId": "g1"}
        return httpx.Response(status_code)

    async def fake_get(self, url):
        assert url == "http://node1/v1/group/g1/"
        return httpx.Response(status_code)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "request", fake_delete)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    node, response = await operation.send_request(method, "http://node1")

    assert node == "http://node1"
    assert response.status_code == status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation, initial_status, get_status, expected_state, expected_success",
    [
        ("create", 201, None, "created", True),
        ("create", 500, 200, "created", True),
        ("create", 500, 404, "not_created", False),
        ("create", 500, 500, "unknown", False),
        ("delete", 200, None, "deleted", True),
        ("delete", 500, 404, "deleted", True),
        ("delete", 500, 200, "not_deleted", False),
        ("delete", 500, 500, "unknown", False),
    ],
)
async def test_process(
    operation,
    initial_status,
    get_status,
    expected_state,
    expected_success,
):
    group_operation = GroupOperation("g1")

    group_operation.send_request = AsyncMock(
        return_value=("http://node1", httpx.Response(get_status))
        if get_status is not None
        else None
    )

    result = await group_operation.process(
        operation,
        "http://node1",
        httpx.Response(initial_status),
    )

    assert_node_result(result)

    assert result == {
        "node": "http://node1",
        "state": expected_state,
        "success": expected_success,
    }

    if get_status is not None:
        group_operation.send_request.assert_awaited_once_with(
            "get",
            "http://node1",
        )
    else:
        group_operation.send_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_success():
    operation = GroupOperation("g1")

    responses = {
        "http://node1": httpx.Response(201),
        "http://node2": httpx.Response(201),
    }

    async def send_request(method, node):
        return node, responses[node]

    operation.send_request = AsyncMock(side_effect=send_request)

    result = await operation.run(
        "create",
        ["http://node1", "http://node2"],
    )

    assert result["operation"] == "create"
    assert result["overall_state"] is True
    assert result["rollback_result"] == []
    assert result["rollback"] is None

    assert len(result["operation_result"]) == 2

    for item in result["operation_result"]:
        assert_node_result(item)
        assert item["state"] == "created"
        assert item["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation, expected_operation, status_code, expected_state",
    [
        ("create", "delete", 200, "deleted"),
        ("delete", "create", 201, "created"),
    ],
)
async def test_rollback(
    operation,
    expected_operation,
    status_code,
    expected_state,
):
    group_operation = GroupOperation("g1")

    group_operation.send_request = AsyncMock(
        return_value=(
            "http://node1",
            httpx.Response(status_code),
        )
    )

    result = await group_operation.rollback(
        operation,
        ["http://node1"],
    )

    assert len(result) == 1
    assert_node_result(result[0])

    assert result[0] == {
        "node": "http://node1",
        "state": expected_state,
        "success": True,
    }

    group_operation.send_request.assert_awaited_once_with(
        expected_operation,
        "http://node1",
    )