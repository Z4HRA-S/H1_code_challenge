from group_operation import GroupOperation
from model import create_db, get_session, Group, Node
import uuid


def get_last_group_id(session, group_name):
    group = (
        session.query(Group)
        .filter(Group.group_name == group_name)
        .order_by(Group.version.desc())
        .first()
    )
    return group.group_id if group else None


def create_group(session, group_name):
    last_group = (
        session.query(Group)
        .filter(Group.group_name == group_name)
        .order_by(Group.version.desc())
        .first()
    )

    version = last_group.version + 1 if last_group else 1
    group_id = str(uuid.uuid4())

    group = Group(
        group_id=group_id,
        group_name=group_name,
        version=version,
        status="unavailable",
    )

    session.add(group)
    session.commit()

    return group


def register_nodes(session, nodes):
    for host in nodes:
        node = session.query(Node).filter(Node.host == host).first()
        if node is None:
            session.add(Node(node_id=str(uuid.uuid4()), host=host))

    session.commit()


async def main(operation, group_name, nodes):
    engine = create_db()

    with get_session(engine) as session:
        group = create_group(session, group_name)

        register_nodes(session, nodes)

        group_operation = GroupOperation(group.group_id)
        result = await group_operation.run(operation, nodes)

        update_database(session, group, nodes, result)

        report(session, group, result)

        return result


def update_database(session, group, nodes, result):
    pass


def report(session, group, result):
    pass