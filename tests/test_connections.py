"""Tests for FileConnection model — CRUD, defaults, table name, Base/Concrete subclassing."""

from __future__ import annotations

from sqlmodel import Session, SQLModel, select

from grover.models.connections import FileConnection, FileConnectionBase


class TestFileConnectionModel:
    def test_table_exists(self, engine):
        """grover_file_connections table is created by create_all."""
        assert "grover_file_connections" in engine.dialect.get_table_names(engine.connect())

    def test_defaults(self, session: Session):
        conn = FileConnection(source_path="/a.py", target_path="/b.py")
        session.add(conn)
        session.commit()
        session.refresh(conn)

        assert conn.id  # UUID string
        assert conn.source_path == "/a.py"
        assert conn.target_path == "/b.py"
        assert conn.type == ""
        assert conn.weight == 1.0
        assert conn.metadata_json == "{}"
        assert conn.created_at is not None

    def test_with_type_and_weight(self, session: Session):
        conn = FileConnection(
            source_path="/a.py",
            target_path="/b.py",
            type="imports",
            weight=0.5,
            metadata_json='{"module": "os"}',
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)

        assert conn.type == "imports"
        assert conn.weight == 0.5
        assert conn.metadata_json == '{"module": "os"}'

    def test_round_trip(self, session: Session):
        conn = FileConnection(
            source_path="/src/auth.py",
            target_path="/src/auth.py#login",
            type="contains",
        )
        session.add(conn)
        session.commit()

        result = session.exec(
            select(FileConnection).where(FileConnection.source_path == "/src/auth.py")
        ).first()
        assert result is not None
        assert result.target_path == "/src/auth.py#login"
        assert result.type == "contains"

    def test_multiple_edges_same_source(self, session: Session):
        for target in ["/b.py", "/c.py", "/d.py"]:
            session.add(FileConnection(source_path="/a.py", target_path=target, type="imports"))
        session.commit()

        results = session.exec(
            select(FileConnection).where(FileConnection.source_path == "/a.py")
        ).all()
        assert len(results) == 3

    def test_base_subclass_custom_table(self, engine):
        """Custom table name via subclassing FileConnectionBase."""

        class CustomConnection(FileConnectionBase, table=True):
            __tablename__ = "custom_connections"

        SQLModel.metadata.create_all(engine)
        tables = engine.dialect.get_table_names(engine.connect())
        assert "custom_connections" in tables

    def test_unique_ids(self, session: Session):
        conn1 = FileConnection(source_path="/a.py", target_path="/b.py")
        conn2 = FileConnection(source_path="/a.py", target_path="/c.py")
        session.add_all([conn1, conn2])
        session.commit()
        assert conn1.id != conn2.id


class TestFileConnectionExports:
    def test_importable_from_models(self):
        from grover.models import FileConnection, FileConnectionBase

        assert FileConnection is not None
        assert FileConnectionBase is not None
