import re
from dataclasses import dataclass, field
from email.utils import formatdate
from http import HTTPStatus
from typing import Dict, List


TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


@dataclass
class Request:
    method: str
    target: str
    headers: Dict[str, List[str]]

    @property
    def close(self):
        values = ",".join(self.headers.get("connection", [])).lower().split(",")
        return "close" in [value.strip() for value in values]


@dataclass
class Response:
    status: int
    message: str
    headers: Dict[str, str] = field(default_factory=dict)


class RequestReader:
    def __init__(self, client, header_limit=16384, body_limit=1048576):
        self._client = client
        self._pending = b""
        self._header_limit = header_limit
        self._body_limit = body_limit

    def read(self):
        while b"\r\n\r\n" not in self._pending:
            if len(self._pending) > self._header_limit:
                raise ValueError("Headers too large")
            data = self._client.recv(4096)
            if not data:
                if self._pending:
                    raise ValueError("Incomplete request")
                return None
            self._pending += data

        header, self._pending = self._pending.split(b"\r\n\r\n", 1)
        if len(header) > self._header_limit:
            raise ValueError("Headers too large")
        request = self._parse_header(header)
        length = self._body_length(request.headers)
        while len(self._pending) < length:
            data = self._client.recv(min(4096, length - len(self._pending)))
            if not data:
                raise ValueError("Incomplete body")
            self._pending += data
        self._pending = self._pending[length:]
        return request

    def _parse_header(self, header):
        lines = header.decode("iso-8859-1").split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) != 3:
            raise ValueError("Invalid request line")
        method, target, version = parts
        if not TOKEN.fullmatch(method) or version != "HTTP/1.1":
            raise ValueError("Invalid request line")
        if not target.startswith("/") or any(ord(char) <= 32 or ord(char) >= 127 for char in target):
            raise ValueError("Invalid request target")

        headers = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if not separator or not TOKEN.fullmatch(name):
                raise ValueError("Invalid header")
            if any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in value):
                raise ValueError("Invalid header value")
            headers.setdefault(name.lower(), []).append(value.strip(" \t"))
        return Request(method, target, headers)

    def _body_length(self, headers):
        if "transfer-encoding" in headers:
            raise ValueError("Transfer-Encoding is not supported")
        lengths = headers.get("content-length", ["0"])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
            raise ValueError("Invalid Content-Length")
        length = int(lengths[0])
        if length > self._body_limit:
            raise ValueError("Body too large")
        return length


class ResponseWriter:
    def __init__(self, client):
        self._client = client

    def write(self, response, close=False, head=False):
        body = response.message.encode("utf-8")
        headers = [
            f"HTTP/1.1 {response.status} {HTTPStatus(response.status).phrase}",
            f"Date: {formatdate(usegmt=True)}",
            "Content-Type: text/plain; charset=utf-8",
            f"Content-Length: {len(body)}",
            "Connection: close" if close else "Connection: keep-alive",
        ]
        headers.extend(f"{name}: {value}" for name, value in response.headers.items())
        data = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")
        self._client.sendall(data + (b"" if head else body))
