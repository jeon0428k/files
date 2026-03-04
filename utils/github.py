import os
import time
import yaml
import requests
from typing import Any, Dict, List, Optional, Union


def load_config(path: str = "./config/github.config.yml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class GitHubAPIError(RuntimeError):
    def __init__(self, status_code: int, message: str, response_text: str = ""):
        super().__init__(f"GitHub API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response_text = response_text


class ProxyAuthError(GitHubAPIError):
    pass


class GitHubAPI:
    def __init__(self, config_path: str = "./config/github.config.yml"):
        cfg = load_config(config_path)
        gh = cfg["github"]

        self.token = gh["token"]
        self.base_url = gh["base_url"].rstrip("/")
        self.timeout = int(gh.get("timeout", 30))
        self.user_agent = gh.get("user_agent", "python-github-api-client")
        self.accept = gh.get("accept", "application/vnd.github+json")
        self.auto_rate_limit_wait = bool(gh.get("auto_rate_limit_wait", True))
        self.max_retries = int(gh.get("max_retries", 3))
        self.retry_backoff_sec = float(gh.get("retry_backoff_sec", 1.0))

        proxy_cfg = (gh.get("proxy") or {})
        proxies = {
            "http": proxy_cfg.get("http"),
            "https": proxy_cfg.get("https"),
        }
        self.proxies = {k: v for k, v in proxies.items() if v}

        self.verify_ssl = bool(proxy_cfg.get("verify_ssl", True))
        self.ca_bundle = (proxy_cfg.get("ca_bundle") or "").strip()
        self.verify = self.ca_bundle if self.ca_bundle else self.verify_ssl

        no_proxy = proxy_cfg.get("no_proxy")
        if no_proxy:
            os.environ["NO_PROXY"] = str(no_proxy)
            os.environ["no_proxy"] = str(no_proxy)

        self.session = requests.Session()
        if self.proxies:
            self.session.proxies.update(self.proxies)

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
                    verify=self.verify,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                attempt += 1
                if attempt > self.max_retries:
                    raise RuntimeError(f"Request failed after retries: {e}") from e
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
                verify=self.verify,
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

    def _friendly_proxy_407_message(self, resp: requests.Response) -> str:
        proxy_auth = resp.headers.get("Proxy-Authenticate", "") or ""
        via = resp.headers.get("Via", "") or ""
        proxy_conn = resp.headers.get("Proxy-Connection", "") or ""
        server = resp.headers.get("Server", "") or ""

        hint_parts = []
        if proxy_auth:
            hint_parts.append(f"Proxy-Authenticate: {proxy_auth}")
        if via:
            hint_parts.append(f"Via: {via}")
        if proxy_conn:
            hint_parts.append(f"Proxy-Connection: {proxy_conn}")
        if server:
            hint_parts.append(f"Server: {server}")

        proxy_urls = []
        if self.proxies.get("http"):
            proxy_urls.append(f"http={self.proxies['http']}")
        if self.proxies.get("https"):
            proxy_urls.append(f"https={self.proxies['https']}")

        proxy_cfg_hint = ""
        if proxy_urls:
            proxy_cfg_hint = " / ".join(proxy_urls)

        base = "Proxy authentication required (HTTP 407)."
        details = " ".join(hint_parts).strip()
        cfg = f"Configured proxy: {proxy_cfg_hint}".strip() if proxy_cfg_hint else "No proxy configured in client."
        action = (
            "Check proxy credentials (user:pass@proxy:port), corporate SSO approval, or ask your IT for the correct proxy settings."
        )

        msg = base
        if details:
            msg += " " + details
        msg += " " + cfg + " " + action
        return msg.strip()

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 407:
            raise ProxyAuthError(resp.status_code, self._friendly_proxy_407_message(resp), resp.text)

        try:
            payload = resp.json()
            message = payload.get("message", resp.reason)
            if isinstance(payload, dict) and "errors" in payload and isinstance(payload["errors"], list):
                details = "; ".join(
                    str(e.get("message", "")) for e in payload["errors"] if isinstance(e, dict) and e.get("message")
                )
                if details:
                    message = (message + " " + details).strip()
        except Exception:
            message = resp.reason or "Request failed"

        raise GitHubAPIError(resp.status_code, message, resp.text)


if __name__ == "__main__":
    gh = GitHubAPI("./config/github.config.yml")
    me = gh.request("GET", "/user")
    print(me["login"])