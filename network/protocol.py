import json


MESSAGE_TYPES = {
    "LEAVE": "leave",
    "MOVE": "move",
    "RESET": "reset",
    "STATE_SYNC": "state_sync",
    "SETUP_SYNC": "setup_sync",
    "GAME_START": "game_start",
    "WELCOME": "welcome",
}


def encode_message(msg_type, data=None):
    message = {"type": msg_type}
    if data:
        message["data"] = data
    return json.dumps(message) + "\n"


def decode_message(raw_message):
    try:
        return json.loads(raw_message)
    except json.JSONDecodeError:
        return None


def send_message(sock, msg_type, data=None):
    message = encode_message(msg_type, data)
    try:
        sock.sendall(message.encode("utf-8"))
        return True
    except (ConnectionError, OSError):
        return False


def receive_message(file_obj):
    try:
        line = file_obj.readline()
        if not line:
            return None
        msg = decode_message(line.decode("utf-8").strip())
        if msg is None:
            return {"type": "_malformed"}
        return msg
    except (ConnectionError, OSError, UnicodeDecodeError):
        return None


class SocketLineReader:
    def __init__(self, sock, bufsize=65536):
        self._sock = sock
        self._bufsize = bufsize
        self._buffer = b""

    def readline(self):
        while b"\n" not in self._buffer:
            try:
                chunk = self._sock.recv(self._bufsize)
            except (ConnectionError, OSError):
                chunk = b""
            if not chunk:
                remaining = self._buffer
                self._buffer = b""
                if remaining:
                    return remaining
                return b""
            self._buffer += chunk
        line, self._buffer = self._buffer.split(b"\n", 1)
        return line + b"\n"

    def close(self):
        self._buffer = b""


def receive_message_from_socket(reader):
    try:
        line = reader.readline()
        if not line:
            return None
        msg = decode_message(line.decode("utf-8").strip())
        if msg is None:
            return {"type": "_malformed"}
        return msg
    except (ConnectionError, OSError, UnicodeDecodeError):
        return None