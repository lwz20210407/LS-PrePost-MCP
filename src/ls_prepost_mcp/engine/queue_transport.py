"""Authenticated loopback notification for the noninteractive session bridge."""

import json
import socket


class QueueTransport:
    def __init__(self, ready, timeout):
        self.ready = ready
        self.timeout = timeout

    def preflight(self):
        if type(self.ready.get("port")) is not int or not 0 < self.ready["port"] < 65536:
            raise ValueError("Invalid session listener port")
        if not isinstance(self.ready.get("token"), str) or len(self.ready["token"]) != 64:
            raise ValueError("Invalid session listener identity")

    def submit(self, request_id):
        self.preflight()
        message = dict(token=self.ready["token"], session_id=self.ready["session_id"], request_id=request_id)
        with socket.create_connection(("127.0.0.1", self.ready["port"]), timeout=self.timeout) as connection:
            connection.sendall(json.dumps(message).encode("utf8") + b"\n")
        # No retry: a send error does not prove the job was not queued.
