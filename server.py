import argparse
import socket
import threading

from calculator import CalculatorHandler
from connection import ClientConnection, RequestHandler
from operations import Add, Calculator, Divide, Multiply, Subtract


class HttpServer:
    def __init__(self, host, port, handler: RequestHandler):
        self._host = host
        self._port = port
        self._handler = handler

    def serve(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self._host, self._port))
            server.listen()
            print(f"Listening on {self._host}:{server.getsockname()[1]}", flush=True)
            while True:
                client, address = server.accept()
                connection = ClientConnection(client, self._handler)
                threading.Thread(target=connection.run, daemon=True).start()


def build_handler():
    operations = {
        "/add": Add(),
        "/sub": Subtract(),
        "/mul": Multiply(),
        "/div": Divide(),
    }
    return CalculatorHandler(Calculator(operations))


def main():
    parser = argparse.ArgumentParser(description="HTTP/1.1 socket calculator")
    parser.add_argument("port", nargs="?", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    server = HttpServer(args.host, args.port, build_handler())
    try:
        server.serve()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
