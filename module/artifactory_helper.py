import json
import os
import ssl
from collections.abc import Callable
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

import auth.auth as shared_auth

ARTIFACTORY_HOST = "https://ara-artifactory.volvocars.biz"
ARTIFACTORY_AQL_API = f"{ARTIFACTORY_HOST}/artifactory/api/search/aql"
ARTIFACTORY_REPO = "carbit-share-sts"
ARTIFACTORY_TIMEOUT_SECONDS = 15


try:
    SSL_CTX = ssl._create_unverified_context()
except AttributeError:
    SSL_CTX = ssl.create_default_context()

def clear_auth_cache() -> None:
    """Drop the shared token so the next upstream request authenticates again."""
    shared_auth.clear_auth_cache()

def _open_authenticated(url: str, headers: dict[str, str], timeout: int):
    opener = build_opener(HTTPSHandler(context=SSL_CTX), HTTPRedirectHandler)
    return opener.open(Request(url, headers=headers, method="GET"), timeout=timeout)

def _retry_once_on_401(call: Callable[[], Any]) -> Any:
    try:
        return call()
    except HTTPError as error:
        if error.code != 401:
            raise
        clear_auth_cache()
        return call()

def format_file_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return ""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TB"

def get_auth_headers(force_refresh: bool = False) -> dict[str, str]:
    """Return non-secret request headers from the shared auth implementation."""
    return shared_auth.get_auth_headers(force_refresh)

def fetch_aql_query(aql_query_str: str, timeout: int = 15) -> list[dict[str, Any]]:
    """Execute an Artifactory AQL query and return its result records."""
    def request_aql() -> list[dict[str, Any]]:
        headers = get_auth_headers()
        headers["Content-Type"] = "text/plain"
        headers["Accept"] = "application/json"
        request = Request(
            ARTIFACTORY_AQL_API,
            data=aql_query_str.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=timeout, context=SSL_CTX) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = json.loads(response.read().decode(charset, errors="replace"))
        return payload.get("results", []) if isinstance(payload, dict) else []

    return _retry_once_on_401(request_aql)

def query_artifactory_files(job_id: str, task_id: str = "") -> list[dict[str, Any]]:
    """Return normalized Artifactory files for one Zeta job."""
    job_id = str(job_id).strip()
    if not job_id:
        raise ValueError("Job ID is required to query Artifactory files")

    aql_query = (
        f'items.find({{"repo": "{ARTIFACTORY_REPO}", '
        f'"path": {{"$match": "zeta/jobs/{job_id}*"}}}})'
    )
    files: list[dict[str, Any]] = []
    for item in fetch_aql_query(aql_query, timeout=ARTIFACTORY_TIMEOUT_SECONDS):
        name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        if not name:
            continue
        size = int(item.get("size") or 0)
        updated = str(item.get("updated") or "")
        files.append({
            "name": name,
            "path": path,
            "size": size,
            "formatted_size": format_file_size(size),
            "updated": updated[:19].replace("T", " "),
            "url": f"{ARTIFACTORY_HOST}/artifactory/{ARTIFACTORY_REPO}/{path}/{name}",
        })
    return files

def fetch_artifact_bytes(
    url: str,
    timeout: int = 60,
    max_bytes: int = 200_000_000,
    progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> tuple[bytes, str]:
    """Download an arbitrary authenticated Artifactory asset and its MIME type."""
    def request_asset() -> tuple[bytes, str]:
        headers = get_auth_headers()
        headers["Accept"] = "*/*"
        with _open_authenticated(url, headers, timeout) as response:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            total = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
            chunks: list[bytes] = []
            received = 0
            while received < max_bytes:
                chunk = response.read(min(256 * 1024, max_bytes - received))
                if not chunk:
                    break
                chunks.append(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
        return b"".join(chunks), content_type

    return _retry_once_on_401(request_asset)

def query_agent_log_url(job_id: str, task_id: str = "") -> list[dict[str, Any]]:
    """Return normalized Artifactory files for one Zeta job."""
    job_id = str(job_id).strip()
    if not job_id:
        raise ValueError("Job ID is required to query Artifactory files")

    aql_query = (
        f'items.find({{"repo": "{ARTIFACTORY_REPO}", '
        f'"path": {{"$match": "zeta/jobs/{job_id}*"}}}})'
    )
    url: list[dict[str, Any]] = []
    for item in fetch_aql_query(aql_query, timeout=ARTIFACTORY_TIMEOUT_SECONDS):
        name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        if not name or "agent_log" not in path:
            continue
        size = int(item.get("size") or 0)
        updated = str(item.get("updated") or "")
        url.append({
            "name": name,
            "url": f"{ARTIFACTORY_HOST}/artifactory/{ARTIFACTORY_REPO}/{path}/{name}",
        })
    return url
