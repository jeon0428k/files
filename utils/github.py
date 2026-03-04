import os
import time
import json
import yaml
import requests
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Union, Tuple
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl


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
        self.is_session = bool(gh.get("is_session", True))
        self.is_pretty_console = bool(gh.get("is_pretty_console", False))
        self.is_limit = bool(gh.get("is_limit", True))

        proxy_cfg = (gh.get("proxy") or {})
        proxies = {
            "http": proxy_cfg.get("http"),
            "https": proxy_cfg.get("https"),
        }
        self.proxies = {k: v for k, v in proxies.items() if v}

        self.verify_ssl = bool(proxy_cfg.get("verify_ssl", True))
        self.ca_bundle = (proxy_cfg.get("ca_bundle") or "").strip()
        self.verify = self.ca_bundle if self.ca_bundle else self.verify_ssl

        self.session = None
        if self.is_session:
            self.session = requests.Session()
            if self.proxies:
                self.session.proxies.update(self.proxies)

    def print_output(self, data: Any):
        if isinstance(data, (dict, list)):
            if self.is_pretty_console:
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(json.dumps(data, ensure_ascii=False))
        else:
            print(data)

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

    def _decode_text(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return text

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

    def _friendly_proxy_407_message(self, via: str = "", proxy_auth: str = "") -> str:
        parts = ["Proxy authentication required (HTTP 407)."]
        if proxy_auth:
            parts.append(f"Proxy-Authenticate: {proxy_auth}")
        if via:
            parts.append(f"Via: {via}")
        if self.proxies:
            cfg = []
            if self.proxies.get("http"):
                cfg.append(f"http={self.proxies['http']}")
            if self.proxies.get("https"):
                cfg.append(f"https={self.proxies['https']}")
            parts.append("Configured proxy: " + " / ".join(cfg))
        parts.append("Check proxy credentials (user:pass@proxy:port), corporate SSO approval, or ask IT for the correct proxy settings.")
        return " ".join([p for p in parts if p]).strip()

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 407:
            via = resp.headers.get("Via", "") or ""
            proxy_auth = resp.headers.get("Proxy-Authenticate", "") or ""
            raise ProxyAuthError(resp.status_code, self._friendly_proxy_407_message(via=via, proxy_auth=proxy_auth), resp.text)

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

    def _merge_url_params(self, url: str, params: Optional[Dict[str, Any]]) -> str:
        if not params:
            return url
        parts = urlsplit(url)
        existing = dict(parse_qsl(parts.query, keep_blank_values=True))
        merged = {**existing, **params}
        query = urlencode(merged, doseq=True)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    def _curl_call(self, method: str, url: str, headers: Dict[str, str], body: Any) -> Tuple[int, Dict[str, str], str]:
        with tempfile.NamedTemporaryFile(delete=False) as hf:
            header_path = hf.name

        cmd = ["curl", "-sS", "-X", method, "-D", header_path]

        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]

        if self.proxies.get("https"):
            cmd += ["-x", self.proxies["https"]]
        elif self.proxies.get("http"):
            cmd += ["-x", self.proxies["http"]]

        if self.ca_bundle:
            cmd += ["--cacert", self.ca_bundle]
        elif self.verify is False:
            cmd += ["-k"]

        if body is not None:
            cmd += ["-H", "Content-Type: application/json"]
            cmd += ["-d", json.dumps(body, ensure_ascii=False)]

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        finally:
            try:
                with open(header_path, "r", encoding="utf-8", errors="replace") as f:
                    raw_headers = f.read()
            except Exception:
                raw_headers = ""
            try:
                os.unlink(header_path)
            except Exception:
                pass

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(stderr if stderr else "curl failed")

        status_code, parsed_headers = self._parse_curl_headers(raw_headers)
        body_text = result.stdout or ""
        return status_code, parsed_headers, body_text

    def _parse_curl_headers(self, raw: str) -> Tuple[int, Dict[str, str]]:
        lines = [ln.rstrip("\r\n") for ln in (raw or "").splitlines()]
        status_code = 0
        headers: Dict[str, str] = {}

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.lower().startswith("http/"):
                headers = {}
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    status_code = int(parts[1])
                i += 1
                while i < len(lines) and lines[i].strip() != "":
                    hline = lines[i]
                    if ":" in hline:
                        k, v = hline.split(":", 1)
                        headers[k.strip()] = v.strip()
                    i += 1
            i += 1

        return status_code, headers

    def _curl_request_once(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]],
        body: Any,
    ) -> Tuple[Any, Dict[str, str], int]:
        final_url = self._merge_url_params(url, params)
        status_code, resp_headers, body_text = self._curl_call(method, final_url, headers, body)

        if status_code == 407:
            via = resp_headers.get("Via", "") or ""
            proxy_auth = resp_headers.get("Proxy-Authenticate", "") or ""
            raise ProxyAuthError(407, self._friendly_proxy_407_message(via=via, proxy_auth=proxy_auth), body_text)

        if not (200 <= status_code < 300):
            msg = resp_headers.get("Status", "") or "Request failed"
            raise GitHubAPIError(status_code, msg, body_text)

        return self._decode_text(body_text), resp_headers, status_code

    def _curl_collect_all_pages(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]],
        body: Any,
        item_key: Optional[str],
    ) -> Any:
        aggregated: List[Any] = []
        first_payload, resp_headers, _ = self._curl_request_once(method, url, headers, params, body)

        if item_key and isinstance(first_payload, dict):
            aggregated.extend(list(first_payload.get(item_key, [])))
            payload_kind = "dict_items"
            base_payload = dict(first_payload)
        elif isinstance(first_payload, list):
            aggregated.extend(list(first_payload))
            payload_kind = "list"
            base_payload = None
        else:
            return first_payload

        next_url = self._parse_next_link(resp_headers.get("Link"))
        while next_url:
            payload, resp_headers, _ = self._curl_request_once(method, next_url, headers, None, None)
            if payload_kind == "dict_items":
                if isinstance(payload, dict):
                    aggregated.extend(list(payload.get(item_key or "items", [])))
                else:
                    aggregated.append(payload)
            else:
                if isinstance(payload, list):
                    aggregated.extend(payload)
                else:
                    aggregated.append(payload)
            next_url = self._parse_next_link(resp_headers.get("Link"))

        if payload_kind == "dict_items":
            base_payload[item_key] = aggregated
            return base_payload
        return aggregated

    def _requests_collect_all_pages(
        self,
        first_resp: requests.Response,
        method: str,
        json_body: Optional[Dict[str, Any]],
        data_body: Optional[Union[Dict[str, Any], str, bytes]],
        headers: Dict[str, str],
        item_key: Optional[str],
    ) -> Any:
        first_payload = self._decode_requests(first_resp)

        if item_key and isinstance(first_payload, dict):
            agg: List[Any] = list(first_payload.get(item_key, []))
            payload_kind = "dict_items"
            base_payload = dict(first_payload)
        elif isinstance(first_payload, list):
            agg = list(first_payload)
            payload_kind = "list"
            base_payload = None
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

            payload = self._decode_requests(resp)
            if payload_kind == "dict_items":
                if isinstance(payload, dict):
                    agg.extend(payload.get(item_key, []))
                else:
                    agg.append(payload)
            else:
                if isinstance(payload, list):
                    agg.extend(payload)
                else:
                    agg.append(payload)

            next_url = self._parse_next_link(resp.headers.get("Link"))

        if payload_kind == "dict_items":
            base_payload[item_key] = agg
            return base_payload
        return agg

    def _decode_requests(self, resp: requests.Response) -> Any:
        if resp.status_code == 204:
            return None
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct or "application/vnd.github+json" in ct:
            return resp.json()
        return resp.text

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

        should_collect_all = bool(paginate) and (not self.is_limit)

        if not self.is_session:
            if should_collect_all:
                return self._curl_collect_all_pages(method, url, req_headers, params, json if json is not None else data, item_key)
            payload, _, _ = self._curl_request_once(method, url, req_headers, params, json if json is not None else data)
            return payload

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
                return self._decode_requests(resp)

            if self.is_limit:
                return self._decode_requests(resp)

            return self._requests_collect_all_pages(resp, method, json, data, req_headers, item_key)

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        url = self.base_url + "/graphql"
        return self.request(
            "POST",
            url,
            json={"query": query, "variables": variables or {}},
            paginate=False,
        )


if __name__ == "__main__":
    gh = GitHubAPI("./config/github.config.yml")
    result = gh.request("GET", "/user")
    gh.print_output(result)