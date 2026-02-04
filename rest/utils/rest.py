import yaml
import aiohttp
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List
from aiohttp import FormData


class AsyncRestUtil:
    DEFAULT_TIMEOUT = 10

    def __init__(self, config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        base = self.config.get("rest", {}).get("base", {})

        self.base_timeout = base.get("timeout", self.DEFAULT_TIMEOUT)
        self.log_pretty_req = base.get("log_pretty_req", False)
        self.log_pretty_res = base.get("log_pretty_res", False)
        self.log_pretty_head = base.get("log_pretty_head", False)
        self.is_log = base.get("is_log", True)

        self.domains = self.config["rest"]["domains"]
        self._req_seq = 0

    # ==================================================
    # PUBLIC
    # ==================================================
    async def call_all(self, requests_info: List[Dict[str, Any]]):
        async with aiohttp.ClientSession() as session:
            tasks = [self._call_one(session, info) for info in requests_info]
            return await asyncio.gather(*tasks, return_exceptions=False)

    # ==================================================
    # INTERNAL
    # ==================================================
    async def _call_one(self, session: aiohttp.ClientSession, info: Dict[str, Any]):
        self._req_seq += 1
        req_id = f"REQ-{self._req_seq:04d}"
        api_name = info["api_name"]

        domain = self.domains[info["domain_name"]]
        api = domain["apis"][api_name]

        timeout = (
                api.get("timeout")
                or domain.get("timeout")
                or self.base_timeout
        )

        url = domain["domain"] + self._replace(
            api["path"], info.get("path_params")
        )

        headers = self._replace_obj(
            api.get("headers", {}), info.get("header_params") or {}
        )

        body_def = api.get("body", {"type": "none"})
        body_type = body_def.get("type", "none")
        body_params = info.get("body_params") or {}

        json_data = None
        data = None
        result_value = None

        try:
            if body_type == "json":
                json_data = self._handle_json(body_def, body_params)
                result_value = json_data
            elif body_type == "text":
                data = self._handle_text(body_def, body_params)
                result_value = data
            elif body_type == "multipart":
                data = self._build_multipart(body_def, body_params)
                result_value = body_params  # multipart는 보낸 파라미터 정보 반환

            self._log_request(req_id, api_name, api["method"], url, headers, json_data, data, body_def, body_params)

            async with session.request(
                    method=api["method"],
                    url=url,
                    headers=headers if body_type != "multipart" else None,
                    params=info.get("query_params"),
                    json=json_data,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                text = await resp.text()
                self._log_response(req_id, api_name, resp.status, text)

                resp.raise_for_status()

                return {
                    "req_id": req_id,
                    "api_name": api_name,
                    "method": api["method"],
                    "url": url,
                    "headers": headers,
                    "bind_params": body_params,
                    "response_status": resp.status,
                    "response_body": text,
                    "params": result_value
                }

        except Exception as e:
            if self.is_log:
                print(f"\n===== ERROR [{req_id}] =====")
                print(str(e))
                print("============================")
            return {
                "req_id": req_id,
                "api_name": api_name,
                "error": str(e)
            }

    # ==================================================
    # BODY HANDLER
    # ==================================================
    def _handle_json(self, cfg, params):
        # 파일 기반 JSON 처리
        if "file_path" in cfg:
            raw = self._read_file(cfg["file_path"])
            data = json.loads(raw)
            return self._replace_obj(data, params)

        # inline value 처리
        value = cfg.get("value")
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            key = value[1:-1]  # "{result}" -> "result"
            if key in params:
                return params[key]  # list/dict이면 그대로 반환
            else:
                return value
        else:
            return self._replace_obj(value, params)

    def _handle_text(self, cfg, params):
        if "file_path" in cfg:
            return self._read_file(cfg["file_path"])
        return self._replace(cfg.get("value", ""), params)

    def _build_multipart(self, cfg, params):
        form = FormData()

        for f in cfg.get("files", []):
            key = f["path"].strip("{}")
            raw_path = str(params[key]).strip()

            raw_path = os.path.expandvars(os.path.expanduser(raw_path))
            path = Path(raw_path)

            if not path.is_absolute():
                path = Path(os.getcwd()) / path

            path = Path(os.path.realpath(path))

            if not path.exists() or not path.is_file():
                raise FileNotFoundError(f"multipart file not found: {path}")

            form.add_field(
                name=f["param"],
                value=path.open("rb"),
                filename=path.name,
                content_type="application/octet-stream",
            )

        data_fields = self._replace_obj(cfg.get("data", {}), params)
        for k, v in data_fields.items():
            form.add_field(k, str(v))

        return form

    # ==================================================
    # UTIL
    # ==================================================
    def _read_file(self, path: str):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        return p.read_text(encoding="utf-8")

    def _replace(self, text: str, params: Dict[str, Any]):
        if not params:
            return text
        for k, v in params.items():
            text = text.replace(f"{{{k}}}", str(v))
        return text

    def _replace_obj(self, obj, params: Dict[str, Any]):
        if isinstance(obj, dict):
            return {k: self._replace_obj(v, params) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._replace_obj(v, params) for v in obj]
        if isinstance(obj, str):
            return self._replace(obj, params)
        return obj

    # ==================================================
    # LOG
    # ==================================================
    def _pretty(self, obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

    def _log_request(self, req_id, api_name, method, url, headers, json_data, data, body_def=None, body_params=None):
        if not self.is_log:
            return
        print(f"\n===== REQUEST [{req_id}] =====")
        print(f"> {api_name}")
        print(f"{method} {url}")
        if headers:
            print("Headers:")
            if self.log_pretty_head:
                print(self._pretty(headers))
            else:
                print(headers)
        print("-----")
        if json_data is not None:
            print(self._pretty(json_data) if self.log_pretty_req else json_data)
        elif isinstance(data, str):
            print(data)
        elif isinstance(data, FormData) and body_def and body_params:
            print("MULTIPART: files + data")
            for f in body_def.get("files", []):
                key = f["path"].strip("{}")
                file_path = body_params[key]
                print(f"  File Param: {f['param']}, Filename: {Path(file_path).name}")
            data_fields = self._replace_obj(body_def.get("data", {}), body_params)
            for k, v in data_fields.items():
                print(f"  Data Param: {k}, Value: {v}")
        print("==============================")

    def _log_response(self, req_id, api_name, status, body):
        if not self.is_log:
            return
        print(f"\n===== RESPONSE [{req_id}] =====")
        print(f"> {api_name}")
        print("STATUS:", status)
        print("-----")
        if self.log_pretty_res:
            try:
                print(self._pretty(json.loads(body)))
            except Exception:
                print(body)
        else:
            print(body)
        print("==============================")
