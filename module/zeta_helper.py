import asyncio
import logging
from pydantic import BaseModel
# from title_mapping import JobTitle
from typing import Any, Literal

import httpx2

# Constants
CISTATS_API_BASE = "https://cistat.volvocars.biz/_search/?size=1&pretty=true"
USER_AGENT = "zmaster-app/1.0"
OUTPUT_NAME = "Output"      # The name of the output log in the elastic search results
ZETA_LOG_NAME = "zeta-log"  # The name of the zeta log in the elastic search results

JobTitle = Literal[
    # Infra Nightly SI
    "SPA3_Infra_Nightly_SI_1",
    "SPA3_Infra_Nightly_SI_2",
    "SPA3 Infra Nightly SI 3",
    "SPA3_Infra_Nightly_SI_4",
    "SPA3_Infra_Nightly_SI_5",
    "SPA3_Infra_Nightly_SI_6",

    # Infra Nightly Domain
    "SPA3_Infra_Nightly_Domain_1",
    "SPA3 Infra Nightly Domain 2",
    "SPA3_Infra_Nightly_Domain_3",
    "SPA3_Infra_Nightly_Domain_4",

    # SVA BQ Baseline Qualification V436
    "SVA BQ V436 Sensor Integration DOS 6.5",
    "SVA BQ V436 Sensor Integration",
    "SVA BQ V436 Domain",
]

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Elastic Search Helper Functions
async def _elastic_search(search_request: dict) -> dict | None:
    """ Make a request to Victoria Elastic Search API with proper error handling"""
    headers = {"User-Agent": USER_AGENT}
    async with httpx2.AsyncClient() as client:
        try:
            response = await client.post(CISTATS_API_BASE, headers=headers, json=search_request, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            if not data["hits"]["hits"]:
                return None
            
            source = data["hits"]["hits"][0]["_source"]
            return source
        except Exception:
            logger.error("Error occurred during elastic search")
            raise

def _search_builder(title: JobTitle, size: int = 5, from_idx: int = 0, state: str | None = None) -> dict:
    """
    Build the search request for Elastic Search API based on the given title.
    If user does not provide size or from_idx, default values will be used.

    Args:
        title (JobTitle): The title to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.
    Returns:
        dict: The search request for Elastic Search API.
    """

    search = {
        "size": size,
        "from": from_idx,
        "track_total_hits": True,

        "_source": [
            "state", # The state of the job -> e.g., finished, ongoing
            "url", # The Zeta link to access the job details
            "logs" # The Zeta logs associated with the job
        ],

        "query": {
            "bool": {
                "must": [
                    {"match": {"head.type": "ActivityStateEvent"}},
                    {"match_phrase": {"title": title}},
                ]
            }
        },

        "sort": [{"@timestamp": {"order": "desc"}}],
    }

    if state:
        search["query"]["bool"]["must"].append(
            {
                "match": {"state": state}
            }
        )
    
    return search

# Response models for Zeta job link and log retrieval
class ToolResponse(BaseModel):
    message: str | None = None

class ZetaLinkResponse(ToolResponse):
    job_state: Literal["ongoing", "finished", "not found"]
    output_log: str | None = None
    source: dict | None = None
    zeta_link: str | None = None
    job_id: str | None = None

class ZetaLogResponse(ToolResponse):
    job_state: Literal["ongoing", "finished", "not found"]
    output_log: str | None = None
    source: dict | None = None
    zeta_log: str | None = None

class ZetaResponse(ToolResponse):
    job_state: Literal["ongoing", "finished", "not found"]
    output_log: str | None = None
    source: dict | None = None
    zeta_link: str | None = None
    zeta_log: str | None = None
    job_id: str | None = None


# Tool functions for Zeta job link and log retrieval
def _get_job_id(zeta_link: str) -> str | None:
    job_id = zeta_link.rsplit("/", 1)[-1]

    if job_id.isdigit():
        return job_id
    else:
        logger.error("Zeta link is not valid: %s", zeta_link)
        return None


def get_latest_zeta_link_(title: JobTitle, size: int = 5, from_idx: int = 0) -> ZetaLinkResponse:
    """
    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

    Returns:
        ZetaLinkResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job link will be included.
        In case of an error, the raw search result will be returned.
    """

    _source = asyncio.run(_elastic_search(_search_builder(title, size=size, from_idx=from_idx)))

    if not _source:
        logger.warning("No source returned from elastic search for title '%s'", title)
        return ZetaLinkResponse(
            job_state="not found",
            message="No source returned from elastic search, the job might be ongoing.",
        )

    #HACK: Is there a third state besides "ongoing" and "finished"?
    if _source.get("state") == "ongoing":
        logger.info("Zeta job '%s' is still ongoing.", title)
        output_log = next((log["url"] for log in _source.get("logs", []) if log.get("name") == "Output"), None)
        if output_log is None:
            logger.warning("Job is ongoing but no output log available for Zeta job '%s'.", title)

        return ZetaLinkResponse(
            job_state="ongoing", 
            message=(
                None
                if output_log
                else "Zeta job is ongoing but output log is not available."
            ), 
            output_log=output_log, 
            source=_source
        )
    
    zeta_link = _source.get("url")
    if zeta_link is None:
        logger.error("Error occurred while fetching zeta link, get returned source %s", _source)
        return ZetaLinkResponse(
            job_state="finished", 
            message="Zeta job finished but link is not available.", 
            source=_source
        )

    return ZetaLinkResponse(
        job_state="finished", 
        zeta_link=zeta_link,
        job_id=_get_job_id(zeta_link=zeta_link),
    )


def get_latest_zeta_log_(title: JobTitle, size: int = 5, from_idx: int = 0) -> ZetaLogResponse:
    """
    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

    Returns:
        ZetaLogResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job logs will be included.
        In case of an error, the raw search result will be returned.
    """

    _source = asyncio.run(_elastic_search(_search_builder(title, size=size, from_idx=from_idx)))

    if not _source:
        logger.warning("No source returned from elastic search for title '%s'", title)
        return ZetaLogResponse(
            job_state="not found",
            message="No source returned from elastic search, the job might be ongoing.",
        )

    #HACK: Is there a third state besides "ongoing" and "finished"?
    if _source.get("state") == "ongoing":
        logger.info("Zeta job with title '%s' is still ongoing.", title)
        output_log = next((log["url"] for log in _source.get("logs", []) if log.get("name") == OUTPUT_NAME), None)
        if output_log is None:
            logger.warning("No output log available for Zeta job '%s'.", title)

        return ZetaLogResponse(
            job_state="ongoing", 
            message=(
                None
                if output_log
                else "Zeta job is ongoing but output log is not available."
            ), 
            output_log=output_log, 
            source=_source
        )

    zeta_log = next((log["url"] for log in _source.get("logs", []) if log.get("name") == ZETA_LOG_NAME), None)
    # If zeta_log is None, it means there are no logs available for the finished job.
    if zeta_log is None:
        logger.error("Error occurred while fetching zeta log, get returned source %s", _source)
        return ZetaLogResponse(
            job_state="finished", 
            message="Zeta job finished but log is not available", 
            source=_source
        )

    return ZetaLogResponse(
        job_state="finished", 
        zeta_log=zeta_log,
    )

def get_last_finsihed_zeta_run_(title: JobTitle, size: int = 5, from_idx: int = 0) -> ZetaResponse:
    """
    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

    Returns:
        ZetaResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job logs will be included.
        In case of an error, the raw search result will be returned.
    """

    _source = asyncio.run(_elastic_search(_search_builder(title, size=size, from_idx=from_idx, state="finished")))

    if not _source:
        logger.warning("No source returned from elastic search for title '%s'", title)
        return ZetaResponse(
            job_state="not found",
            message="No source returned from elastic search, the job finished but no zeta info available.",
        )

    zeta_link = _source.get("url")
    if zeta_link is None:
        logger.error("No zeta link available with finished run, something wrong with the zeta, get returned source %s", _source)

    zeta_log = next((log["url"] for log in _source.get("logs", []) if log.get("name") == ZETA_LOG_NAME), None)
    # If zeta_log is None, it means there are no logs available for the finished job.
    if zeta_log is None:
        logger.error("No zeta log available with finished run, get returned source %s", _source)

    return ZetaResponse(
        job_state="finished", 
        zeta_link=zeta_link if zeta_link else None,
        zeta_log=zeta_log if zeta_log else None,
        job_id=_get_job_id(zeta_link=zeta_link),
    )
