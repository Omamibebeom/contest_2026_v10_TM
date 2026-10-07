"""
arm_link.py —— 和機械手臂講話的模組 (達明 TM 版; 換手臂只改這一支)

樹莓派當 TCP Server (0.0.0.0:5000), 手臂當 Client 連進來。
a、b 兩個通道共用這一條 Socket (正式比賽不需要 GPIO ↔ 繼電器配線)。

a 通道 (顏色; 對應原 GPIO ready / R1~R4 時序語意):
  主程式和 io_test.py 都透過 pi_gpio_controller.PiGPIOController 送顏色。
  本檔在 import 時把該類別的 ready() / send() / send_fail() / all_off() /
  cleanup() / __init__() 換成下面的 Socket 版本
  (main_contest.py 先 import arm_link 再建物件, 替換在建立前生效;
   io_test.py 是先建物件再載入 main_contest, 方法掛在類別上, 已建立的物件
   一樣會改用 Socket; 本模組載入時就會開 Server, 所以 io_test 也能收 A_REQ)。
  pi_gpio_controller.py 本身不用改, 學生作答的 IO_CODES / FAIL_CODE /
  HOLD_SEC / FAIL_HOLD_SEC 照常從那裡讀:
    1. 手臂到辨識位 → 送 "A_REQ"                    ← ready() 變 1
    2. 主程式投票 VOTE_SEC 秒 → send(color)
    3. send(): IO_CODES 的 (R2,R3,R4) → code = R2*4+R3*2+R4
              → 等 1 秒 → 回 "$A,<code>"
       失敗: send_fail() 回 "$A,<failcode>"
    4. 手臂讀完後送 "A_DONE" → ready() 變 0, 才能收下一件

b 通道 (座標):
  手臂送 "GET" → 我們回 "$B,x,y" (mm)
  沒有下一件 → "$B,-1,-1" (固定三段, 避免手臂 String_Split 爆 index)
  其他: SCAN / GRIP / RELEASE / RESET / QUIT

手臂端可貼 Script: docs/tm-a-flow-v1.txt (a)、docs/tm-b-flow-v1.txt (b)。
"""
import socket
import threading
import time

import pi_gpio_controller
from pi_gpio_controller import IO_CODES, FAIL_CODE

# ---------- 連線 ----------
HOST, PORT = "0.0.0.0", 5000     # 樹莓派在這個埠等手臂 ("0.0.0.0" = 任何網卡)
LINE_END = "\r\n"                # 回覆結尾 = TMscript newline

# ---------- 手臂會送來的指令字 ----------
CMD_GET = "GET"
CMD_SCAN = "SCAN"
CMD_GRIP = "GRIP"
CMD_RELEASE = "RELEASE"
CMD_RESET = "RESET"
CMD_QUIT = "QUIT"
CMD_A_REQ = "A_REQ"              # a 通道: 請開始辨識 (原 ready 拉高)
CMD_A_DONE = "A_DONE"            # a 通道: 已讀完顏色 (原 ready 放下)

# ---------- 我們回給手臂的格式 ----------
REPLY_OK = "$OK"
REPLY_BYE = "$BYE"
# 固定三段 "B,x,y", 沒物件時 x=y=-1, 手臂不要拆不到的 index
REPLY_NONE = "$B,-1,-1"


def reply_target(x, y):
    """b 通道座標, 例: $B,487.5,0.0 (讀完去掉 $ 後為 B,487.5,0.0 → bp[1], bp[2])。"""
    return f"$B,{x:.1f},{y:.1f}"


def reply_count(n):
    return f"$COUNT,{n}"


def reply_a(code):
    """a 通道顏色代碼, 例: $A,1 (red 預設)。不送 $A_OFF, 避免污染下一次 $ 讀取。"""
    return f"$A,{int(code)}"


# ==============================================================================
# 共用 Socket (a、b 與背景執行緒都走這一條, 用鎖排隊)
# ==============================================================================
_lock = threading.Lock()
_srv = None
_conn = None
_buf = b""
_ready_flag = 0                  # 1 = 手臂已送 A_REQ 且尚未 A_DONE
_b_cmds = []                     # poll() 要交給主程式的 b 通道指令


def _ensure_server():
    """開 TCP Server (只開一次)。io_test / main 都會間接到這裡。"""
    global _srv
    with _lock:
        if _srv is not None:
            return
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(1)
        srv.settimeout(0.05)
        _srv = srv
        print(f"[arm] Socket Server 聆聽 {HOST}:{PORT} (a/b 通道共用)")


def _drop_conn():
    global _conn, _buf, _ready_flag
    if _conn is not None:
        try:
            _conn.close()
        except OSError:
            pass
    _conn = None
    _buf = b""
    _ready_flag = 0


