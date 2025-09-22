from config import API
from typing import List, Dict, Optional
from urllib.parse import urlparse
import logging

logger = logging.getLogger("HackerOneAPI")


class HackerOneAPI(API):
    def __init__(self, username: str, token: str) -> None:
        """
        Initialize a new HackerOneAPI object with the given API credentials.
        """
        super().__init__(base_url="https://api.hackerone.com")
        self.username = username
        self.token = token
        self.session.auth = (self.username, self.token)
        # preserve existing headers behavior
        self.session.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            )
        }

    def _build_url(self, endpoint: str) -> str:
        """
        Return a full URL for the given endpoint. If the endpoint is already
        an absolute URL, return it unchanged. Otherwise prepend base_url.
        """
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        # allow both "/v1/..." and "v1/..." forms
        if endpoint.startswith("/"):
            return f"{self.base_url}{endpoint}"
        return f"{self.base_url}/{endpoint}"

    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """
        Wrapper around session.get that accepts either a full URL or a relative path.
        Returns parsed JSON (raises on non-2xx).
        """
        url = self._build_url(endpoint)
        # Use the underlying session (assumed to be httpx or requests-like)
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def paginate(self, endpoint: str, params: Optional[Dict] = None, max_pages: int = 500) -> List[dict]:
        """
        Retrieve all paginated results from the given API endpoint.

        Args:
            endpoint: initial endpoint or full URL to request.
            params: query params for the first request (e.g. {'page[size]': 100}).
            max_pages: safety cap to prevent infinite loops.

        Returns:
            List of page JSON objects (each page as returned by the API).
        """
        results: List[dict] = []
        # Start with the provided endpoint (could be relative or absolute)
        next_url: Optional[str] = endpoint
        current_params = params or {"page[size]": 100}
        page_count = 0

        while next_url:
            page_count += 1
            logger.info(f"HackerOne paginate: fetching page #{page_count}: {next_url}")

            try:
                response_json = self.get(next_url, params=current_params)
            except Exception as e:
                logger.error(f"Failed fetching {next_url}: {e}")
                # stop pagination on failure
                break

            results.append(response_json)

            # safety cap
            if page_count >= max_pages:
                logger.warning(f"Reached max_pages={max_pages}, stopping pagination.")
                break

            # After the first request, no additional params are required because
            # the 'next' link contains the query string already.
            current_params = None

            # Extract the next link (if any). HackerOne returns a full URL in links.next.
            next_link = response_json.get("links", {}).get("next")
            if not next_link:
                # no more pages
                break

            # Use the full next_link as-is (get() will accept absolute URLs).
            next_url = next_link

        return results

    def program_info(self, scope: str) -> dict:
        """
        Gather structured_scopes for a given program 'scope' (handle).
        """
        data = []
        # Use a relative endpoint; paginate will build full URLs as needed.
        endpoint = f"/v1/hackers/programs/{scope}/structured_scopes"
        for structured_scope in self.paginate(endpoint):
            if isinstance(structured_scope, dict) and "data" in structured_scope:
                data.extend(structured_scope["data"])

        return {"relationships": {"structured_scopes": {"data": data}}}

    def brief(self, results: List[dict]) -> List[dict]:
        """
        Produce a reduced summary ("brief") of the raw results.
        """
        return [
            {
                "handle": result.get("attributes", {}).get("handle", "unknown"),
                "bounty": 1 if result.get("attributes", {}).get("offers_bounties", False) else 0,
                "active": 1 if result.get("attributes", {}).get("submission_state") == "open" else 0,
                "assets": {
                    "in_scope": [
                        {
                            "identifier": scope.get("attributes", {}).get("asset_identifier", "unknown"),
                            "type": scope.get("attributes", {}).get("asset_type", "unknown"),
                        }
                        for scope in result.get("relationships", {}).get("structured_scopes", {}).get("data", [])
                        if scope.get("attributes", {}).get("eligible_for_submission", False)
                    ],
                    "out_of_scope": [
                        {
                            "identifier": scope.get("attributes", {}).get("asset_identifier", "unknown"),
                            "type": scope.get("attributes", {}).get("asset_type", "unknown"),
                        }
                        for scope in result.get("relationships", {}).get("structured_scopes", {}).get("data", [])
                        if not scope.get("attributes", {}).get("eligible_for_submission", True)
                    ],
                },
            }
            for result in results if isinstance(result, dict)
        ]
