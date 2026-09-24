# HTTP/1.1 Calculator

A calculator built with Python sockets and the standard library. Requires Python 3.8 or newer. No packages need to be installed.

## Run

```sh
python3 server.py
```

The server listens on `127.0.0.1:8080`. To choose another port:

```sh
python3 server.py 9000
```

In another terminal:

```sh
curl 'http://127.0.0.1:8080/add?a=2&b=3'
```

Stop the server with Ctrl+C.

## Requests

| Request | Status | Body |
| --- | --- | --- |
| `GET /add?a=2&b=3` | 200 | `5` |
| `GET /sub?a=10&b=4` | 200 | `6` |
| `GET /mul?a=6&b=7` | 200 | `42` |
| `GET /div?a=9&b=3` | 200 | `3` |
| `GET /div?a=1&b=0` | 400 | Error message |
| `GET /add?a=x&b=3` | 400 | Error message |
| `GET /pow?a=2&b=8` | 404 | Error message |
| `POST /add` | 405 | Error message |
| `GET /add` without Host | 400 | Error message |

Every request needs HTTP/1.1 and one nonempty `Host` header. Each supported operation needs one numeric `a` and one numeric `b`. Negative values, decimals, and scientific notation are accepted. Arithmetic uses floating-point numbers and displays up to 15 significant digits.

## Connection handling

The server keeps a byte buffer for each connection. It reads through `\r\n\r\n`, parses the headers, and consumes exactly `Content-Length` body bytes before answering. A body is consumed even when the method is rejected. Any remaining bytes stay in the buffer for the next request.

Every response has a `Content-Length` measured in bytes. Requests can arrive separately, in pieces, or together; responses are sent in request order. The connection stays open after validly framed requests, including arithmetic errors, missing Host, unknown paths, and unsupported methods.

`Connection: close` closes the socket after the response. A socket read times out after 30 seconds without incoming data, giving a person time to send the next request while releasing abandoned connections. Headers are limited to 16 KiB and bodies to 1 MiB.

Malformed framing gets a 400 response followed by connection closure because the next request boundary cannot be trusted. Chunked encoding is an optional extension in the assignment and is not implemented; requests with `Transfer-Encoding` are rejected and the connection is closed. Each client runs in its own thread.

## Design

The code uses small classes with separate responsibilities:

| File | Responsibility |
| --- | --- |
| `operations.py` | Arithmetic operations and result validation through `Calculator` |
| `calculator.py` | Request validation and mapping calculator results to responses |
| `http_protocol.py` | Request and response data, byte parsing, and response formatting |
| `connection.py` | The request loop and lifetime of one client connection |
| `server.py` | Accepting clients, starting threads, and assembling the application |

Each connection owns its request buffer. The server and connection classes receive a handler through their constructors. They depend on the one-method `RequestHandler` interface, so they can serve another application without changing the socket code.

The arithmetic classes implement the one-method `Operation` interface. To add an operation, implement `calculate(a, b)` and register an instance under a path in `build_handler()`. The calculator and request handler need no edits. Operations accept finite numbers and return a numeric result, or raise `ValueError` for invalid arithmetic. `Calculator` handles common validation and formatting.

| SOLID principle | Application |
| --- | --- |
| Single responsibility | Parsing, formatting, arithmetic, request handling, and connection management have separate classes. |
| Open/closed | New operations are added by implementing and registering an operation. |
| Liskov substitution | Every operation follows the same input, result, and error contract. |
| Interface segregation | `Operation` and `RequestHandler` each expose one method. |
| Dependency inversion | The calculator receives operations, and the server receives a request handler; implementations are selected at startup. |

## Check

```sh
python3 -m unittest -v
```

The tests start a local TCP listener on an available port. They check the six marking requests on one connection and then send a seventh request to prove that the socket remains usable. They also cover pipelining, split headers and bodies, body boundaries, missing Host, invalid numbers, connection closure, and malformed framing.

Design tests check operation substitution, registering a new operation, using another request handler, and running the command-line server with independent clients.

Message framing reference: [RFC 9112](https://www.rfc-editor.org/rfc/rfc9112.html).
