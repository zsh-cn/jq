import socket
import threading
import queue
from network.protocol import send_message, receive_message, MESSAGE_TYPES


class GomokuClient:
    def __init__(self, host="127.0.0.1", port=9000):
        self.host = host
        self.port = port
        self.client_socket = None
        self.file_obj = None
        self.message_queue = queue.Queue()
        self.running = False
        self.player_id = 0
        self.is_connected = False
        self._send_lock = threading.Lock()

    def connect(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(3.0)
            self.client_socket.connect((self.host, self.port))
            self.client_socket.settimeout(None)
            self.file_obj = self.client_socket.makefile("rb")
            self.is_connected = True
            self.running = True
            receive_thread = threading.Thread(target=self._receive_messages, daemon=True)
            receive_thread.start()
            print(f"已连接到服务器 {self.host}:{self.port}")
            return True
        except (ConnectionError, OSError, socket.timeout) as e:
            print(f"连接失败: {e}")
            if self.client_socket:
                try:
                    self.client_socket.close()
                except OSError:
                    pass
                self.client_socket = None
            return False

    def disconnect(self):
        if self.is_connected:
            try:
                send_message(self.client_socket, MESSAGE_TYPES["LEAVE"], {
                    "player_id": self.player_id
                })
            except (ConnectionError, OSError):
                pass
        self.running = False
        self.is_connected = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except OSError:
                pass
        self.client_socket = None
        self.file_obj = None
        print("已断开连接")

    def _receive_messages(self):
        try:
            while self.running:
                msg = receive_message(self.file_obj)
                if msg is None:
                    break
                self.message_queue.put(msg)
        except (ConnectionError, OSError):
            pass
        finally:
            self.is_connected = False
            self.message_queue.put({"type": "disconnect"})

    def send_move(self, from_row, from_col, to_row, to_col):
        with self._send_lock:
            if self.is_connected and self.client_socket:
                try:
                    send_message(self.client_socket, MESSAGE_TYPES["MOVE"], {
                        "from_row": from_row,
                        "from_col": from_col,
                        "to_row": to_row,
                        "to_col": to_col,
                        "player_id": self.player_id
                    })
                except (ConnectionError, OSError):
                    self.is_connected = False

    def send_reset(self):
        with self._send_lock:
            if self.is_connected and self.client_socket:
                try:
                    send_message(self.client_socket, MESSAGE_TYPES["RESET"], {
                        "player_id": self.player_id
                    })
                except (ConnectionError, OSError):
                    self.is_connected = False

    def send_setup_sync(self, pieces_data):
        with self._send_lock:
            if self.is_connected and self.client_socket:
                try:
                    send_message(self.client_socket, MESSAGE_TYPES["SETUP_SYNC"], {
                        "pieces": pieces_data,
                        "player_id": self.player_id
                    })
                except (ConnectionError, OSError):
                    self.is_connected = False

    def send_state_sync(self, state_dict):
        with self._send_lock:
            if self.is_connected and self.client_socket:
                try:
                    send_message(self.client_socket, MESSAGE_TYPES["STATE_SYNC"], state_dict)
                except (ConnectionError, OSError):
                    self.is_connected = False

    def get_next_message(self):
        try:
            return self.message_queue.get_nowait()
        except queue.Empty:
            return None

    def get_all_messages(self):
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages
