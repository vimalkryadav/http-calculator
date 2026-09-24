from typing import Protocol

from http_protocol import Request, RequestReader, Response, ResponseWriter


class RequestHandler(Protocol):
    def handle(self, request: Request) -> Response:
        ...


class ClientConnection:
    def __init__(self, client, handler: RequestHandler, timeout=30):
        self._client = client
        self._handler = handler
        self._timeout = timeout
        self._reader = RequestReader(client)
        self._writer = ResponseWriter(client)

    def run(self):
        with self._client:
            self._client.settimeout(self._timeout)
            try:
                while True:
                    try:
                        request = self._reader.read()
                    except ValueError as error:
                        self._writer.write(Response(400, str(error)), close=True)
                        return
                    if request is None:
                        return
                    response = self._handler.handle(request)
                    self._writer.write(response, request.close, request.method == "HEAD")
                    if request.close:
                        return
            except OSError:
                return
