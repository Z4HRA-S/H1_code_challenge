from group_operation import GroupOperation
from model import create_db, get_session
from model import (
    Operation,
    NodeOperation,
    Group,
    Node,
    OperationType,
    OverallStatus,
    NodeOperationStatus,
    GroupStatus,
)
import uuid


def get_last_group_id(session, group_name):
    group = (
        session.query(Group)
        .filter(
            Group.group_name == group_name,
            Group.status == "available",
        )
        .order_by(Group.version.desc())
        .first()
    )
    return group.group_id if group else None


def get_next_version(session, group_name):
    group = (
        session.query(Group)
        .filter(Group.group_name == group_name)
        .order_by(Group.version.desc())
        .first()
    )
    return group.version + 1 if group else 1


def register_nodes(session, nodes):
    for host in nodes:
        node = session.query(Node).filter(Node.host == host).first()
        if node is None:
            session.add(Node(node_id=str(uuid.uuid4()), host=host))

    session.commit()


async def main(operation, group_name, nodes):
    engine = create_db()

    with get_session(engine) as session:
        register_nodes(session, nodes)

        if operation == "create":
            group_id = str(uuid.uuid4())

        elif operation == "delete":
            group_id = get_last_group_id(session, group_name)

            if group_id is None:
                return {
                    "operation": operation,
                    "group_name": group_name,
                    "overall_state": "failed",
                    "error": "No available group found",
                }

        group_operation = GroupOperation(group_id)
        result = await group_operation.run(operation, nodes)

        update_database(session, group_name, group_id, operation, result)

        report(session, group_name, result)

        return result

def get_node_operation_status(state):
    if state in ("created", "deleted"):
        return NodeOperationStatus.SUCCESS
    elif state in ("not-created", "not-deleted"):
        return NodeOperationStatus.FAILED
    else:
        return NodeOperationStatus.UNKNOWN

def update_database(session, group_name, group_id, operation, result):
    if result["overall_state"]:
        overall_status = OverallStatus.SUCCESS
    elif result["rollback"]:
        overall_status = OverallStatus.FAIL
    else:
        overall_status = OverallStatus.UNKNOWN

    db_operation = Operation(
        group_id=group_id,
        operation=OperationType(operation),
        overall_status=overall_status,
    )
    session.add(db_operation)
    session.flush()

    node_results = {
        item["node"]: {**item, "status": get_node_operation_status(item["state"])}
        for item in result["operation_result"]
    }

    for item in result["rollback_result"]:
        node_operation_status = NodeOperationStatus.ROLLBACKED if item["success"] else NodeOperationStatus.UNKNOWN
        node_results[item["node"]] = {**item, "status": node_operation_status}

    for host, item in node_results.items():
        node = (
            session.query(Node)
            .filter(Node.host == host)
            .first()
        )

        if node is None:
            continue

        session.add(
            NodeOperation(
                node_id=node.node_id,
                operation_id=db_operation.operation_id,
                status=item["status"],
            )
        )

    if operation == "create":
        if any(item["success"] for item in result["operation_result"]):
            version = get_next_version(session, group_name)

            session.add(
                Group(
                    group_id=group_id,
                    group_name=group_name,
                    version=version,
                    status=(
                        GroupStatus.AVAILABLE
                        if result["overall_state"]
                        else GroupStatus.UNAVAILABLE
                    ),
                )
            )

    elif operation == "delete":
        group = session.get(Group, group_id)

        if group:
            if result["overall_state"]:
                session.delete(group)
            else:
                group.status = GroupStatus.UNAVAILABLE

    session.commit()


def report(session, group_name, result):
    pass