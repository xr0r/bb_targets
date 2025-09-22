from config import API
from typing import List, Dict
from urllib.parse import urlparse

class HackerOneAPI(API):
    def __init__(self, username: str, token: str) -> None:
        """
        Initialize a new HackerOneAPI object with the given API credentials.
        """
        super().__init__(base_url="https://api.hackerone.com")
        self.username = username
        self.token = token
        self.session.auth = (self.username, self.token)
        self.session.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            )
        }

    def paginate(self, endpoint: str, params: Dict = None) -> List[dict]:
        """
        Retrieve all paginated results from the given API endpoint.
        """
        results = []
        url = endpoint
        params = params or {"page[size]": 100}

        while url:
            response_json = self.get(url, params=params)
            results.append(response_json)

            # reset params after first call because `next` already contains them
            params = None  

            # follow next link if exists
            url = response_json.get("links", {}).get("next")

            # normalize if full URL is returned
            if url:
                parsed = urlparse(url)
                url = parsed.path + ("?" + parsed.query if parsed.query else "")

        return results

    def program_info(self, scope: str) -> dict:
        """
        Gathering information of a scope with the HackerOne API.
        """
        data = []
        for structured_scope in self.paginate(
            f"/v1/hackers/programs/{scope}/structured_scopes"
        ):
            if "data" in structured_scope:
                data.extend(structured_scope["data"])

        return {"relationships": {"structured_scopes": {"data": data}}}

    def brief(self, results: dict) -> list:
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
