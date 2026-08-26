"""A DevTools client with no dependencies outside the standard library.

Driving the browser needs two things: the HTTP endpoint that lists targets,
and a WebSocket to talk to one. Python ships the first and not the second, so
the framing is implemented here rather than pulling in a package. It is about
eighty lines, and a build tool that has to keep working for years is better
off without a dependency that can rot.

Only what CDP needs is supported: text frames, server pings and close. No
extensions, no compression, no binary payloads.
"""

import base64
import json
import os
import socket
import struct
import time
import urllib.request
from urllib.parse import urlparse

OP_CONTINUATION, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA


class WebSocket:
    def __init__(self, url: str, timeout: float = 30.0):
        parts = urlparse(url)
        port = parts.port or 80
        self.sock = socket.create_connection((parts.hostname, port), timeout)
        self.sock.settimeout(timeout)
        self._handshake(parts.hostname, port, parts.path or "/")

    def _handshake(self, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        # The response headers end at the blank line; read no further, because
        # anything after it is already frame data.
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("closed during handshake")
            buf += chunk
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"upgrade refused: {buf.splitlines()[:1]}")

    def _read_exact(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("closed mid-frame")
            out += chunk
        return out

    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x80 | OP_TEXT])
        n = len(payload)
        # The client always masks; a server must drop unmasked frames.
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv(self) -> str:
        message, opcode = b"", None
        while True:
            b1, b2 = self._read_exact(2)
            fin, op = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read_exact(8))[0]
            # Server frames are never masked, so the payload follows directly.
            data = self._read_exact(n)

            if op == OP_PING:
                self.sock.sendall(bytes([0x80 | OP_PONG, 0x80 | len(data)])
                                  + b"\x00\x00\x00\x00" + data)
                continue
            if op == OP_CLOSE:
                raise ConnectionError("server closed the connection")
            if op == OP_PONG:
                continue

            if op != OP_CONTINUATION:
                opcode = op
            message += data
            if fin:
                if opcode == OP_BINARY:
                    message, opcode = b"", None
                    continue
                return message.decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.sendall(bytes([0x80 | OP_CLOSE, 0x80]) + b"\x00\x00\x00\x00")
        except OSError:
            pass
        self.sock.close()


class Target:
    """One CDP connection, addressed by sequential message id."""

    def __init__(self, ws_url: str, timeout: float = 30.0):
        self.ws = WebSocket(ws_url, timeout)
        self.next_id = 0

    def call(self, method: str, **params):
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        # Events share the socket with replies, so read past anything that is
        # not the reply being waited on.
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != mid:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error'].get('message')}")
            return message.get("result", {})

    def evaluate(self, expression: str):
        """Run JavaScript in the page and return the value, or None."""
        result = self.call(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
        )
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise RuntimeError(details.get("text", "evaluation failed"))
        return result.get("result", {}).get("value")

    def close(self) -> None:
        self.ws.close()


def targets(port: int) -> list:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        return json.loads(r.read().decode())


def wait_for_page(port: int, deadline: float, poll: float = 0.02):
    """Return the first page target once DevTools is serving, or None."""
    while time.monotonic() < deadline:
        try:
            for target in targets(port):
                if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
                    return target
        except OSError:
            pass  # DevTools has not bound its port yet.
        time.sleep(poll)
    return None
