import time
import json
import yaml
import requests
import subprocess
from typing import Any, Dict, List, Optional, Union
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
        if path_or_url.startswith("http"):
            return path_or_url
        if not path_or_url.startswith("/"):
            path_or_url = "/" + path_or_url
        return self.base_url + path_or_url

    def _decode(self, text: str):
        try:
            return json.loads(text)
        except Exception:
            return text

    def _curl_request(self, method, url, headers, params, body):

        if params:
            parts = urlsplit(url)
            existing = dict(parse_qsl(parts.query, keep_blank_values=True))
            merged = {**existing, **params}
            query = urlencode(merged, doseq=True)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

        cmd = ["curl", "-sS", "-X", method]

        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]

        if self.proxies.get("https"):
            cmd += ["-x", self.proxies["https"]]

        if body:
            cmd += ["-d", json.dumps(body)]

        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.returncode != 0:
            if "407" in result.stderr:
                raise ProxyAuthError(
                    407,
                    "Proxy authentication required. Check proxy credentials or proxy configuration.",
                    result.stderr
                )
            raise RuntimeError(result.stderr)

        return self._decode(result.stdout)

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
    ):
        method = method.upper()
        url = self._full_url(path_or_url)
        req_headers = self._headers(headers)

        if not self.is_session:
            return self._curl_request(method, url, req_headers, params, json or data)

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
                    raise RuntimeError(str(e))
                time.sleep(self.retry_backoff_sec * (2 ** (attempt - 1)))
                continue

            if resp.status_code == 407:
                raise ProxyAuthError(
                    407,
                    "Proxy authentication required. Check proxy credentials or proxy configuration.",
                    resp.text
                )

            if not (200 <= resp.status_code < 300):
                raise GitHubAPIError(resp.status_code, resp.reason, resp.text)

            if not paginate:
                return resp.json() if "json" in resp.headers.get("Content-Type", "") else resp.text

            return self._paginate_collect(resp, method, json, data, req_headers, item_key)

    def _parse_next_link(self, link_header):
        if not link_header:
            return None
        parts = link_header.split(",")
        for p in parts:
            if 'rel="next"' in p:
                start = p.find("<") + 1
                end = p.find(">")
                return p[start:end]
        return None

    def _paginate_collect(self, first_resp, method, json_body, data, headers, item_key):

        payload = first_resp.json()

        if item_key and isinstance(payload, dict):
            result = list(payload.get(item_key, []))
        elif isinstance(payload, list):
            result = list(payload)
        else:
            return payload

        next_url = self._parse_next_link(first_resp.headers.get("Link"))

        while next_url:

            resp = self.session.request(
                method,
                next_url,
                headers=headers,
                timeout=self.timeout,
                verify=self.verify,
            )

            if not (200 <= resp.status_code < 300):
                raise GitHubAPIError(resp.status_code, resp.reason, resp.text)

            data = resp.json()

            if item_key and isinstance(data, dict):
                result.extend(data.get(item_key, []))
            elif isinstance(data, list):
                result.extend(data)

            next_url = self._parse_next_link(resp.headers.get("Link"))

        if item_key and isinstance(payload, dict):
            payload[item_key] = result
            return payload

        return result

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None):

        url = self.base_url + "/graphql"

        return self.request(
            "POST",
            url,
            json={"query": query, "variables": variables or {}},
        )


def get_prs_created_by_users(
    gh,
    owner: str,
    repo: str,
    users: Optional[List[str]] = None,
    state: str = "all",
) -> List[Dict[str, Any]]:

    if not users:
        prs = gh.request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": 100},
            paginate=True,
        )
        return [
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "state": pr["state"],
                "url": pr["html_url"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
            }
            for pr in prs
        ]

    merged = {}
    for u in users:
        q = f"is:pr repo:{owner}/{repo} author:{u}"
        if state in ("open", "closed"):
            q += f" state:{state}"

        res = gh.request(
            "GET",
            "/search/issues",
            params={"q": q, "per_page": 100, "sort": "created", "order": "desc"},
            paginate=True,
            item_key="items",
        )

        for it in res.get("items", []):
            merged[it["number"]] = {
                "number": it["number"],
                "title": it["title"],
                "state": it["state"],
                "url": it["html_url"],
                "created_at": it["created_at"],
                "updated_at": it["updated_at"],
                "author": u,
            }

    return sorted(merged.values(), key=lambda x: (x["created_at"], x["number"]), reverse=True)


def get_pr_detail(gh, owner: str, repo: str, pr_number: int):
    return gh.request("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")


def get_pr_files(gh, owner: str, repo: str, pr_number: int):
    return gh.request(
        "GET",
        f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
        params={"per_page": 100},
        paginate=True,
    )


if __name__ == "__main__":

    gh = GitHubAPI("./config/github.config.yml")

    result = gh.request("GET", "/user")
    gh.print_output(result)

    result = get_prs_created_by_users(
        gh,
        owner="YOUR_ORG",
        repo="abc",
        users=["user1", "user2"],
        state="all",
    )
    gh.print_output(result)

    result = get_pr_detail(gh, "YOUR_ORG", "abc", 123)
    gh.print_output(result)

    result = get_pr_files(gh, "YOUR_ORG", "abc", 123)
    gh.print_output(result)