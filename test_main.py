import pytest
from unittest.mock import AsyncMock, patch

from main import (
    get_last_group_id,
    get_next_version,
    get_node_operation_status,
    run,
    recover_unknown_operations,
    recovery_report,
    report,
)

from model import (
    Group,
    Node,
    Operation,
    NodeOperation,
    OverallStatus,
    NodeOperationStatus,
    GroupStatus,
    OperationType,
)

from model import create_db, get_session


@pytest.fixture
def engine():
    engine = create_db("sqlite:///:memory:")
    return engine


@pytest.fixture
def session(engine):
    with get_session(engine) as session:
        yield session

def test_group_helpers(session):
    group1 = Group(
        group_id="g1",
        group_name="customers",
        version=1,
        status=GroupStatus.AVAILABLE,
    )

    group2 = Group(
        group_id="g2",
        group_name="customers",
        version=2,
        status=GroupStatus.AVAILABLE,
    )

    unavailable = Group(
        group_id="g3",
        group_name="customers",
        version=3,
        status=GroupStatus.UNAVAILABLE,
    )

    session.add_all([group1, group2, unavailable])
    session.commit()

    assert get_last_group_id(session, "customers") == "g2"
    assert get_next_version(session, "customers") == 4
    assert get_last_group_id(session, "missing") is None
    assert get_next_version(session, "missing") == 1


@pytest.mark.parametrize(
    "state, expected",
    [
        ("created", NodeOperationStatus.SUCCESS),
        ("deleted", NodeOperationStatus.SUCCESS),
        ("not-created", NodeOperationStatus.FAILED),
        ("not-deleted", NodeOperationStatus.FAILED),
        ("unknown", NodeOperationStatus.UNKNOWN),
    ],
)
def test_get_node_operation_status(state, expected):
    assert get_node_operation_status(state) == expected


@pytest.mark.asyncio
async def test_run_create(engine):
    nodes = ["node1", "node2"]

    result = {
        "operation": "create",
        "operation_result": [
            {"node": "node1", "state": "created", "success": True},
            {"node": "node2", "state": "created", "success": True},
        ],
        "rollback": None,
        "rollback_result": [],
        "overall_state": True,
    }

    with patch("main.GroupOperation") as mock_group_operation:
        mock_group_operation.return_value.run = AsyncMock(
            return_value=result
        )

        returned = await run(
            engine,
            "create",
            "customers",
            nodes,
        )

    assert returned == result

    mock_group_operation.assert_called_once()
    mock_group_operation.return_value.run.assert_awaited_once_with(
        "create",
        nodes,
    )


@pytest.mark.asyncio
async def test_run_delete_without_available_group(engine):
    result = await run(
        engine,
        "delete",
        "customers",
        ["node1", "node2"],
    )

    assert result == {
        "operation": "delete",
        "group_name": "customers",
        "overall_state": "failed",
        "error": "No available group found",
        "operation_result": [],
        "rollback": None,
        "rollback_result": [],
    }



# This test is written by AI, and tests should not have side-effects yes. but I leave it here since the task is meant to take no more than 24 hours, 
@pytest.mark.asyncio
async def test_recover_unknown_operations(engine):
    # Prepare node
    with patch("main.GroupOperation") as mock_group_operation:
        group_operation = mock_group_operation.return_value

        group_operation.rollback = AsyncMock(
            return_value=[
                {
                    "node": "node1",
                    "state": "deleted",
                    "success": True,
                }
            ]
        )

        # The actual DB setup for an UNKNOWN operation is
        # done here so recovery can query it.
        from main import get_session

        with get_session(engine) as session:
            node = Node(
                node_id="n1",
                host="node1",
            )
            session.add(node)

            operation = Operation(
                group_id="g1",
                operation=OperationType.CREATE,
                overall_status=OverallStatus.UNKNOWN,
            )
            session.add(operation)
            session.flush()

            node_operation = NodeOperation(
                node_id="n1",
                operation_id=operation.operation_id,
                status=NodeOperationStatus.UNKNOWN,
            )
            session.add(node_operation)
            session.commit()

            operation_id = operation.operation_id

        results = await recover_unknown_operations(engine)

        assert len(results) == 1

        result = results[0]

        assert result["operation"] == OperationType.CREATE
        assert result["group_id"] == "g1"
        assert result["operation_id"] == operation_id
        assert result["overall_state"] is True
        assert result["rollback_result"] == [
            {
                "node": "node1",
                "state": "deleted",
                "success": True,
            }
        ]

        group_operation.rollback.assert_awaited_once_with(
            "delete",
            ["node1"],
        )

        with get_session(engine) as session:
            node_operation = session.get(
                NodeOperation,
                ( "n1", operation_id ),
            )

            operation = session.get(Operation, operation_id)

            assert node_operation.status == NodeOperationStatus.ROLLBACKED
            assert operation.overall_status == OverallStatus.FAIL

