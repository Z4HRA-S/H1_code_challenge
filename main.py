from group_operation import GroupOperation
from model import create_db, get_session, Group, Operation, Node

def update_database(session, group, nodes, result):
    pass


def report(session, group_id, result):
    pass

async def main(operation, group_id, nodes):
    engine = create_db()

    with get_session(engine) as session:
        group = session.get(Group, group_id)

        if group is None:
            group = Group(group_id=group_id, version=1, status="unavailable")
            session.add(group)
        else:
            group.version += 1

        session.commit()
        group_operation = GroupOperation(group_id)
        result = await group_operation.run(operation, nodes,)

        update_database(session, group, nodes, result)

        report(session, group_id, result)

        return result