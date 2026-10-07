from module.zeta_helper import get_latest_zeta_link_, get_latest_zeta_log_, get_last_finsihed_zeta_run_, JobTitle, ZetaLinkResponse, ZetaLogResponse, ZetaResponse
from module.agent_log_helper import analyze_test_case_, get_test_result_

from mcp.server import MCPServer

# Initialize MCPServer
mcp = MCPServer("ci-nurse")

# Tool functions for Zeta job link and log retrieval
@mcp.tool(name="get_latest_zeta_link")
def get_latest_zeta_link(title: JobTitle, size: int = 1, from_idx: int = 0) -> ZetaLinkResponse:
    """
    Fetch Zeta job link in CISTATS with Elastic Search API.
    This tool will be used when user generally ask for a zeta job log, the job can be not-finsihed state.
    This function uses the `elastic_search` and `search_builder` functions 
    to query the Elastic Search API and retrieve the Zeta job link based on the provided title.
    If user does not provide size or from_idx, default values will be used.

    The function will return a valid Zeta job link if the job is finished, or the output log for
    Victoria state if the job is still ongoing, or if there is no Zeta job link available and the state
    is not ongoing, then the raw search result will be returned.

    If getting the zeta job link returns None, it means the job is still ongoing or no link is available.
    If getting the output log returns None, it means there is no output log available for the ongoing job.

    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

        Users may refer to jobs using simplified or shorthand names.
        When calling this tool, always resolve the user's shorthand to one
        of the exact allowed `title` values defined in the tool schema.
        Never pass the user's shorthand directly as `title`, it should match
        one of the following:
        SPA3_Infra_Nightly_SI_1,
        SPA3_Infra_Nightly_SI_2,
        SPA3 Infra Nightly SI 3,
        SPA3_Infra_Nightly_SI_4,
        SPA3_Infra_Nightly_SI_5,
        SPA3_Infra_Nightly_SI_6,
        
        SPA3_Infra_Nightly_Domain_1,
        SPA3 Infra Nightly Domain 2,
        SPA3_Infra_Nightly_Domain_3,
        SPA3_Infra_Nightly_Domain_4,

        For example:
            "SPA3_Infra_Nightly_SI_1" can be input as "spa3 s1 infra" or "SPA3 s1 nightly".
            "Sensor1" or "Sensor 1" means "SI 1".
        The following explaination should be followed along with the rules above:
            "SVA BQ V436 Sensor Integration DOS 6.5" -> The Baseline Qualification (BQ) job for Sensor Integration 2 (SI 2).
            "SVA BQ V436 Sensor Integration" -> The Baseline Qualification (BQ) job for Sensor Integration 3 (SI 3).
            "SVA BQ V436 Domain" -> The Baseline Qualification (BQ) job for the Domain 2.
    
    Returns:
        ZetaLinkResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job link will be included.
        In case of an error, the raw search result will be returned.
        If valid zeta link is returned, the reponse will contain job_id.
    """

    return get_latest_zeta_link_(title=title, size=size, from_idx=from_idx)


@mcp.tool(name="get_latest_zeta_log")
def get_latest_zeta_log(title: JobTitle, size: int = 1, from_idx: int = 0) -> ZetaLogResponse:
    """
    Fetch Zeta job log in CISTATS with Elastic Search API.
    This tool will be used when user generally ask for a zeta job log, the job can be not-finsihed state.
    This function uses the `elastic_search` and `search_builder` functions 
    to query the Elastic Search API and retrieve the Zeta job log based on the provided title.
    If user does not provide size or from_idx, default values will be used.
    
    The function will return a valid Zeta job log if the job is finished, or the output log for
    Victoria state if the job is still ongoing, or if there is no Zeta job log available and the state
    is not ongoing, then the raw search result will be returned.

    If getting the zeta job log returns None, it means the job is still ongoing or no log is available.
    If getting the output log returns None, it means there is no output log available for the ongoing job.

    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

        Users may refer to jobs using simplified or shorthand names.
        When calling this tool, always resolve the user's shorthand to one
        of the exact allowed `title` values defined in the tool schema.
        Never pass the user's shorthand directly as `title`, it should match
        one of the following:
        SPA3_Infra_Nightly_SI_1,
        SPA3_Infra_Nightly_SI_2,
        SPA3 Infra Nightly SI 3,
        SPA3_Infra_Nightly_SI_4,
        SPA3_Infra_Nightly_SI_5,
        SPA3_Infra_Nightly_SI_6,
        
        SPA3_Infra_Nightly_Domain_1,
        SPA3 Infra Nightly Domain 2,
        SPA3_Infra_Nightly_Domain_3,
        SPA3_Infra_Nightly_Domain_4,
        
        SVA BQ V436 Sensor Integration DOS 6.5,
        SVA BQ V436 Sensor Integration,
        SVA BQ V436 Domain,

        For example:
            "SPA3_Infra_Nightly_SI_1" can be input as "spa3 s1 infra" or "SPA3 s1 nightly".
            "Sensor1" or "Sensor 1" means "SI 1".
        The following explaination should be followed along with the rules above:
            "SVA BQ V436 Sensor Integration DOS 6.5" -> The Baseline Qualification (BQ) job for Sensor Integration 2 (SI 2).
            "SVA BQ V436 Sensor Integration" -> The Baseline Qualification (BQ) job for Sensor Integration 3 (SI 3).
            "SVA BQ V436 Domain" -> The Baseline Qualification (BQ) job for the Domain 2.

    Returns:
        ZetaLogResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job logs will be included.
        In case of an error, the raw search result will be returned.
    """

    return get_latest_zeta_log_(title=title, size=size, from_idx=from_idx)

