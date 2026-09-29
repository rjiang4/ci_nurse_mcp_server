import argparse
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session, sessionmaker

from .models import Job, LogEntry, PytestCase, PytestSuite, TestResult, init_db

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LEVEL_NO = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "WARN": 30, "ERROR": 40, "CRITICAL": 50}

DEFAULT_FILES = {
    "runner_log": "carbit.debug.json",
    "server_log": "server_log_spa3_si.json",
    "test_results": "carbit.test_results.json",
    "pytest_xml": "VCCTEST_ANALYSIS.xml",
}


@dataclass(frozen=True)
class JobArtifacts:
    runner_log: bytes | None = None
    server_log: bytes | None = None
    test_results: bytes | None = None
    pytest_xml: bytes | None = None


def iter_json_objects(data: bytes) -> Iterator[dict]:
    """Yield objects from JSONL, concatenated pretty-printed JSON, or a JSON array."""
    text = data.decode("utf-8", errors="replace")
    decoder = json.JSONDecoder()
    idx, n = 0, len(text)
    while True:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            return
        obj, idx = decoder.raw_decode(text, idx)
        if isinstance(obj, list):
            yield from obj
        else:
            yield obj


def parse_ts(value: str) -> datetime:
    """Normalize to naive UTC. Naive inputs (runner log) are assumed to already be UTC."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _log_rows(job_id: str, source: str, data: bytes) -> list[dict]:
    rows = []
    for seq, rec in enumerate(iter_json_objects(data)):
        level = (rec.get("level") or "").upper()
        message = ANSI_RE.sub("", rec.get("message") or "")
        rows.append(
            {
                "job_id": job_id,
                "source": source,
                "seq": seq,
                "timestamp": parse_ts(rec["timestamp"]),
                "level": level,
                "level_no": LEVEL_NO.get(level, 0),
                "stage": rec.get("stage"),
                "test_case": rec.get("test_case"),
                "message": message,
                "call_stack": rec.get("call_stack"),
                "request_id": rec.get("request_id"),
                "is_server_echo": source == "runner" and message.startswith("[Server Log]"),
            }
        )
    return rows


def _join_unique(elements: list[ET.Element]) -> str | None:
    # pytest-html/junit often repeats identical captured-output blocks per phase.
    seen: list[str] = []
    for el in elements:
        text = (el.text or "").strip()
        if text and text not in seen:
            seen.append(text)
    return "\n\n".join(seen) or None


def _ingest_junit(session: Session, job_id: str, data: bytes, source_file: str) -> None:
    root = ET.fromstring(data)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    outcome_tags = {"failure": "failed", "error": "error", "skipped": "skipped"}

    for s in suites:
        suite_time = s.get("time")
        suite = PytestSuite(
            job_id=job_id,
            source_file=source_file,
            name=s.get("name"),
            tests=int(s.get("tests", 0)),
            failures=int(s.get("failures", 0)),
            errors=int(s.get("errors", 0)),
            skipped=int(s.get("skipped", 0)),
            time=float(suite_time) if suite_time else None,
            timestamp=s.get("timestamp"),
            hostname=s.get("hostname"),
        )
        session.add(suite)
        session.flush()

        rows = []
        for tc in s.iter("testcase"):
            case_time = tc.get("time")
            outcome, message, details = "passed", None, None
            for tag, value in outcome_tags.items():
                el = tc.find(tag)
                if el is not None:
                    outcome, message, details = value, el.get("message"), el.text
                    break
            classname = tc.get("classname", "")
            rows.append(
                {
                    "job_id": job_id,
                    "suite_id": suite.id,
                    "test_case": classname.split(".", 1)[0],
                    "classname": classname,
                    "name": tc.get("name", ""),
                    "time": float(case_time) if case_time else None,
                    "outcome": outcome,
                    "message": message,
                    "details": details,
                    "system_out": _join_unique(tc.findall("system-out")),
                    "system_err": _join_unique(tc.findall("system-err")),
                }
            )
        if rows:
            session.execute(insert(PytestCase), rows)


def ingest_job_bytes(
    session_factory: sessionmaker,
    job_id: str,
    artifacts: JobArtifacts,
    *,
    source_ref: str | None = None,
    pytest_xml_name: str = DEFAULT_FILES["pytest_xml"],
) -> None:
    """Ingest in-memory artifacts. Re-ingesting the same job_id replaces its data."""

    with session_factory.begin() as session:
        for model in (LogEntry, PytestCase, PytestSuite, TestResult, Job):
            session.execute(delete(model).where(model.job_id == job_id))

        session.add(Job(job_id=job_id, source_dir=source_ref))
        session.flush()

        if artifacts.test_results is not None:
            rows = [
                {
                    "job_id": job_id,
                    "test_case": r["test_case"],
                    "result": r["result"],
                    "voting": bool(r.get("voting", False)),
                }
                for r in iter_json_objects(artifacts.test_results)
            ]
            if rows:
                session.execute(insert(TestResult), rows)

        for source, data in (("runner", artifacts.runner_log), ("server", artifacts.server_log)):
            if data is not None:
                rows = _log_rows(job_id, source, data)
                if rows:
                    session.execute(insert(LogEntry), rows)

        if artifacts.pytest_xml is not None:
            _ingest_junit(session, job_id, artifacts.pytest_xml, pytest_xml_name)


def ingest_job(
    session_factory: sessionmaker,
    job_id: str,
    data_dir: str | Path,
    files: dict[str, str] | None = None,
) -> None:
    """Read artifacts from a directory and pass their bytes to the core ingester."""
    data_dir = Path(data_dir)
    files = {**DEFAULT_FILES, **(files or {})}

    def read_if_present(key: str) -> bytes | None:
        path = data_dir / files[key]
        return path.read_bytes() if path.exists() else None

    ingest_job_bytes(
        session_factory,
        job_id,
        JobArtifacts(
            runner_log=read_if_present("runner_log"),
            server_log=read_if_present("server_log"),
            test_results=read_if_present("test_results"),
            pytest_xml=read_if_present("pytest_xml"),
        ),
        source_ref=str(data_dir.resolve()),
        pytest_xml_name=files["pytest_xml"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest HIL test logs for a job into SQLite.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--db", default="sqlite:///hil_reports.db")
    for key, default in DEFAULT_FILES.items():
        parser.add_argument(f"--{key.replace('_', '-')}", default=default)
    args = parser.parse_args()

    files = {key: getattr(args, key) for key in DEFAULT_FILES}
    ingest_job(init_db(args.db), args.job_id, args.data_dir, files)
    print(f"Ingested job {args.job_id} into {args.db}")


if __name__ == "__main__":
    main()
