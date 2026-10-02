"""Asynchronous HTTP client for Meetily Pro Automation API."""

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from backend.config import settings
from backend.meetily.errors import (
    MeetilyAuthError,
    MeetilyConnectionError,
    MeetilyInvalidResponse,
    MeetilyNotFound,
    MeetilyServerError,
)
from backend.meetily.schema_adapter import MeetilySchemaAdapter
from backend.schemas.meeting import MeetingMetadata, MeetingSummary, MeetingTranscript


class MeetilyClient:
    """Async client interacting with local Meetily Pro gateway on loopback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ):
        self.base_url = (base_url or settings.MEETILY_BASE_URL).rstrip("/")
        self.api_token = api_token or (
            settings.MEETILY_API_TOKEN.get_secret_value() if settings.MEETILY_API_TOKEN else None
        )
        self.timeout = timeout_seconds or settings.MEETILY_TIMEOUT_SECONDS
        self._external_client = client
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute HTTP request with retries on 5xx or network errors."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._get_headers()
        timeout = httpx.Timeout(timeout=self.timeout, connect=5.0)

        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                # Use injected client if provided (useful for tests)
                if self._external_client:
                    response = await self._external_client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                        timeout=timeout,
                    )
                else:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.request(
                            method=method,
                            url=url,
                            headers=headers,
                            params=params,
                            json=json_data,
                        )

                # Check HTTP status codes
                if response.status_code == 200 or response.status_code == 201:
                    try:
                        return response.json()
                    except Exception as e:
                        raise MeetilyInvalidResponse(f"Failed to parse JSON response: {str(e)}") from e

                if response.status_code in (401, 403):
                    raise MeetilyAuthError(
                        f"Authentication failed: HTTP {response.status_code}",
                        status_code=response.status_code,
                    )

                if response.status_code == 404:
                    raise MeetilyNotFound(f"Resource not found at {path}")

                if response.status_code >= 500:
                    last_error = MeetilyServerError(
                        f"Meetily server returned error: HTTP {response.status_code}",
                        status_code=response.status_code,
                    )
                    # Retry on 5xx
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                        continue
                    raise last_error

                # Other 4xx
                raise MeetilyInvalidResponse(f"Unexpected HTTP {response.status_code} from Meetily")

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = MeetilyConnectionError(
                    f"Connection to Meetily failed: {type(e).__name__}", details=str(e)
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self.backoff_factor * (2 ** (attempt - 1)))
                    continue
                raise last_error from e

        if last_error:
            raise last_error
        raise MeetilyConnectionError("Max retries exceeded connecting to Meetily")

    async def health(self) -> Dict[str, Any]:
        """Check Meetily Pro gateway health."""
        return await self._request("GET", "/health")

    async def whoami(self) -> Dict[str, Any]:
        """Query token credentials and scopes."""
        return await self._request("GET", "/v1/whoami")

    async def openapi(self) -> Dict[str, Any]:
        """Fetch the live OpenAPI schema."""
        return await self._request("GET", "/openapi.json")

    async def list_meetings(
        self, limit: int = 50, cursor: Optional[str] = None
    ) -> List[MeetingMetadata]:
        """List meetings available on the Meetily gateway."""
        params: Dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/v1/meetings", params=params)

        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("meetings") or data.get("items") or data.get("data") or []

        return [MeetilySchemaAdapter.parse_meeting_metadata(item) for item in items if isinstance(item, dict)]

    async def iter_meetings(self, batch_size: int = 50) -> AsyncIterator[MeetingMetadata]:
        """Async iterator yielding meetings with pagination."""
        cursor = None
        while True:
            params: Dict[str, Any] = {"limit": batch_size}
            if cursor:
                params["cursor"] = cursor
            data = await self._request("GET", "/v1/meetings", params=params)

            items = []
            next_cursor = None
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("meetings") or data.get("items") or []
                next_cursor = data.get("next_cursor") or data.get("cursor")

            if not items:
                break

            for item in items:
                if isinstance(item, dict):
                    yield MeetilySchemaAdapter.parse_meeting_metadata(item)

            if not next_cursor:
                break
            cursor = next_cursor

    async def get_meeting(self, meeting_id: str) -> MeetingMetadata:
        """Fetch meeting metadata by id."""
        data = await self._request("GET", f"/v1/meetings/{meeting_id}")
        return MeetilySchemaAdapter.parse_meeting_metadata(data)

    async def get_transcript(self, meeting_id: str) -> MeetingTranscript:
        """Fetch transcript segments for a meeting."""
        data = await self._request("GET", f"/v1/meetings/{meeting_id}/transcript")
        return MeetilySchemaAdapter.parse_transcript(meeting_id, data)

    async def get_summary(self, meeting_id: str) -> MeetingSummary:
        """Fetch meeting summary and action items."""
        data = await self._request("GET", f"/v1/meetings/{meeting_id}/summary")
        return MeetilySchemaAdapter.parse_summary(meeting_id, data)

    async def export_meeting(self, meeting_id: str, format: str = "json") -> Any:
        """Export full meeting packet in requested format."""
        return await self._request("GET", f"/v1/meetings/{meeting_id}/export", params={"format": format})

    async def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search meetings by keyword."""
        data = await self._request("GET", "/v1/search", params={"q": query, "limit": limit})
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get("results") or data.get("items") or []
        return []