@mcp.tool(name="get_last_finsihed_zeta_run")
def get_last_finsihed_zeta_run(title: JobTitle, size: int = 5, from_idx: int = 0) -> ZetaResponse:
    """
    Fetch the last finished Zeta job link and log in CISTATS with Elastic Search API.
    This function will be used when user specifc they need a finished run or similar expression.
    This function uses the `elastic_search` and `search_builder` functions 
    to query the Elastic Search API and retrieve the Zeta job log based on the provided title.
    If user does not provide size or from_idx, default values will be used.
    
    The function will return a valid Zeta job log if the job is finished, or the output log for
    Victoria state if the job is still ongoing, or if there is no Zeta job log available and the state
    is not ongoing, then the raw search result will be returned.

    If getting the zeta job log returns None, it means the job is still ongoing or no log is available.
    If getting the output log returns None, it means there is no output log available for the ongoing job.

    Args:
        title (JobTitle): The title of the Zeta job to search for.
        size (int): The number of search results to return.
        from_idx (int): The starting index for the search results.

        Users may refer to jobs using simplified or shorthand names.
        When calling this tool, always resolve the user's shorthand to one
        of the exact allowed `title` values defined in the tool schema.
        Never pass the user's shorthand directly as `title`, it should match
        one of the following:
        SPA3_Infra_Nightly_SI_1,
        SPA3_Infra_Nightly_SI_2,
        SPA3 Infra Nightly SI 3,
        SPA3_Infra_Nightly_SI_4,
        SPA3_Infra_Nightly_SI_5,
        SPA3_Infra_Nightly_SI_6,
        
        SPA3_Infra_Nightly_Domain_1,
        SPA3 Infra Nightly Domain 2,
        SPA3_Infra_Nightly_Domain_3,
        SPA3_Infra_Nightly_Domain_4,
        
        SVA BQ V436 Sensor Integration DOS 6.5,
        SVA BQ V436 Sensor Integration,
        SVA BQ V436 Domain,

        For example:
            "SPA3_Infra_Nightly_SI_1" can be input as "spa3 s1 infra" or "SPA3 s1 nightly".
            "Sensor1" or "Sensor 1" means "SI 1".
        The following explaination should be followed along with the rules above:
            "SVA BQ V436 Sensor Integration DOS 6.5" -> The Baseline Qualification (BQ) job for Sensor Integration 2 (SI 2).
            "SVA BQ V436 Sensor Integration" -> The Baseline Qualification (BQ) job for Sensor Integration 3 (SI 3).
            "SVA BQ V436 Domain" -> The Baseline Qualification (BQ) job for the Domain 2.

    Returns:
        ZetaLogResponse:
        The response will indicate the state of the Zeta job ("ongoing", "finished", or "error") along with the relevant logs or output.
        If the job is ongoing, the output log URL will be provided if available.
        If the job is finished, the Zeta job logs will be included.
        In case of an error, the raw search result will be returned.
        If valid zeta link is returned, the reponse will contain job_id.
    """

    return get_last_finsihed_zeta_run_(title=title, size=size, from_idx=from_idx)


@mcp.tool(name="get_test_result")
def get_test_result(job_id: str, only_failed: bool = False) -> list[dict]:
    """
    Get the test result overview for a test job.

    Use this tool as the FIRST STEP when analyzing a test job.

    By default, it returns all test cases, but you can set `only_failed` to True
    to retrieve only the failed ones.

    For each test case returned by this tool, use
    `analyze_test_case(job_id, test_case)` to retrieve detailed logs and
    analysis context.

    Recommended workflow for whole-job analysis:
        1. Call `get_test_result(job_id)` to identify all test cases.
        2. Call `analyze_test_case(job_id, test_case)` for each test case.
        3. Combine the results to summarize the overall job status, failures,
           and possible root causes.

    Args:
        job_id: The unique identifier of the test job.
        only_failed: If True, return only failed test cases.
            If False, return all test case results. By default, it is False.

    Returns:
        A list of dictionaries with test case results, for example:
        {
            "test_case": "test_example",
            "result": "failed",
            "voting": True
        }
    """
    return get_test_result_(job_id=job_id, only_failed=only_failed)

@mcp.tool(name="analyze_test_case")
def analyze_test_case(job_id: str, test_case: str) -> dict:
    """
    Retrieve detailed analysis context for one test case within a test job.

    Use this tool AFTER `get_test_result` when a specific test case requires
    investigation.

    This tool is intended for detailed debugging and root-cause analysis of a
    test case. The returned context may include test logs, server logs,
    timestamps, stages, result analysis, and other diagnostic information.

    When analyzing an entire test job:
        - First call `get_test_result(job_id)`.
        - Then call this tool for each failed or otherwise relevant test case.
        - Use the collected contexts to produce a job-level analysis.

    Args:
        job_id: The unique identifier of the test job.
        test_case: The exact test case name returned by `get_test_result`.

    Returns:
        A dictionary containing the available logs, analysis results, and
        diagnostic context for the specified test case.
    """

    return analyze_test_case_(job_id=job_id, test_case=test_case)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8081,
        #streamable_http_path="",  Define the root path here, by default is mcp
    )
