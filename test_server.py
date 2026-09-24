import socket
import threading
import unittest

from server import handle_client


def request(path="/add?a=2&b=3", method="GET", headers="Host: localhost\r\n", body=b""):
    return f"{method} {path} HTTP/1.1\r\n{headers}\r\n".encode() + body


class CalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.listener = socket.socket()
        cls.listener.bind(("127.0.0.1", 0))
        cls.listener.listen()
        cls.listener.settimeout(0.1)
        cls.running = True
        cls.worker = threading.Thread(target=cls.accept_clients)
        cls.worker.start()

    @classmethod
    def accept_clients(cls):
        while cls.running:
            try:
                client, address = cls.listener.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_client, args=(client,), daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.running = False
        cls.worker.join()
        cls.listener.close()

    def setUp(self):
        self.client = socket.create_connection(self.listener.getsockname(), timeout=2)
        self.reader = self.client.makefile("rb")

    def tearDown(self):
        self.reader.close()
        self.client.close()

    def response(self, head=False):
        line = self.reader.readline().decode().strip()
        self.assertTrue(line.startswith("HTTP/1.1 "), line)
        status = int(line.split()[1])
        headers = {}
        while True:
            line = self.reader.readline()
            self.assertNotEqual(line, b"")
            if line == b"\r\n":
                break
            name, value = line.decode().split(":", 1)
            headers[name.lower()] = value.strip()
        length = int(headers["content-length"])
        body = b"" if head else self.reader.read(length)
        self.assertEqual(len(body), 0 if head else length)
        return status, body.decode(), headers

    def test_marking_sequence_on_one_connection(self):
        cases = [
            ("/add?a=2&b=3", "GET", 200, "5"),
            ("/sub?a=10&b=4", "GET", 200, "6"),
            ("/mul?a=6&b=7", "GET", 200, "42"),
            ("/div?a=1&b=0", "GET", 400, None),
            ("/pow?a=2&b=8", "GET", 404, None),
            ("/add", "POST", 405, None),
            ("/div?a=9&b=3", "GET", 200, "3"),
        ]
        for path, method, expected_status, expected_body in cases:
            with self.subTest(path=path, method=method):
                self.client.sendall(request(path, method))
                status, body, headers = self.response()
                self.assertEqual(status, expected_status)
                if expected_body is not None:
                    self.assertEqual(body, expected_body)
                self.assertEqual(headers["connection"], "keep-alive")
                if status == 405:
                    self.assertEqual(headers["allow"], "GET")

    def test_pipeline_with_body_containing_request_text(self):
        body = request("/mul?a=99&b=99")
        first = request("/add", "POST", f"Host: localhost\r\nContent-Length: {len(body)}\r\n", body)
        self.client.sendall(first + request() + request("/mul?a=6&b=7"))
        self.assertEqual(self.response()[0], 405)
        self.assertEqual(self.response()[:2], (200, "5"))
        self.assertEqual(self.response()[:2], (200, "42"))

    def test_all_six_requests_pipelined(self):
        paths = ["/add?a=2&b=3", "/sub?a=10&b=4", "/mul?a=6&b=7", "/div?a=1&b=0", "/pow?a=2&b=8"]
        self.client.sendall(b"".join(request(path) for path in paths) + request("/add", "POST"))
        self.assertEqual([self.response()[0] for _ in range(6)], [200, 200, 200, 400, 404, 405])
        self.client.sendall(request())
        self.assertEqual(self.response()[:2], (200, "5"))

    def test_split_body_waits_for_all_bytes(self):
        self.client.sendall(request(headers="Host: localhost\r\nContent-Length: 4\r\n", body=b"ab"))
        self.client.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            self.client.recv(1)
        self.client.settimeout(2)
        self.client.sendall(b"cd" + request("/sub?a=10&b=4"))
        self.assertEqual(self.response()[:2], (200, "5"))
        self.assertEqual(self.response()[:2], (200, "6"))

    def test_split_headers(self):
        self.client.sendall(b"GET /add?a=2&b=3 HTTP/1.1\r\nHo")
        self.client.sendall(b"st: localhost\r\n\r")
        self.client.sendall(b"\n")
        self.assertEqual(self.response()[:2], (200, "5"))

    def test_missing_or_duplicate_host_keeps_connection(self):
        for headers in ("", "Host: \r\n", "Host: localhost\r\nHost: localhost\r\n"):
            self.client.sendall(request(headers=headers) + request())
            self.assertEqual(self.response()[0], 400)
            self.assertEqual(self.response()[:2], (200, "5"))

    def test_invalid_numbers_and_parameters(self):
        for query in ("a=x&b=3", "a=2", "a=&b=3", "a=2&a=4&b=3", "a=nan&b=3", "a=inf&b=3", "a=1e309&b=3", "a=1_0&b=3"):
            with self.subTest(query=query):
                self.client.sendall(request("/add?" + query))
                self.assertEqual(self.response()[0], 400)
        self.client.sendall(request())
        self.assertEqual(self.response()[:2], (200, "5"))

    def test_decimal_and_negative_numbers(self):
        for path, expected in (("/add?a=0.1&b=0.2", "0.3"), ("/sub?a=-2&b=3", "-5"), ("/div?a=1&b=4", "0.25")):
            self.client.sendall(request(path))
            self.assertEqual(self.response()[:2], (200, expected))

    def test_connection_close(self):
        self.client.sendall(request(headers="hOsT: localhost\r\ncOnNeCtIoN: keep-alive, Close\r\n"))
        status, body, headers = self.response()
        self.assertEqual((status, body), (200, "5"))
        self.assertEqual(headers["connection"], "close")
        self.assertEqual(self.reader.read(1), b"")

    def test_invalid_length_closes_connection(self):
        self.client.sendall(request(headers="Host: localhost\r\nContent-Length: nope\r\n"))
        self.assertEqual(self.response()[0], 400)
        self.assertEqual(self.reader.read(1), b"")

    def test_transfer_encoding_is_rejected(self):
        self.client.sendall(request(headers="Host: localhost\r\nTransfer-Encoding: chunked\r\n"))
        self.assertEqual(self.response()[0], 400)
        self.assertEqual(self.reader.read(1), b"")

    def test_incomplete_body(self):
        self.client.sendall(request(headers="Host: localhost\r\nContent-Length: 10\r\n", body=b"abc"))
        self.client.shutdown(socket.SHUT_WR)
        self.assertEqual(self.response()[0], 400)
        self.assertEqual(self.reader.read(1), b"")

    def test_head_has_no_response_body(self):
        self.client.sendall(request(method="HEAD") + request())
        self.assertEqual(self.response(head=True)[0], 405)
        self.assertEqual(self.response()[:2], (200, "5"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
