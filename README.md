# 工科賽 2026 影像辨識定位 —— 工程師 README（v10）

給維護程式的人看。學生要看的操作說明都在各程式檔頂端的 docstring
（vision_tuner、io_test、affine_sample_tool、main_contest）。

---

## 1. 系統概觀

一台樹莓派＋一顆 C270，同時服務兩條互不相干的通道；前提是兩塊板上的物件**顏色完全不同**。
一句話：a 是「這是什麼顏色」，b 是「這個顏色在哪裡」。

| 通道 | 物件來源 | 觸發 | 做什麼 | 輸出 |
|---|---|---|---|---|
| a | 放置板（位置固定，題目指定夾哪件）；手臂夾起後舉到鏡頭與光電感測器前 | 手臂拉高 ready(GPIO26) | 3 秒投票辨識顏色（只看 IO_CODES 裡的顏色，取面積最大者） | 4 顆繼電器 3-bit 碼 |
| b | 隨機位置放置板（位置每次不同） | 手臂 TCP 送 `GET` | 開場拍一次快照，算好每件的手臂座標；之後只查表 | `$x,y,color` 回給手臂 |

（舊版文件的「a＝2025 辨識、b＝2026 定位」即這兩者。）

顏色分工不靠檔案、靠兩張作答表：`PICK_ORDER`（main_contest.py）裡的顏色歸 b，`IO_CODES`（pi_gpio_controller.py）裡的顏色歸 a。所有顏色都存在同一份 `vision_profiles.json`。

## 2. 檔案一覽（全部拉平，無子資料夾）

| 檔案 | 角色 | 作答區 |
|---|---|---|
| main_contest.py | 比賽主程式：快照、a 通道狀態機、主迴圈 | `PICK_ORDER` |
| arm_link.py | 手臂通訊：連線、收句、回句、指令字、回覆格式。**換手臂只改這支** | — |
| pi_gpio_controller.py | 繼電器輸出協定、ready 腳 | `IO_CODES` / `FAIL_CODE` / `HOLD_SEC` |
| affine_transform.py | 像素→手臂座標（最小平方仿射） | `PIXELS` / `ARMS` |
| color_detect.py | HSV 顏色偵測（a、b 共用） | — |
| camera_config.py | 開相機：自動從 0~5 找、讀到畫面才算、解析度警告、MJPG 開關 | — |
| vision_tuner.py | 工具：調 HSV → vision_profiles.json | — |
| affine_sample_tool.py | 工具：取像素↔手臂點位 | — |
| io_test.py | 工具：顏色→IO 測試 | — |
| vision_profiles.json | 顏色設定（附的是範例值，現場必須重調） | — |
| docs/tm-flow-v1.txt | 大會 script（手臂端，不需修改） | — |
| docs/a_channel_flow.txt | a 通道手臂端 flow 與 DI 解碼表 | — |

## 3. 資料流

```
vision_tuner.py ──存──► vision_profiles.json ──讀──► main_contest.py / io_test.py / affine_sample_tool.py
affine_sample_tool.py ──印出──► 手抄進 affine_transform.py 的 PIXELS/ARMS ──import──► main_contest.py
pi_gpio_controller.IO_CODES ──import──► main_contest.py (a 通道只看這些顏色) / io_test.py
```

主迴圈（main_contest.main）每圈：`cap.read()` → `a.step(frame)` → `link.poll()` 逐句 `b.handle()` 回覆 → 有 UI 才畫面。沒有多執行緒；只有繼電器保持時序（7～10 秒）開背景 thread，不卡迴圈。

## 4. 通訊協定（arm_link.py）

達明 TM：手臂為 client，連樹莓派 `0.0.0.0:5000`；句子以 `\n` 結尾；回覆以 `\r\n` 結尾（＝TMscript 的 `newline`）。

| 手臂送 | 回覆 |
|---|---|
| GET | `$x,y,color`（PICK_ORDER 下一個顏色、快照裡由左到右第一件未給過的）；沒有 → `$NONE` |
| SCAN | `$COUNT,n`（只回件數，刻意不重拍） |
| RESET | `$OK`，取用順序歸零 |
| QUIT | `$BYE`，程式結束 |
| GRIP / RELEASE / 其他 | `$OK` |

