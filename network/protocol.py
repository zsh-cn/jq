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