def _pump():
    """非阻塞: 接受連線、收句子, 更新 _ready_flag, 把 b 通道指令排進 _b_cmds。"""
    global _conn, _buf, _ready_flag
    _ensure_server()
    with _lock:
        if _conn is None:
            try:
                conn, addr = _srv.accept()
                conn.settimeout(0.05)
                _conn = conn
                _buf = b""
                print(f"[arm] 手臂連線: {addr}")
            except socket.timeout:
                return
            except OSError:
                return
        try:
            data = _conn.recv(1024)
        except socket.timeout:
            return
        except OSError:
            _drop_conn()
            return
        if not data:
            print("[arm] 手臂斷線")
            _drop_conn()
            return
        _buf += data
        while b"\n" in _buf:
            line, _buf = _buf.split(b"\n", 1)
            cmd = line.decode(errors="ignore").strip().upper()
            if not cmd:
                continue
            if cmd == CMD_A_REQ:
                _ready_flag = 1
                print("[io] 收到 A_REQ → ready=1")
            elif cmd == CMD_A_DONE:
                _ready_flag = 0
                print("[io] 收到 A_DONE → ready=0")
            else:
                _b_cmds.append(cmd)


def _send_raw(text):
    """回一句話給手臂; 沒連線就印警告。回傳 True = 有送出。"""
    with _lock:
        if _conn is None:
            print(f"[arm] 尚未連線, 無法送: {text}")
            return False
        try:
            _conn.sendall((text + LINE_END).encode())
            return True
        except OSError:
            _drop_conn()
            return False


def _close_all():
    global _srv
    with _lock:
        _drop_conn()
        if _srv is not None:
            try:
                _srv.close()
            except OSError:
                pass
            _srv = None


# ==============================================================================
# a 通道: 用 Socket 版本替換 PiGPIOController 的方法
# ==============================================================================
def _code_of(bits):
    """IO_CODES 的 (R2, R3, R4) → 數字: R2 最高位。例 (0,0,1)=1、(0,1,0)=2、(0,1,1)=3、(1,1,1)=7。"""
    r2, r3, r4 = bits
    return int(r2) * 4 + int(r3) * 2 + int(r4)


def _a_init(self):
    """不碰 GPIO。開 Socket Server (連不上手臂也沒關係, 之後 pump 再等)。"""
    print(f"[io] a 通道走 Socket: A_REQ/A_DONE → $A,code ({HOST}:{PORT})")
    _ensure_server()


def _a_ready(self):
    """讀「ready」: 手臂是否已送 A_REQ。順便幫 io_test 泵 Socket (主程式則靠 poll)。"""
    _pump()
    return _ready_flag


def _a_all_off(self):
    """Socket 版不需對手臂再送「全關」字串 (避免污染下一次 $ 讀取)。"""
    return


def _a_send(self, color):
    """辨識成功: 背景「等 1 秒 → 送一次 $A,code」。顏色不在表就當失敗。"""
    if color not in IO_CODES:
        _a_send_fail(self)
        return
    code = _code_of(IO_CODES[color])

    def run():
        print(f"[io] {color} → $A,{code}; 1 秒後送出")
        time.sleep(1)
        if not _send_raw(reply_a(code)):
            print("[io] 送 $A 失敗 (手臂沒連上?)")

    threading.Thread(target=run, daemon=True).start()


def _a_send_fail(self):
    """辨識失敗: 背景送一次 $A,failcode。"""
    code = _code_of(FAIL_CODE)

    def run():
        print(f"[io] 辨識失敗 → $A,{code}")
        if not _send_raw(reply_a(code)):
            print("[io] 送失敗碼失敗 (手臂沒連上?)")

    threading.Thread(target=run, daemon=True).start()


def _a_cleanup(self):
    """程式結束: 關 Server。"""
    _close_all()


pi_gpio_controller.PiGPIOController.__init__ = _a_init
pi_gpio_controller.PiGPIOController.ready = _a_ready
pi_gpio_controller.PiGPIOController.send = _a_send
pi_gpio_controller.PiGPIOController.send_fail = _a_send_fail
pi_gpio_controller.PiGPIOController.all_off = _a_all_off
pi_gpio_controller.PiGPIOController.cleanup = _a_cleanup

# 模組載入即開 Server, 讓 io_test 在「先建物件再 import main_contest」時也能收 A_REQ
_ensure_server()


# ==============================================================================
# b 通道: ArmLink (介面給 main_contest.py 用)
# ==============================================================================
class ArmLink:
    def open(self):
        """開始等手臂連線 (主程式在快照完成後才呼叫)。"""
        _ensure_server()
        print(f"[arm] === 階段二可連線 ({HOST}:{PORT}) ===")

    def poll(self):
        """收這一圈的 b 通道指令 (A_REQ/A_DONE 已在 _pump 內消化, 不會出現在這裡)。"""
        _pump()
        with _lock:
            cmds = list(_b_cmds)
            _b_cmds.clear()
        return cmds

    def send(self, text):
        """回一句話給手臂 (自動加結尾符號)。"""
        _send_raw(text)

    def close(self):
        _close_all()


# ---------- 直接執行: 請改用 arm_link_test_tm.py 做完整測機 ----------
if __name__ == "__main__":
    print(f"Socket Server 應已聆聽 {HOST}:{PORT} (a/b 共用)。")
    print("完整測機請執行:  python3 arm_link_test_tm.py")
    print("a 通道 (相機+投票) 請執行:  python3 io_test.py")
    print("正式比賽:  python3 main_contest.py --no-ui")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _close_all()
        print("\n已關閉 Server")
