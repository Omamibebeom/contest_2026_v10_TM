"""
arm_link_test_tm.py —— 只測「手臂 ↔ 樹莓派」的通訊 (達明 TM Socket 版)

跟比賽主程式的差別
  不開相機、不讀 vision_profiles.json、不做座標轉換。
  使用同一支 arm_link.py (a/b 都走 Socket, 不接繼電器)。

手臂送什麼 → 這支怎麼處理 (句子以換行結尾; 回覆以 \\r\\n 結尾 = TMscript newline)
  GET       → $x,y      下面 FAKE_TARGETS 的下一個點 (單位 mm)
  SCAN      → $COUNT,n
  RESET     → $OK       並把取用順序歸零
  QUIT      → $BYE      並結束本程式
  A_REQ     → (a 通道) ready=1, 本測試程式會回假顏色 $A,1; 正式比賽由 ChannelA 投票後再送
  A_DONE    → (a 通道) ready=0
  其他      → $OK

執行
  python3 arm_link_test_tm.py
  (沒有手臂時, 另一台電腦可用:  nc 192.168.1.10 5000  然後打 GET 或 A_REQ)

賽前確認
  1. docs/tm-b-flow-v1.txt 的 Socket 宣告是 "192.168.1.10", 5000
  2. 樹莓派有線網卡 IP 設成 192.168.1.10/24
  3. 不需要接 GPIO / 繼電器

注意
  手臂 script 收到座標會真的移動, FAKE_TARGETS 請填安全可達的點。
"""
import time

import arm_link
from pi_gpio_controller import PiGPIOController

# ======= 測試用假座標 (單位 mm, 手臂座標系) =======
FAKE_TARGETS = [
    (300.0, 0.0),
    (300.0, 60.0),
    (300.0, -60.0),
]
# 測試用假顏色代碼 (對應預設 IO_CODES: red=1 blue=2 green=3)
FAKE_A_CODE = 1
# ================================================


def main():
    gpio = PiGPIOController()          # 已由 arm_link patch 成 Socket 版
    link = arm_link.ArmLink()
    link.open()
    print(f"[測試] 開始等手臂連線: {arm_link.HOST}:{arm_link.PORT}")
    print(f"[測試] 假座標共 {len(FAKE_TARGETS)} 個; A_REQ 會回 $A,{FAKE_A_CODE}")
    print("[測試] Ctrl+C 離開\n")

    i = 0
    total = 0
    a_replied = False                   # 這一輪 A_REQ 是否已回過假顏色
    running = True
    try:
        while running:
            ready = gpio.ready()        # 內部會泵 Socket; A_REQ/A_DONE 在這裡消化
            if ready == 1 and not a_replied:
                reply = arm_link.reply_a(FAKE_A_CODE)
                link.send(reply)
                print(f"[a] ready=1 → 回覆 {reply}")
                a_replied = True
            elif ready == 0:
                a_replied = False

            for cmd in link.poll():
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

                else:
                    reply = arm_link.REPLY_OK

                link.send(reply)
                print(f"[回覆] {reply}")

            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[測試] 手動結束")
    finally:
        link.close()
        gpio.cleanup()
        print(f"[測試] 已關閉, 這次共給了 {total} 組座標")


if __name__ == "__main__":
    main()
