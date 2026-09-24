import re
from urllib.parse import parse_qs, urlsplit

from http_protocol import Request, Response
from operations import Calculator


NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


class CalculatorHandler:
    def __init__(self, calculator: Calculator):
        self._calculator = calculator

    def handle(self, request: Request) -> Response:
        hosts = request.headers.get("host", [])
        if len(hosts) != 1 or not hosts[0]:
            return Response(400, "Host is required")
        if request.method != "GET":
            return Response(405, "Method not allowed", {"Allow": "GET"})
        try:
            address = urlsplit(request.target)
            if address.netloc or address.fragment:
                return Response(400, "Invalid request target")
            if not self._calculator.supports(address.path):
                return Response(404, "Not found")
            values = parse_qs(address.query, keep_blank_values=True, max_num_fields=20)
        except ValueError:
            return Response(400, "Invalid query")
        if any(len(values.get(name, [])) != 1 for name in ("a", "b")):
            return Response(400, "Provide one a and one b")
        if any(not NUMBER.fullmatch(values[name][0]) for name in ("a", "b")):
            return Response(400, "Invalid number")
        try:
            a = float(values["a"][0])
            b = float(values["b"][0])
            return Response(200, self._calculator.calculate(address.path, a, b))
        except ValueError as error:
            return Response(400, str(error))
