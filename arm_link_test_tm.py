"""
arm_link_test.py —— 只測「手臂 ↔ 樹莓派」的 TCP 通訊 (廠商測機用)

跟比賽主程式的差別:
  不開相機、不讀 vision_profiles.json、不碰 GPIO/繼電器、不做座標轉換。
  只留下 arm_link.py (和比賽用的是同一支), 所以這裡測通的連線、
  句子結尾、回覆格式, 比賽時完全一樣。

手臂送什麼 → 這支回什麼:
  GET      → $x,y    (下面 FAKE_TARGETS 的下一個點, 用完自動從頭再來)
  SCAN     → $COUNT,n
  RESET    → $OK     並把取用順序歸零
  QUIT     → $BYE    程式結束
  其他     → $OK

執行:
  python3 arm_link_test.py

賽前手臂端要先確認的兩件事 (tm-flow-v1.txt 裡寫死的):
  1. 樹莓派有線網卡 IP = 192.168.1.10
  2. 埠號 = 5000
"""
import arm_link

# ======= 測試用假座標 (單位 mm, 請改成這台手臂上安全、確定到得了的點) =======
# 這裡只驗通訊, 座標本身不需要正確; 但手臂會真的移動過去, 所以務必填安全的點。
FAKE_TARGETS = [
    (487.5, 0.0),
    (450.0, 60.0),
    (450.0, -60.0),
]
# ==========================================================================


def main():
    link = arm_link.ArmLink()
    link.open()
    print(f"[test] 開始等手臂連線: {arm_link.HOST}:{arm_link.PORT}")
    print(f"[test] 假座標共 {len(FAKE_TARGETS)} 個, 用完會從頭再來; Ctrl+C 離開")

    i = 0                                   # 下一次 GET 要給第幾個假座標
    running = True
    try:
        while running:
            for cmd in link.poll():         # 收這一圈手臂送來的句子
                print(f"[收到] {cmd}")

                if cmd == arm_link.CMD_GET:
                    x, y = FAKE_TARGETS[i % len(FAKE_TARGETS)]
                    i += 1
                    reply = arm_link.reply_target(x, y)

                elif cmd == arm_link.CMD_SCAN:
                    reply = arm_link.reply_count(len(FAKE_TARGETS))

                elif cmd == arm_link.CMD_RESET:
                    i = 0
                    reply = arm_link.REPLY_OK

                elif cmd == arm_link.CMD_QUIT:
                    reply = arm_link.REPLY_BYE
                    running = False

                else:                       # GRIP / RELEASE / 打錯字都回 OK
                    reply = arm_link.REPLY_OK

                link.send(reply)
                print(f"[回覆] {reply}")
    except KeyboardInterrupt:
        print("\n[test] 手動結束")
    finally:
        link.close()
        print("[test] 已關閉")


if __name__ == "__main__":
    main()
