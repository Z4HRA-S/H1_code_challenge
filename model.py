from datetime import datetime
from enum import Enum

from sqlalchemy import create_engine, ForeignKey, String, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


class Base(DeclarativeBase):
    pass


class OperationType(str, Enum):
    CREATE = "create"
    DELETE = "delete"


class OverallStatus(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
    UNKNOWN = "unknown"


class NodeOperationStatus(str, Enum):
    ROLLBACKED = "rollbacked"
    SUCCESS = "success"
    FAILED = "failed"
    UNKNOWN = "unknown"


class GroupStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Group(Base):
    __tablename__ = "group"

    group_id: Mapped[str] = mapped_column(String, primary_key=True)
    group_name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[GroupStatus] = mapped_column(String)


class Node(Base):
    __tablename__ = "node"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    host: Mapped[str] = mapped_column(String, unique=True)


class Operation(Base):
    __tablename__ = "operation"

    operation_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    group_id: Mapped[str] = mapped_column(ForeignKey("group.group_id"))
    operation: Mapped[OperationType] = mapped_column(String)
    overall_status: Mapped[OverallStatus] = mapped_column(String)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )


class NodeOperation(Base):
    __tablename__ = "node_operation"

    node_id: Mapped[str] = mapped_column(ForeignKey("node.node_id"), primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("operation.operation_id"), primary_key=True)
    status: Mapped[NodeOperationStatus] = mapped_column(String)



def create_db(url="sqlite:///cluster.db"):
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    return Session(engine)