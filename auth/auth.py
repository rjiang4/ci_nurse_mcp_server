"""Azure AD, Vault, and Artifactory OIDC authentication for Version 4."""

from __future__ import annotations

import http.client
import json
import os
import threading
import time
from typing import Final

import hvac
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

VAULT_ADDR: Final = "https://vault.csm.volvocars.biz/"
VAULT_MOUNTPOINT: Final = "teamstores"
OIDC_TOKEN_ENDPOINT: Final = "https://ara-artifactory.volvocars.biz/access/api/v1/oidc/token"
AZURE_TENANT_ID: Final = "81fa766e-a349-4867-8bf4-ab35e250a08f"
AZURE_SCOPE: Final = "api://AzureADTokenExchange/.default"
USER_AGENT: Final = "ZetaOperationsV4/4.0"
TOKEN_TTL_SECONDS: Final = 4 * 3600 - 5 * 60

_lock = threading.Lock()
_headers: dict[str, str] = {}
_fetched_at = 0.0
_status = "Not authenticated"


class VaultClient:
    """Read Azure service-principal credentials from HashiCorp Vault."""

    def __init__(self) -> None:
        token = os.environ.get("VAULT_TOKEN")
        if not token:
            raise EnvironmentError("VAULT_TOKEN must be set for Artifactory and Victoria access.")
        self._client = hvac.Client(url=VAULT_ADDR, token=token, verify=False)
        if not self._client.is_authenticated():
            raise RuntimeError("Vault authentication failed.")
        token_info = self._client.auth.token.lookup_self()
        if token_info.get("data", {}).get("renewable"):
            self._client.auth.token.renew_self()
        self._client.secrets.kv.default_kv_version = "2"

    def azure_credentials(self) -> tuple[str, str]:
        response = self._client.secrets.kv.read_secret_version(
            "cld-9600-sva-ad-adas-sg/azure-spn", mount_point=VAULT_MOUNTPOINT
        )
        data = response["data"]["data"]
        return str(data["client_id"]), str(data["client_secret"])


def _fetch_azure_token() -> str:
    client_id, client_secret = VaultClient().azure_credentials()
    response = requests.post(
        f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret, "scope": AZURE_SCOPE},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=False,
        timeout=30,
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def fetch_artifactory_token() -> tuple[str, str]:
    """Exchange a Vault-backed Azure token for an Artifactory OIDC token."""
    payload = json.dumps({"grant_type": "urn:ietf:params:oauth:grant-type:token-exchange", "subject_token_type": "urn:ietf:params:oauth:token-type:id_token", "provider_name": "azuread", "subject_token": _fetch_azure_token(), "expires_in": "14400"})
    headers = {"Content-Type": "application/json"}
    response = requests.post(OIDC_TOKEN_ENDPOINT, headers=headers, data=payload, verify=False, timeout=30)
    if response.status_code == 401:
        connection = http.client.HTTPSConnection("ara-artifactory.volvocars.biz", timeout=30)
        connection.request("POST", "/access/api/v1/oidc/token", payload, headers)
        response_data = json.loads(connection.getresponse().read().decode("utf-8"))
    else:
        response.raise_for_status()
        response_data = response.json()
    return str(response_data.get("username") or ""), str(response_data.get("access_token") or "")


def clear_auth_cache() -> None:
    global _headers, _fetched_at
    with _lock:
        _headers = {}
        _fetched_at = 0.0


def get_auth_headers(force_refresh: bool = False) -> dict[str, str]:
    """Return cached Bearer headers, refreshing before the 4-hour token expires."""
    global _headers, _fetched_at, _status
    with _lock:
        expired = time.monotonic() - _fetched_at >= TOKEN_TTL_SECONDS
        if _headers and not force_refresh and not expired:
            return dict(_headers)
        base = {"User-Agent": USER_AGENT, "Cache-Control": "no-cache", "Pragma": "no-cache"}
        try:
            username, token = fetch_artifactory_token()
            if token:
                _headers = {**base, "Authorization": f"Bearer {token}"}
                _fetched_at = time.monotonic()
                _status = f"Authenticated as {username}"
                return dict(_headers)
            _status = "Token exchange returned no token"
        except Exception as error:
            _status = f"Token error: {error}"
        return base


def auth_status() -> str:
    """Return non-secret authentication status for diagnostics/UI display."""
    return _status