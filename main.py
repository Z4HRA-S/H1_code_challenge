from group_operation import GroupOperation
from model import create_db, get_session, Group, Node
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


def update_database(session, group_name, group_id, operation, result):
    pass


def report(session, group_name, result):
    pass