import os
import time
import yaml
import requests
from typing import Any, Dict, Iterable, List, Optional, Union


def load_config(path: str = "./config/github.config.yml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class GitHubAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, response_text: str = ""):
        super().__init__(f"GitHub API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response_text = response_text


class GitHubAPI:
    def __init__(self, config_path: str = "./config/github.config.yml"):
        cfg = load_config(config_path)

        self.token = cfg["github"]["token"]
        self.base_url = cfg["github"]["base_url"].rstrip("/")
        self.timeout = int(cfg["github"].get("timeout", 30))
        self.user_agent = cfg["github"].get("user_agent", "python-github-api-client")
        self.accept = cfg["github"].get("accept", "application/vnd.github+json")
        self.auto_rate_limit_wait = bool(cfg["github"].get("auto_rate_limit_wait", True))
        self.max_retries = int(cfg["github"].get("max_retries", 3))
        self.retry_backoff_sec = float(cfg["github"].get("retry_backoff_sec", 1.0))

        self.session = requests.Session()

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": self.accept,
            "User-Agent": self.user_agent,
        }
        if extra:
            headers.update(extra)
        return headers

    def _full_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return self.base_url + path_or_url

    def _parse_next_link(self, link_header: Optional[str]) -> Optional[str]:
        if not link_header:
            return None
        parts = [p.strip() for p in link_header.split(",")]
        for part in parts:
            if 'rel="next"' in part:
                start = part.find("<") + 1
                end = part.find(">", start)
                if start > 0 and end > start:
                    return part[start:end]
        return None

    def _rate_limit_reset_epoch(self, headers: Dict[str, str]) -> Optional[int]:
        v = headers.get("X-RateLimit-Reset")
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def _maybe_wait_rate_limit(self, resp: requests.Response) -> bool:
        if not self.auto_rate_limit_wait:
            return False
        if resp.status_code not in (403, 429):
            return False
        remaining = resp.headers.get("X-RateLimit-Remaining")
        reset_epoch = self._rate_limit_reset_epoch(resp.headers)
        if remaining == "0" and reset_epoch:
            wait_sec = max(0, reset_epoch - int(time.time())) + 1
            time.sleep(wait_sec)
            return True
        if resp.status_code == 429:
            time.sleep(self.retry_backoff_sec)
            return True
        return False

    def request(
        self,
        method: str,
        path_or_url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        headers: Optional[Dict[str, str]] = None,
        paginate: bool = False,
        item_key: Optional[str] = None,
    ) -> Any:
        method = method.upper()
        url = self._full_url(path_or_url)
        req_headers = self._headers(headers)

        attempt = 0
        while True:
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    data=data,
                    headers=req_headers,
                    timeout=self.timeout,
                )
            except (requests.ConnectionError, requests.Timeout):
                attempt += 1
                if attempt > self.max_retries:
                    raise
                time.sleep(self.retry_backoff_sec * (2 ** (attempt - 1)))
                continue

            if self._maybe_wait_rate_limit(resp):
                attempt += 1
                if attempt > self.max_retries:
                    self._raise_for_status(resp)
                continue

            if resp.status_code in (502, 503, 504):
                attempt += 1
                if attempt > self.max_retries:
                    self._raise_for_status(resp)
                time.sleep(self.retry_backoff_sec * (2 ** (attempt - 1)))
                continue

            if not (200 <= resp.status_code < 300):
                self._raise_for_status(resp)

            if not paginate:
                return self._decode(resp)

            return self._paginate_collect(resp, method, json, data, req_headers, item_key)

    def _paginate_collect(
        self,
        first_resp: requests.Response,
        method: str,
        json: Optional[Dict[str, Any]],
        data: Optional[Union[Dict[str, Any], str, bytes]],
        headers: Dict[str, str],
        item_key: Optional[str],
    ) -> Any:
        first_payload = self._decode(first_resp)

        if item_key and isinstance(first_payload, dict):
            agg: List[Any] = list(first_payload.get(item_key, []))
        elif isinstance(first_payload, list):
            agg = list(first_payload)
        else:
            return first_payload

        next_url = self._parse_next_link(first_resp.headers.get("Link"))
        while next_url:
            resp = self.session.request(
                method,
                next_url,
                headers=headers,
                timeout=self.timeout,
            )

            if self._maybe_wait_rate_limit(resp):
                continue

            if not (200 <= resp.status_code < 300):
                self._raise_for_status(resp)

            payload = self._decode(resp)
            if item_key and isinstance(payload, dict):
                agg.extend(payload.get(item_key, []))
            elif isinstance(payload, list):
                agg.extend(payload)
            else:
                agg.append(payload)

            next_url = self._parse_next_link(resp.headers.get("Link"))

        if item_key and isinstance(first_payload, dict):
            out = dict(first_payload)
            out[item_key] = agg
            return out

        return agg

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        gql_url = self.base_url + "/graphql"
        return self.request(
            "POST",
            gql_url,
            json={"query": query, "variables": variables or {}},
        )

    def _decode(self, resp: requests.Response) -> Any:
        if resp.status_code == 204:
            return None
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct or "application/vnd.github+json" in ct:
            return resp.json()
        return resp.text

    def _raise_for_status(self, resp: requests.Response) -> None:
        try:
            payload = resp.json()
            message = payload.get("message", resp.reason)
        except Exception:
            message = resp.reason
        raise GitHubAPIError(resp.status_code, message, resp.text)


if __name__ == "__main__":
    gh = GitHubAPI("./config/github.config.yml")
    user = gh.request("GET", "/user")
    print(user["login"])