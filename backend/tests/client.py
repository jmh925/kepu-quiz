# -*- coding: utf-8 -*-
"""极简 HTTP 客户端（仅标准库）：供冒烟测试与验收脚本复用。

为什么不用 requests：测试脚本要求「零第三方依赖即可运行」，
这样在只装了 Python 的机器上也能复现论文第 6 章的实测数据。
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


def _encode_path(path):
    """只对路径部分做百分号编码，保留 / ? & = 等分隔符与已有的编码。"""
    if not any(ord(ch) > 127 for ch in path):
        return path
    parts = urllib.parse.urlsplit(path)
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe="/%"),
        urllib.parse.quote(parts.query, safe="=&%"),
        parts.fragment))


class Response(object):
    """统一响应对象：status / body(dict) / elapsed_ms / raw。"""

    def __init__(self, status, body, elapsed_ms, raw=""):
        self.status = status
        self.body = body if isinstance(body, dict) else {}
        self.elapsed_ms = elapsed_ms
        self.raw = raw

    @property
    def code(self):
        return self.body.get("code")

    @property
    def message(self):
        return self.body.get("message")

    @property
    def data(self):
        return self.body.get("data")

    def __repr__(self):
        return "<Response %s code=%s %.1fms>" % (self.status, self.code, self.elapsed_ms)


class Client(object):
    def __init__(self, base_url="http://127.0.0.1:8000", timeout=150):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token = None
        self.admin_token = None

    # ---------- 底层请求 ----------
    def request(self, method, path, json_body=None, headers=None, raw_body=None,
                content_type="application/json"):
        # 路径里的中文必须编码：题干会被放进 DELETE 路径，
        # 不编码时 urllib 会以 ascii 编解码失败（报 codec can't encode characters）。
        url = self.base_url + _encode_path(path)
        data = None
        hdrs = {"Accept": "application/json"}
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = content_type + "; charset=utf-8"
        elif raw_body is not None:
            data = raw_body
            hdrs["Content-Type"] = content_type
        if headers:
            hdrs.update(headers)
        if self.token:
            hdrs.setdefault("Authorization", "Bearer " + self.token)
        if self.admin_token:
            hdrs.setdefault("X-Admin-Token", self.admin_token)

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                status = resp.status
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        except Exception as exc:                       # 连接失败等
            return Response(0, {"code": -1, "message": str(exc), "data": None},
                            (time.time() - start) * 1000)
        elapsed = (time.time() - start) * 1000
        try:
            body = json.loads(text) if text else {}
        except ValueError:
            body = {"code": -1, "message": text[:200], "data": None}
        return Response(status, body, elapsed, text)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, json_body=None, **kw):
        return self.request("POST", path, json_body=json_body, **kw)

    def put(self, path, json_body=None, **kw):
        return self.request("PUT", path, json_body=json_body, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    # ---------- 业务快捷方法 ----------
    def login(self, nickname="测试小科学家", grade="primary_high"):
        resp = self.post("/api/v1/user/login", {"nickname": nickname, "grade": grade})
        if resp.code == 0:
            self.token = resp.data["token"]
        return resp

    def admin_login(self, username="admin", password="kepu@2026"):
        body = {"username": username, "password": password}
        headers = {"X-Admin-Token": ""}          # 登录接口本身不需要管理端 Token
        resp = self.post("/api/v1/admin/login", body, headers=headers)
        if resp.code == 0:
            self.admin_token = resp.data["token"]
        return resp

    def upload(self, path, filename, content, field="file"):
        """构造 multipart/form-data 请求（仅标准库）。"""
        boundary = "----kepuSmokeBoundary7d1a"
        if isinstance(content, str):
            content = content.encode("utf-8")
        body = b""
        body += ("--%s\r\n" % boundary).encode()
        body += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                 % (field, filename)).encode("utf-8")
        body += b"Content-Type: text/plain\r\n\r\n"
        body += content + b"\r\n"
        body += ("--%s--\r\n" % boundary).encode()
        return self.request("POST", path, raw_body=body,
                            content_type="multipart/form-data; boundary=%s" % boundary)