script 端：`socket_open` → `socket_sendline("GET")` → `socket_read_string(..., "$", newline, 1, 3000)` 只等 **3 秒**；`Socket` 宣告的第三個參數 5000 ms 是讀寫逾時。`String_ToFloat` 吃到空字串會回 0（手冊），所以「連上但沒回覆」在手臂端看起來是**座標 0、不報錯**。

**埠在快照完成後才開**（`link.open()` 在 `take_snapshot()` 之後）：準備期間手臂 `socket_open` 直接得到 False，不會再出現「連上卻等不到回覆」。

換手臂：改 `arm_link.py` 的連線方式（誰連誰、埠）、`LINE_END`、`CMD_*` 指令字、`reply_*` 格式。主程式不用動。

## 5. IO 訊號協定（pi_gpio_controller.py）

- 腳位 BCM：R1 R2 R3 R4 = 17 27 22 23；ready = 26（`PUD_DOWN`，浮接讀 0）；繼電器低電位吸合（`INVERSE_LOGIC=True`）。
- 成功：先擺 R2 R3 R4 → 1 秒 → R1 拉高 → 保持 `HOLD_SEC`(7) 秒 → 全關。R1 是「資料已備妥」旗子。
- 失敗：R1 不拉高，R2 R3 R4 = `FAIL_CODE`(1,1,1) 保持 `FAIL_HOLD_SEC`(10) 秒；手臂端是「等 DI0 逾時後再讀 DI1~DI3 = 1 1 1」，所以保持時間必須比手臂的逾時長。
- 非樹莓派自動模擬（只印字）。新版 Raspberry Pi OS 要用 `rpi-lgpio`（requirements_pi.txt），裝到原版 RPi.GPIO 會在 `GPIO.setmode` 丟 RuntimeError。

## 6. 網路設定（達明）

- 樹莓派**有線網卡**固定 IP `192.168.1.10/24`（script 寫死連這個位址）；手臂 `192.168.1.20`。直連一條 Cat5e 即可，不需路由器。
- Wi-Fi 可保留給上網／SSH，不同網段不衝突。
- 設定：桌面網路圖示 → Edit Connections → Wired → IPv4 Manual，或
  `sudo nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.1.10/24 && sudo nmcli con up "Wired connection 1"`
- 測試而不動手臂：`ss -ltnp | grep 5000` 看程式有沒有在聽；筆電改 .30 後用 `nc 192.168.1.10 5000` 打 `GET`。

## 7. 樹莓派安裝與執行

```bash
python3 --version
pip install -r requirements_pi.txt --break-system-packages
cd ~/Desktop/contest2026_v10
python3 vision_tuner.py            # 每個顏色調好按 s 存
python3 affine_sample_tool.py      # 取點位 → 抄進 affine_transform.py → python3 affine_transform.py 驗算
python3 io_test.py                 # 顏色→IO 接線
python3 main_contest.py --no-ui    # 比賽; 練習加 --practice
```
一律在終端機執行、先 `cd` 進資料夾（相對路徑找 vision_profiles.json）。Geany 只拿來改檔案。

## 8. 版本歷史

**v10（2026-09）重構**
- 移除形狀辨識：刪除 vision_processing/（detector、config、feature_validator、confidence_scorer、color_config.json）。a 通道改為「IO_CODES 顏色中面積最大者」+ 3 秒投票（贏家 +1，不再減其他票）。
- 單一顏色檔：a、b 共用 vision_profiles.json；vision_tuner 只剩 `s` 存檔、`n` 切換。
- 新增 arm_link.py：TCP、句子框架、指令字、回覆格式集中；主程式的 ContestServer 類別移除，迴圈直接寫在 main()。
- pi_gpio_controller 重寫：作答區 IO_CODES / FAIL_CODE / HOLD_SEC；`send(color)`、`send_fail()` 取代 trigger_action_A~F 與三個舊時序；腳位改為常數。
- a_channel_test.py → io_test.py（診斷關卡、重疊檢查、LED 測試全部移除）。
- 移除 `GET,<顏色>` 點名指令與舊格式相容碼。
- board_config.py → camera_config.py：自動搜尋 0~5 號、真的讀到畫面才算成功、解析度不符只警告、`USE_MJPG` 開關（預設關）、`FORCE_INDEX` 指定編號；`open_camera()` 找不到回傳 None。移除 pygrabber 依賴。
- 資料夾拉平；docs/ 放手臂端資料。
- 註解原則：程式內只留操作說明；歷史與除錯集中在本 README。

