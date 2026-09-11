from client import GroupOperation
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
import asyncio
import yaml


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

from collections import defaultdict


async def recover_unknown_operations(engine):
    with get_session(engine) as session:
        unknown_operations = (
            session.query(
                Operation.operation_id,
                Operation.group_id,
                Operation.operation,
                Node.host,
            )
            .join(
                NodeOperation,
                Operation.operation_id == NodeOperation.operation_id,
            )
            .join(
                Node,
                Node.node_id == NodeOperation.node_id,
            )
            .filter(
                Operation.overall_status == OverallStatus.UNKNOWN,
                NodeOperation.status == NodeOperationStatus.UNKNOWN,
            )
            .all()
        )

        groups = defaultdict(lambda: defaultdict(lambda: {
            "operation": None,
            "nodes": [],
        }))

        for operation_id, group_id, operation, host in unknown_operations:
            groups[group_id][operation_id]["operation"] = operation
            groups[group_id][operation_id]["nodes"].append(host)
        
        total_result=[]

        for group_id, operations in groups.items():
            group_operation = GroupOperation(group_id)

            for operation_id, data in operations.items():
                rollback_operation = (
                    "delete"
                    if data["operation"] == OperationType.CREATE
                    else "create"
                )

                result = await group_operation.rollback(
                    rollback_operation,
                    data["nodes"],
                )

                for item in result:
                    node_operation = (
                        session.query(NodeOperation)
                        .join(Node, Node.node_id == NodeOperation.node_id)
                        .filter(
                            NodeOperation.operation_id == operation_id,
                            Node.host == item["node"],
                        )
                        .first()
                    )

                    if node_operation is None:
                        continue

                    node_operation.status = (
                        NodeOperationStatus.ROLLBACKED
                        if item["success"]
                        else NodeOperationStatus.UNKNOWN
                    )

                remaining_unknown = (
                    session.query(NodeOperation)
                    .filter(
                        NodeOperation.operation_id == operation_id,
                        NodeOperation.status == NodeOperationStatus.UNKNOWN,
                    )
                    .count()
                )

                if remaining_unknown == 0:
                    operation_record = session.get(Operation, operation_id)
                    operation_record.overall_status = OverallStatus.FAIL

                session.commit()
                total_result.append(result)

    return total_result


def recovery_report(results):
    print("\n" + "=" * 50)
    print("RECOVERY REPORT")
    print("=" * 50)

    for i, result in enumerate(results, 1):
        rollback_results = result["rollback_result"]

        recovered_count = sum(
            item["success"]
            for item in rollback_results
        )

        unknown_nodes = [
            item["node"]
            for item in rollback_results
            if not item["success"]
        ]

        print(
            f"\nRecovery {i}: "
            f"{result['operation']} - "
            f"group {result['group_id']}"
        )
        print(f"  Recovered : {recovered_count}")
        print(f"  Unknown   : {len(unknown_nodes)}")

        if unknown_nodes:
            print(f"  Nodes     : {unknown_nodes}")

    print("\n" + "=" * 50)


def report(results):
    print("\n" + "=" * 50)
    print("OPERATION REPORT")
    print("=" * 50)

    for i, result in enumerate(results, 1):
        operation_results = result["operation_result"]
        rollback_results = result["rollback_result"]

        rollback_nodes = {
            item["node"]
            for item in rollback_results
            if item["success"]
        }

        unknown_nodes = set()

        for item in operation_results:
            if item["node"] in rollback_nodes:
                continue

            if item["state"] == "unknown":
                unknown_nodes.add(item["node"])

        for item in rollback_results:
            if not item["success"]:
                unknown_nodes.add(item["node"])

        success_count = sum(
            item["success"]
            for item in operation_results
            if item["node"] not in rollback_nodes
        )

        fail_count = sum(
            not item["success"]
            for item in operation_results
            if item["node"] not in rollback_nodes
            and item["state"] != "unknown"
        )

        rollback_count = len(rollback_nodes)

        print(f"\nOperation {i}: {result['operation']} - {result['group_name']}")
        print(f"  Success  : {success_count}")
        print(f"  Failed   : {fail_count}")
        print(f"  Rollback : {rollback_count}")
        print(f"  Overall  : {result['overall_state']}")

        if unknown_nodes:
            print(f"  Unknown  : {list(unknown_nodes)}")

    print("\n" + "=" * 50)



async def run(engine, operation, group_name, nodes):
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

        return result


def load_config(path):
    with open(path, "r") as file:
        return yaml.safe_load(file)


async def main(config_path):
    config = load_config(config_path)
    engine = create_db()
    nodes = config["nodes"]

    results = []

    for operation in config["operations"]:
        result = await run(
            engine = engine,
            operation=operation["operation"],
            group_name=operation["group_name"],
            nodes=nodes,
        )
        result["group_name"] = operation["group_name"]
        results.append(result)

    report(results)

    recovered_results = await recover_unknown_operations(engine)
    recovery_report(recovered_results)

    return results


if __name__ == "__main__":
    asyncio.run(main("config.yaml"))