import socket
import threading
import random
from network.protocol import send_message, receive_message, MESSAGE_TYPES


class GomokuServer:
    def __init__(self, host="0.0.0.0", port=9000):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = {}
        self.client_id = 0
        self.running = False
        self._lock = threading.Lock()
        self._ready_clients = set()
        self._pid_map = None

    def start(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(2)
            self.server_socket.settimeout(1.0)
            self.running = True
            self._ready_clients.clear()
            self._pid_map = None
            accept_thread = threading.Thread(target=self._accept_clients, daemon=True)
            accept_thread.start()
            print(f"服务器启动在 {self.host}:{self.port}")
            return True
        except OSError as e:
            print(f"服务器启动失败: {e}")
            if self.server_socket:
                try:
                    self.server_socket.close()
                except OSError:
                    pass
                self.server_socket = None
            return False

    def stop(self):
        self.running = False
        with self._lock:
            clients_snapshot = list(self.clients.values())
        for client_info in clients_snapshot:
            try:
                client_info["socket"].close()
            except OSError:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
        with self._lock:
            self.clients.clear()
        self._ready_clients.clear()
        print("服务器已停止")

    def _accept_clients(self):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                if len(self.clients) >= 2:
                    try:
                        client_sock.close()
                    except OSError:
                        pass
                    continue
                self.client_id += 1
                cid = self.client_id
                client_info = {
                    "socket": client_sock,
                    "addr": addr,
                    "id": cid,
                }
                self.clients[cid] = client_info
                should_start = len(self.clients) >= 2
                pid_map = None
                if should_start:
                    cids = sorted(self.clients.keys())
                    host_cid, guest_cid = cids[0], cids[1]
                    if random.random() < 0.5:
                        pid_map = {str(host_cid): 1, str(guest_cid): 2}
                    else:
                        pid_map = {str(host_cid): 2, str(guest_cid): 1}
                    self._pid_map = pid_map
                    self._ready_clients.clear()
            print(f"客户端 {cid} 已连接: {addr}")
            try:
                send_message(client_sock, MESSAGE_TYPES["WELCOME"], {
                    "client_id": cid
                })
            except (ConnectionError, OSError):
                self._remove_client(cid)
                continue
            if should_start and pid_map:
                self._broadcast(MESSAGE_TYPES["GAME_START"], {
                    "player_id_map": pid_map,
                })
            client_thread = threading.Thread(
                target=self._handle_client,
                args=(cid, client_sock),
                daemon=True
            )
            client_thread.start()

    def _handle_client(self, client_id, client_sock):
        file_obj = client_sock.makefile("rb")
        try:
            while self.running:
                msg = receive_message(file_obj)
                if msg is None:
                    break
                self._process_message(client_id, msg)
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                file_obj.close()
            except Exception:
                pass
            self._remove_client(client_id)

    def _process_message(self, client_id, msg):
        msg_type = msg.get("type")
        data = msg.get("data", {})
        if msg_type == MESSAGE_TYPES["LEAVE"]:
            self._remove_client(client_id)
        elif msg_type == MESSAGE_TYPES["RESET"]:
            pid_map = None
            with self._lock:
                if len(self.clients) >= 2:
                    cids = sorted(self.clients.keys())
                    if random.random() < 0.5:
                        pid_map = {str(cids[0]): 1, str(cids[1]): 2}
                    else:
                        pid_map = {str(cids[0]): 2, str(cids[1]): 1}
                    self._pid_map = pid_map
                    self._ready_clients.clear()
            if pid_map:
                self._broadcast(MESSAGE_TYPES["GAME_START"], {
                    "player_id_map": pid_map,
                })
        elif msg_type in [MESSAGE_TYPES["MOVE"], MESSAGE_TYPES["STATE_SYNC"], MESSAGE_TYPES["SETUP_SYNC"]]:
            if self._client_count() >= 2:
                self._broadcast_except(client_id, msg_type, data)

    def _client_count(self):
        with self._lock:
            return len(self.clients)

    def _broadcast_except(self, except_id, msg_type, data):
        with self._lock:
            targets = [(cid, info["socket"]) for cid, info in self.clients.items() if cid != except_id]
        for cid, sock in targets:
            try:
                send_message(sock, msg_type, data)
            except (ConnectionError, OSError):
                pass

    def _broadcast(self, msg_type, data):
        with self._lock:
            targets = [(cid, info["socket"]) for cid, info in self.clients.items()]
        for cid, sock in targets:
            try:
                send_message(sock, msg_type, data)
            except (ConnectionError, OSError):
                pass

    def _remove_client(self, client_id):
        with self._lock:
            if client_id in self.clients:
                client_info = self.clients.pop(client_id)
                try:
                    client_info["socket"].close()
                except OSError:
                    pass
                should_notify = len(self.clients) > 0
                self._ready_clients.discard(client_id)
            else:
                should_notify = False
        if should_notify:
            self._broadcast_except(client_id, MESSAGE_TYPES["LEAVE"], {
                "player_id": client_id
            })
