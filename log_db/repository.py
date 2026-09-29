from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import sessionmaker

from log_db import JobArtifacts
from log_db.ingest import LEVEL_NO
from log_db.models import Job, LogEntry, PytestCase, PytestSuite, TestResult
from module.artifactory_helper import fetch_artifact_bytes, query_agent_log_url

def _log_to_dict(e: LogEntry, include_call_stack: bool) -> dict:
    d = {
        "source": e.source,
        "timestamp": e.timestamp.isoformat(),
        "level": e.level,
        "stage": e.stage,
        "test_case": e.test_case,
        "message": e.message,
    }
    if e.request_id:
        d["request_id"] = e.request_id
    if include_call_stack and e.call_stack:
        d["call_stack"] = e.call_stack
    return d


def logs_to_text(logs: list[dict], max_message_chars: int = 500) -> str:
    """Compact, token-friendly rendering of log dicts for an LLM prompt."""
    lines = []
    for log in logs:
        msg = log["message"]
        if len(msg) > max_message_chars:
            msg = msg[:max_message_chars] + f"... [truncated {len(msg) - max_message_chars} chars]"
        lines.append(
            f"{log['timestamp']} [{log['source']}] {log['level']:<8} "
            f"{log['stage'] or '-'}/{log['test_case'] or '-'} | {msg}"
        )
        for frame in log.get("call_stack") or []:
            lines.append(f"    at {frame.get('function')} ({frame.get('file')})")
    return "\n".join(lines)


class LogRepository:
    def __init__(self, session_factory: sessionmaker):
        self._sf = session_factory

    def list_jobs(self) -> list[dict]:
        with self._sf() as s:
            return [
                {"job_id": j.job_id, "ingested_at": j.ingested_at.isoformat(), "source_dir": j.source_dir}
                for j in s.scalars(select(Job).order_by(Job.ingested_at.desc()))
            ]

    def get_test_results(self, job_id: str, only_failed: bool = False, voting_only: bool = False) -> list[dict]:
        stmt = select(TestResult).where(TestResult.job_id == job_id).order_by(TestResult.id)
        if only_failed:
            stmt = stmt.where(TestResult.result != "passed")
        if voting_only:
            stmt = stmt.where(TestResult.voting.is_(True))
        with self._sf() as s:
            return [
                {"test_case": r.test_case, "result": r.result, "voting": r.voting}
                for r in s.scalars(stmt)
            ]

    def get_job_summary(self, job_id: str) -> dict:
        """Entry point for the agent: what ran, what failed, where to look next."""
        with self._sf() as s:
            if s.get(Job, job_id) is None:
                raise KeyError(f"Unknown job_id: {job_id}")

            suites = [
                {"name": su.name, "tests": su.tests, "failures": su.failures, "errors": su.errors,
                 "skipped": su.skipped, "timestamp": su.timestamp}
                for su in s.scalars(select(PytestSuite).where(PytestSuite.job_id == job_id))
            ]
            failed_pytest = [
                {"test_case": c.test_case, "name": c.name, "outcome": c.outcome, "message": c.message}
                for c in s.scalars(
                    select(PytestCase)
                    .where(PytestCase.job_id == job_id, PytestCase.outcome.in_(("failed", "error")))
                    .order_by(PytestCase.id)
                )
            ]
            problem_counts = s.execute(
                select(LogEntry.test_case, LogEntry.level, func.count())
                .where(LogEntry.job_id == job_id, LogEntry.level_no >= LEVEL_NO["WARNING"],
                       LogEntry.is_server_echo.is_(False))
                .group_by(LogEntry.test_case, LogEntry.level)
            ).all()

        return {
            "job_id": job_id,
            "test_results": self.get_test_results(job_id),
            "pytest_suites": suites,
            "pytest_failures": failed_pytest,
            "warning_error_counts": [
                {"test_case": tc, "level": lvl, "count": n} for tc, lvl, n in problem_counts
            ],
        }

    def get_test_case_window(self, job_id: str, test_case: str) -> tuple[datetime, datetime] | None:
        with self._sf() as s:
            row = s.execute(
                select(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
                .where(LogEntry.job_id == job_id, LogEntry.test_case == test_case)
            ).one()
        return None if row[0] is None else (row[0], row[1])

    def get_logs(
        self,
        job_id: str,
        test_case: str | None = None,
        setup_only: bool = False,
        stages: list[str] | None = None,
        min_level: str = "DEBUG",
        sources: tuple[str, ...] = ("runner", "server"),
        start: datetime | None = None,
        end: datetime | None = None,
        contains: str | None = None,
        include_untagged_in_window: bool = False,
        include_server_echo: bool = False,
        include_call_stack: bool = False,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """Filtered, time-ordered logs from runner and server combined.

        setup_only: entries not tied to any test case (hil_setup / hil_environment ...).
        include_untagged_in_window: with test_case, also include entries with no
        test_case whose timestamp falls inside that test case's time window.
        """
        conds = [
            LogEntry.job_id == job_id,
            LogEntry.level_no >= LEVEL_NO.get(min_level.upper(), 0),
            LogEntry.source.in_(sources),
        ]
        if not include_server_echo:
            conds.append(LogEntry.is_server_echo.is_(False))
        if stages:
            conds.append(LogEntry.stage.in_(stages))
        if start:
            conds.append(LogEntry.timestamp >= start)
        if end:
            conds.append(LogEntry.timestamp <= end)
        if contains:
            conds.append(LogEntry.message.contains(contains))
        if setup_only:
            conds.append(LogEntry.test_case.is_(None))
        elif test_case:
            tc_cond = LogEntry.test_case == test_case
            window = self.get_test_case_window(job_id, test_case) if include_untagged_in_window else None
            if window:
                tc_cond = or_(tc_cond, and_(LogEntry.test_case.is_(None),
                                            LogEntry.timestamp.between(*window)))
            conds.append(tc_cond)

        stmt = (
            select(LogEntry)
            .where(*conds)
            .order_by(LogEntry.timestamp, LogEntry.source, LogEntry.seq)
            .limit(limit)
            .offset(offset)
        )
        with self._sf() as s:
            return [_log_to_dict(e, include_call_stack) for e in s.scalars(stmt)]

    def get_pytest_cases(
        self,
        job_id: str,
        test_case: str | None = None,
        outcomes: tuple[str, ...] | None = None,
        include_output: bool = False,
    ) -> list[dict]:
        stmt = select(PytestCase).where(PytestCase.job_id == job_id).order_by(PytestCase.id)
        if test_case:
            stmt = stmt.where(PytestCase.test_case == test_case)
        if outcomes:
            stmt = stmt.where(PytestCase.outcome.in_(outcomes))
        with self._sf() as s:
            out = []
            for c in s.scalars(stmt):
                d = {"test_case": c.test_case, "classname": c.classname, "name": c.name,
                     "outcome": c.outcome, "time": c.time, "message": c.message, "details": c.details}
                if include_output:
                    d["system_out"] = c.system_out
                    d["system_err"] = c.system_err
                out.append(d)
            return out

    def get_test_case_context(self, job_id: str, test_case: str, min_level: str = "DEBUG", limit: int = 300) -> dict:
        """Everything the agent needs to debug a single (failed) test case."""
        result = next((r for r in self.get_test_results(job_id) if r["test_case"] == test_case), None)
        window = self.get_test_case_window(job_id, test_case)
        return {
            "job_id": job_id,
            "test_case": test_case,
            "result": result,
            "time_window": [t.isoformat() for t in window] if window else None,
            "pytest_failures": self.get_pytest_cases(job_id, test_case, outcomes=("failed", "error")),
            "logs": self.get_logs(job_id, test_case=test_case, min_level=min_level,
                                  include_untagged_in_window=True, limit=limit),
        }