**v9** affine_transform 精簡（PARAMS 載入時計算、無 get_mapper/matrix_inverse/檢查）；main_contest 直接 `from affine_transform import pixel_to_arm`；affine_sample_tool 移除 f 鍵；主程式 5000 埠改快照後才開；新增 `--practice`。
**v8** a 通道支援色相跨接縫（`_hsv_mask`）；detector 改先 BGR 模糊再轉 HSV（先轉 HSV 再模糊會把紅色接縫兩側平均成綠色，實測紅方形 19600 像素毀掉 17964）；新增辨識失敗碼 0011；vision_tuner 加 a 鍵。
**v7 / v6** 整合 2025 a 通道與 2026 b 通道為單一主程式；b 改為開場快照鎖定；統一 board_config 開相機；WAIT_RELEASE 狀態避免重複觸發。

## 9. 2025 → 2026 對照

| 2025 | 2026 |
|---|---|
| ARMCtrl_OpenCV/utils/vision_processing、arm_controller 子資料夾 | 全部拉平到根目錄 |
| 顏色×形狀 → A~F 標籤 → trigger_action_A~F | 顏色 → IO_CODES 查表 → send(color) |
| color_config.json（Red/Blue/Green，[[h,s,v],[h,s,v]]） | vision_profiles.json（DetectConfig，任意顏色名） |
| 每幀辨識、顯示標註畫面 | 3 秒投票；標註畫面只在 UI 模式 |
| 無失敗碼 | FAIL_CODE 0011 保持 10 秒 |
| 通訊寫在主程式 | arm_link.py |

## 10. 故障排除（依實際發生過的案例）

- **手臂連上但座標顯示 0、不報錯**：按手臂時程式還沒到「階段二」；v10 已改成快照後才開埠，此情況會變成手臂端 socket_open=False。啟動後等終端印出「階段二」再按。
- **第一次成功、之後都失敗**：PICK_ORDER 用完回 `$NONE`。練習用 `--practice` 或 UI 按 c；正式比賽 PICK_ORDER 要寫滿實際件數。
- **啟動就 `LinAlgError: Singular matrix`**：affine_transform 點位共線或少於 3 點；`ValueError: matmul ... mismatch`：PIXELS 與 ARMS 點數不同。重取或重抄，`python3 affine_transform.py` 驗算。
- **快照 0 件或少件**：手臂停在畫面內、燈光變了、顏色名和 PICK_ORDER 不一致（啟動時會印警告）。
- **手臂完全連不上**：樹莓派有線網卡不是 192.168.1.10（常見：只有 Wi-Fi 拿到 DHCP 位址）；用 `ip -4 addr show eth0` 確認。IP 重複（筆電還留著 .10）會「有時通有時不通」。
- **a 通道無故觸發**：ready 腳接線鬆脫；程式已設 PUD_DOWN，浮接應讀 0，仍觸發就量電位。
- **a 通道看到 b 的物件**：不會——a 只看 IO_CODES 裡的顏色。反之 b 快照會把 a 顏色也存進去，但 PICK_ORDER 不點名就不會給。
- **紅色抓不完整**：色相跨接縫，tuner 把 H min 拉得比 H max 大（畫面顯示 HUE-WRAP）。
- **開不了相機**：camera_config 會印「試過 [0..5] 都讀不到畫面」→ `ls /dev/video*` 看有沒有裝置、`fuser /dev/video0` 看有沒有被佔用。C270 的 video1 是附屬節點讀不到畫面，程式會自動略過。兩台相機時用 `FORCE_INDEX` 指定。
- **啟動印「不是 1280x720」**：相機不支援或被別的程式改了解析度；此時 affine 點位全部失效，先解決再比賽。
- **GPIO RuntimeError**：裝了原版 RPi.GPIO；改裝 rpi-lgpio。

## 11. 已知限制

- a 通道只認顏色，同色兩種物件無法區分（設計前提是顏色皆不同）。
- 快照只拍一次；比賽中物件被移動不會更新（可用 UI 的 r 或 TCP 無法重拍——刻意如此，避免拍到手臂）。
- 相機一動，affine 點位全部作廢。
