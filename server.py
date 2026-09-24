import argparse
import math
import re
import socket
import threading
from email.utils import formatdate
from urllib.parse import parse_qs, urlsplit


HEADER_LIMIT = 16384
BODY_LIMIT = 1048576
IDLE_TIMEOUT = 30
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def read_request(client, pending):
    while b"\r\n\r\n" not in pending:
        if len(pending) > HEADER_LIMIT:
            raise ValueError("Headers too large")
        data = client.recv(4096)
        if not data:
            if pending:
                raise ValueError("Incomplete request")
            return None, b""
        pending += data

    header, pending = pending.split(b"\r\n\r\n", 1)
    if len(header) > HEADER_LIMIT:
        raise ValueError("Headers too large")
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

    if "transfer-encoding" in headers:
        raise ValueError("Transfer-Encoding is not supported")
    lengths = headers.get("content-length", ["0"])
    if len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0]):
        raise ValueError("Invalid Content-Length")
    length = int(lengths[0])
    if length > BODY_LIMIT:
        raise ValueError("Body too large")

    while len(pending) < length:
        data = client.recv(min(4096, length - len(pending)))
        if not data:
            raise ValueError("Incomplete body")
        pending += data
    return (method, target, headers), pending[length:]


def calculate(method, target, headers):
    hosts = headers.get("host", [])
    if len(hosts) != 1 or not hosts[0]:
        return 400, "Host is required"
    if method != "GET":
        return 405, "Method not allowed"
    try:
        address = urlsplit(target)
        if address.netloc or address.fragment:
            return 400, "Invalid request target"
        if address.path not in ("/add", "/sub", "/mul", "/div"):
            return 404, "Not found"
        values = parse_qs(address.query, keep_blank_values=True, max_num_fields=20)
        if any(len(values.get(name, [])) != 1 for name in ("a", "b")):
            return 400, "Provide one a and one b"
        if any(not NUMBER.fullmatch(values[name][0]) for name in ("a", "b")):
            return 400, "Invalid number"
        a = float(values["a"][0])
        b = float(values["b"][0])
        if not math.isfinite(a) or not math.isfinite(b):
            return 400, "Invalid number"
        if address.path == "/add":
            result = a + b
        elif address.path == "/sub":
            result = a - b
        elif address.path == "/mul":
            result = a * b
        else:
            if b == 0:
                return 400, "Cannot divide by zero"
            result = a / b
        if not math.isfinite(result):
            return 400, "Result is too large"
        return 200, format(result, ".15g") if result else "0"
    except ValueError:
        return 400, "Invalid query"


def send_response(client, status, message, close=False, head=False):
    reasons = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}
    body = message.encode("utf-8")
    headers = [
        f"HTTP/1.1 {status} {reasons[status]}",
        f"Date: {formatdate(usegmt=True)}",
        "Content-Type: text/plain; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close" if close else "Connection: keep-alive",
    ]
    if status == 405:
        headers.append("Allow: GET")
    client.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + (b"" if head else body))


def handle_client(client):
    with client:
        client.settimeout(IDLE_TIMEOUT)
        pending = b""
        try:
            while True:
                try:
                    request, pending = read_request(client, pending)
                except ValueError as error:
                    send_response(client, 400, str(error), close=True)
                    return
                if request is None:
                    return
                method, target, headers = request
                connection = ",".join(headers.get("connection", [])).lower().split(",")
                close = "close" in [value.strip() for value in connection]
                status, message = calculate(method, target, headers)
                send_response(client, status, message, close, method == "HEAD")
                if close:
                    return
        except OSError:
            return


def serve(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen()
        print(f"Listening on {host}:{port}", flush=True)
        while True:
            client, address = server.accept()
            threading.Thread(target=handle_client, args=(client,), daemon=True).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP/1.1 socket calculator")
    parser.add_argument("port", nargs="?", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    try:
        serve(args.host, args.port)
    except KeyboardInterrupt:
        pass
