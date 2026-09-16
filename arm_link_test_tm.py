"""
arm_link_test_tm.py —— 只測「手臂 ↔ 樹莓派」的通訊 (達明 TM 版, 廠商測機用)

跟比賽主程式的差別
  不開相機、不讀 vision_profiles.json、不碰 GPIO、不做座標轉換。
  只留下 arm_link.py (和比賽用的是同一支), 所以這裡測通的連線、句子結尾、
  回覆格式, 比賽時完全一樣。

手臂送什麼 → 這支回什麼 (手臂送的句子以換行結尾; 回覆以 \r\n 結尾 = TMscript 的 newline)
  GET       → $x,y      下面 FAKE_TARGETS 的下一個點, 用完自動從頭再來 (單位 mm)
  SCAN      → $COUNT,n
  RESET     → $OK       並把取用順序歸零
  QUIT      → $BYE      並結束本程式
  其他      → $OK

執行
  python3 arm_link_test_tm.py
  (沒有手臂時, 另一台電腦可用  nc 192.168.1.10 5000  打 GET 模擬)

賽前手臂端要先確認的兩件事
  1. docs/tm-flow-v1.txt 的 Socket 宣告是 "192.168.1.10", 5000
  2. 樹莓派有線網卡 IP 設成 192.168.1.10/24

注意
  手臂 script 收到座標會真的移動, FAKE_TARGETS 請填這台手臂上安全可達的點。
"""
import time

import arm_link

# ======= 測試用假座標 (單位 mm, 手臂座標系) =======
# 這裡只驗通訊, 座標本身不需要準; 但手臂會真的移動過去, 務必填安全的點。
FAKE_TARGETS = [
    (300.0, 0.0),
    (300.0, 60.0),
    (300.0, -60.0),
]
# ================================================


def main():
    link = arm_link.ArmLink()
    link.open()
    print(f"[測試] 開始等手臂連線: {arm_link.HOST}:{arm_link.PORT}")
    print(f"[測試] 假座標共 {len(FAKE_TARGETS)} 個, 用完會從頭再來")
    print("[測試] Ctrl+C 離開\n")

    i = 0                                   # 下一次 GET 要給第幾個假座標 (RESET 會歸零)
    total = 0                               # 這次總共給了幾組 (只增不減, 結尾統計用)
    running = True
    try:
        while running:
            for cmd in link.poll():         # 收這一圈手臂送來的句子 (arm_link 已去掉換行、轉大寫)
                print(f"[收到] {cmd}")

                if cmd == arm_link.CMD_GET:
                    x, y = FAKE_TARGETS[i % len(FAKE_TARGETS)]
                    i += 1
                    total += 1
                    reply = arm_link.reply_target(x, y)
                    print(f"       第 {total} 次 GET, 要給 X={x} Y={y} mm")

                elif cmd == arm_link.CMD_SCAN:
                    reply = arm_link.reply_count(len(FAKE_TARGETS))

                elif cmd == arm_link.CMD_RESET:
                    i = 0
                    reply = arm_link.REPLY_OK

                elif cmd == arm_link.CMD_QUIT:
                    reply = arm_link.REPLY_BYE
                    running = False

                else:                       # GRIP / RELEASE / 打錯字都回 ack
                    reply = arm_link.REPLY_OK

                link.send(reply)
                print(f"[回覆] {reply}")

            time.sleep(0.01)                # 沒事做時稍微讓一下 CPU
    except KeyboardInterrupt:
        print("\n[測試] 手動結束")
    finally:
        link.close()
        print(f"[測試] 已關閉, 這次共給了 {total} 組座標")


if __name__ == "__main__":
    main()
