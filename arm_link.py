"""
arm_link.py —— 和機械手臂講話的模組 (換手臂只改這一支)

現在的手臂 (達明 TM, 大會 script tm-flow-v1) 是這樣講話的:
  手臂當客戶端, 連到樹莓派的 5000 埠
  手臂送 "GET" + 換行        → 我們回 "$x,y" + 換行 (手臂座標, 單位 mm)
  沒有可以給的               → 回 "$NONE"
  其他句子: SCAN / GRIP / RELEASE / RESET / QUIT (主程式決定回什麼)

換別的手臂通常要改三個地方: 連線方式 (誰連誰、埠號)、句子的結尾符號、回覆的格式。
"""
import socket

HOST, PORT = "0.0.0.0", 5000     # 樹莓派在這個埠等手臂來連 ("0.0.0.0" = 任何網路卡都可)
LINE_END = "\r\n"                # 回覆的結尾符號 (達明 script 的 newline)

# ---------- 手臂會送來的指令字 ----------
CMD_GET = "GET"
CMD_SCAN = "SCAN"
CMD_GRIP = "GRIP"
CMD_RELEASE = "RELEASE"
CMD_RESET = "RESET"
CMD_QUIT = "QUIT"

# ---------- 我們回給手臂的格式 ----------
REPLY_OK = "$OK"
REPLY_BYE = "$BYE"
REPLY_NONE = "$NONE"


def reply_target(x, y):
    """一件物件的手臂座標, 例: $487.5,0.0
    不回顏色: 顏色只是樹莓派用來找中心點的依據, 手臂照 PICK_ORDER 的順序就知道第幾件是什麼。"""
    return f"${x:.1f},{y:.1f}"


def reply_count(n):
    return f"$COUNT,{n}"


class ArmLink:
    def __init__(self):
        self.srv = None
        self.conn = None
        self.buf = b""

    def open(self):
        """開始等手臂連線 (主程式在快照完成後才呼叫)。"""
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((HOST, PORT))
        self.srv.listen(1)
        self.srv.settimeout(0.05)       # 每圈最多等 0.05 秒, 不卡住主程式

    def poll(self):
        """收這一圈的指令, 回傳清單 (可能是空的)。每句話轉大寫、去頭尾空白。"""
        if self.conn is None:
            try:
                self.conn, addr = self.srv.accept()
                self.conn.settimeout(0.05)
                self.buf = b""
                print(f"[arm] 手臂連線: {addr}")
            except socket.timeout:
                return []
        try:
            data = self.conn.recv(1024)
        except socket.timeout:
            return []
        except OSError:
            self.conn = None
            return []
        if not data:                    # 手臂關了連線, 等下一次
            self.conn.close()
            self.conn = None
            return []
        self.buf += data
        cmds = []
        while b"\n" in self.buf:        # 一次可能收到半句或一句半, 看到換行才算一句
            line, self.buf = self.buf.split(b"\n", 1)
            cmd = line.decode(errors="ignore").strip().upper()
            if cmd:
                cmds.append(cmd)
        return cmds

    def send(self, text):
        """回一句話給手臂 (自動加結尾符號)。"""
        try:
            self.conn.sendall((text + LINE_END).encode())
        except OSError:
            self.conn = None

    def close(self):
        if self.conn:
            self.conn.close()
        if self.srv:
            self.srv.close()
