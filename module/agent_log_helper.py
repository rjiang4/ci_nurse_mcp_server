from module.artifactory_helper import fetch_artifact_bytes, query_agent_log_url
from log_db import LogRepository, init_db, ingest_job_bytes, JobArtifacts

#TODO: Refine the log file name
AGENT_LOG_NAME = {
    "runner_log": "carbit_debug.json",
    "server_log": "server_log.json",
    "test_results": "carbit_test_results.json",
    "pytest_xml": "carbit_analysis.xml",
}

DB_PATH = "sqlite:///C:/Tools/agent_server/database/agent_log.db"

def build_artifacts(job_id: str) -> JobArtifacts:
    agent_log_url = query_agent_log_url(job_id=job_id)
    print(agent_log_url)
    print(f"runner agent log name: {AGENT_LOG_NAME.get("runner_log")}")
    runner_log_url = next(
        (url.get("url") for url in agent_log_url if url.get("name") == AGENT_LOG_NAME.get("runner_log")),
        None
    )
    print(f"runner log url: {runner_log_url}")
    runner_log_byte, _ = fetch_artifact_bytes(url=runner_log_url)

    server_log_url = next(
        (url.get("url") for url in agent_log_url if url.get("name") == AGENT_LOG_NAME.get("server_log")),
        None
    )
    server_log_byte, _ = fetch_artifact_bytes(url=server_log_url)

    test_results_url = next(
        (url.get("url") for url in agent_log_url if url.get("name") == AGENT_LOG_NAME.get("test_results")),
        None
    )
    test_results_byte, _ = fetch_artifact_bytes(url=test_results_url)

    pytest_xml_url = next(
        (url.get("url") for url in agent_log_url if url.get("name") == AGENT_LOG_NAME.get("pytest_xml")),
        None
    )
    pytest_xml_byte, _ = fetch_artifact_bytes(url=pytest_xml_url)

    return JobArtifacts(
        runner_log=runner_log_byte,
        server_log=server_log_byte,
        test_results=test_results_byte,
        pytest_xml=pytest_xml_byte,
    )

def ingest_log_to_db(job_id:str):
    ja = build_artifacts(job_id=job_id)
    sf = init_db(db_url=DB_PATH)
    ingest_job_bytes(session_factory=sf, job_id=job_id, artifacts=ja)


def get_test_result_(job_id: str, only_failed: bool) -> list[dict]:
    """
    Get overview of the test result
    """
    repo = LogRepository(init_db(db_url=DB_PATH))

    job_exist = any(
        job["job_id"] == job_id
        for job in repo.list_jobs()
    )

    if not job_exist:
        ingest_log_to_db(job_id=job_id)

    return repo.get_test_results(job_id=job_id, only_failed=only_failed)

def analyze_test_case_(job_id : str, test_case: str) -> dict:
    repo = LogRepository(init_db(db_url=DB_PATH))
    return repo.get_test_case_context(job_id=job_id, test_case=test_case)
