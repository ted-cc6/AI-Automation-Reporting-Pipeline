"""dashboard/api/powerbi_client.py

Real Power BI REST API client (OAuth client-credentials + ExportTo image
export), structurally complete but not yet usable: the org's Power BI API
access is still pending approval. Calling export_pages_as_images() raises
NotImplementedError with a clear message until then -- the dashboard's
manual-upload path (see visuals_source.py) is the working default in the
meantime, and both populate the exact same visual slots once this is live.
"""
import logging
import time

import requests
from pydantic import BaseModel

log = logging.getLogger(__name__)

AAD_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
POWERBI_API_ROOT = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


class PowerBiConfig(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    workspace_id: str
    report_id: str


class PowerBiClient:
    def __init__(self, config: PowerBiConfig):
        self.config = config

    def _get_access_token(self) -> str:
        url = AAD_TOKEN_URL.format(tenant_id=self.config.tenant_id)
        resp = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "scope": POWERBI_SCOPE,
        })
        resp.raise_for_status()
        return resp.json()["access_token"]

    def export_pages_as_images(self, page_slot_map: dict[str, str]) -> dict[str, bytes]:
        """Export each Power BI report page to a PNG and return {slot: png_bytes}.

        Intended flow once access is approved:
          1. POST .../groups/{workspace_id}/reports/{report_id}/ExportTo {"format": "PNG"}
          2. Poll GET .../exports/{exportId} until status == "Succeeded"
          3. GET .../exports/{exportId}/file to download the rendered image(s)
        """
        raise NotImplementedError(
            "Power BI API access is still pending approval for this organization. "
            "Use the manual visual upload endpoint until this is enabled."
        )
