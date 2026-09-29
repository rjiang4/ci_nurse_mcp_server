from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_dir: Mapped[str | None] = mapped_column(String)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class TestResult(Base):
    """One row per test case from carbit.test_results.json."""

    __tablename__ = "test_results"
    __table_args__ = (UniqueConstraint("job_id", "test_case"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    test_case: Mapped[str] = mapped_column(String)
    result: Mapped[str] = mapped_column(String)
    voting: Mapped[bool] = mapped_column(Boolean, default=False)


class LogEntry(Base):
    """Unified runner (carbit.debug.json) + server (server_log_*.json) log line."""

    __tablename__ = "log_entries"
    __table_args__ = (
        Index("ix_log_job_tc_ts", "job_id", "test_case", "timestamp"),
        Index("ix_log_job_ts", "job_id", "timestamp"),
        Index("ix_log_job_level", "job_id", "level_no"),
        Index("ix_log_job_stage", "job_id", "stage"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"))
    source: Mapped[str] = mapped_column(String)  # "runner" | "server"
    seq: Mapped[int] = mapped_column(Integer)  # original order within the source file
    timestamp: Mapped[datetime] = mapped_column(DateTime)  # naive UTC
    level: Mapped[str] = mapped_column(String)
    level_no: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str | None] = mapped_column(String)
    test_case: Mapped[str | None] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    call_stack: Mapped[list | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String)
    # Runner lines prefixed "[Server Log]" duplicate entries already present in the server log.
    is_server_echo: Mapped[bool] = mapped_column(Boolean, default=False)


class PytestSuite(Base):
    __tablename__ = "pytest_suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"), index=True)
    source_file: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    tests: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    time: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[str | None] = mapped_column(String)
    hostname: Mapped[str | None] = mapped_column(String)


class PytestCase(Base):
    __tablename__ = "pytest_cases"
    __table_args__ = (Index("ix_pytest_job_tc_outcome", "job_id", "test_case", "outcome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id"))
    suite_id: Mapped[int] = mapped_column(ForeignKey("pytest_suites.id"))
    test_case: Mapped[str] = mapped_column(String)  # first segment of classname, links to test_results
    classname: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    time: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String)  # passed | failed | error | skipped
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text)
    system_out: Mapped[str | None] = mapped_column(Text)
    system_err: Mapped[str | None] = mapped_column(Text)


def init_db(db_url: str = "sqlite:///hil_reports.db") -> sessionmaker:
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
