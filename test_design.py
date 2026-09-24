import select
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from calculator import CalculatorHandler
from connection import ClientConnection
from http_protocol import Request, Response
from operations import Add, Calculator, Divide, Multiply, Operation, Subtract
from server import build_handler


class Remainder(Operation):
    def calculate(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a % b


class GreetingHandler:
    def handle(self, request: Request) -> Response:
        return Response(201, "Hello", {"X-Example": "greeting"})


class DesignTests(unittest.TestCase):
    def test_operations_share_the_same_contract(self):
        cases = [(Add(), "11"), (Subtract(), "5"), (Multiply(), "24"), (Divide(), "2.66666666666667")]
        for operation, expected in cases:
            with self.subTest(operation=type(operation).__name__):
                calculator = Calculator({"/operation": operation})
                self.assertEqual(calculator.calculate("/operation", 8, 3), expected)

    def test_new_operation_needs_only_registration(self):
        handler = CalculatorHandler(Calculator({"/remainder": Remainder()}))
        request = Request("GET", "/remainder?a=8&b=3", {"host": ["localhost"]})
        self.assertEqual(handler.handle(request), Response(200, "2"))
        request.target = "/remainder?a=8&b=0"
        self.assertEqual(handler.handle(request).status, 400)
        request.target = "/remainder?a=8&b=3"
        self.assertEqual(build_handler().handle(request).status, 404)

    def test_calculator_rejects_nonfinite_numbers(self):
        calculator = Calculator({"/mul": Multiply()})
        for a, b in ((float("inf"), 2), (2, float("nan")), (1e308, 1e308)):
            with self.subTest(a=a, b=b):
                with self.assertRaises(ValueError):
                    calculator.calculate("/mul", a, b)

    def test_division_by_zero_has_a_clear_error(self):
        calculator = Calculator({"/div": Divide()})
        with self.assertRaisesRegex(ValueError, "Cannot divide by zero"):
            calculator.calculate("/div", 1, 0)

    def test_connection_accepts_another_handler(self):
        client, peer = socket.socketpair()
        client.settimeout(2)
        connection = ClientConnection(peer, GreetingHandler())
        worker = threading.Thread(target=connection.run, daemon=True)
        worker.start()
        try:
            client.sendall(b"GET /hello HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
            data = b""
            while True:
                part = client.recv(4096)
                if not part:
                    break
                data += part
            header, body = data.split(b"\r\n\r\n", 1)
            self.assertTrue(header.startswith(b"HTTP/1.1 201 Created\r\n"))
            self.assertIn(b"X-Example: greeting", header)
            self.assertIn(b"Content-Length: 5", header)
            self.assertEqual(body, b"Hello")
        finally:
            client.close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_command_line_server_handles_multiple_clients(self):
        server_path = Path(__file__).with_name("server.py")
        process = subprocess.Popen(
            [sys.executable, str(server_path), "0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 5)[0], "Server did not start")
            line = process.stdout.readline().strip()
            self.assertTrue(line.startswith("Listening on 127.0.0.1:"), line)
            port = int(line.rsplit(":", 1)[1])
            with socket.create_connection(("127.0.0.1", port), timeout=2) as first:
                first.sendall(b"GET /add?a=2&b=3 HTTP/1.1\r\nHost:")
                with socket.create_connection(("127.0.0.1", port), timeout=2) as second:
                    second.sendall(b"GET /mul?a=6&b=7 HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                    with second.makefile("rb") as reader:
                        self.assertTrue(reader.read().endswith(b"\r\n\r\n42"))
                first.sendall(b" localhost\r\nConnection: close\r\n\r\n")
                with first.makefile("rb") as reader:
                    self.assertTrue(reader.read().endswith(b"\r\n\r\n5"))
        finally:
            process.terminate()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
