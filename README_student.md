# 學生手冊 —— 比賽要改什麼、要做什麼（達明 TM Socket 版）

所有指令都在終端機打（樹莓派：左上角黑色方框圖示或 Ctrl+Alt+T），先進到資料夾：
```
cd ~/Desktop/contest_2026_v10_TM
```

> **本廠商包：a、b 通道都走 Ethernet / Socket。正式比賽不需要樹莓派 GPIO ↔ 繼電器配線。**  
> 網路線與 IP 設定見大會《2026 工科賽達明通訊設定》（Pi `192.168.1.10`，手臂 `192.168.1.20`，埠 `5000`）。

## 零、先弄清楚兩個通道

一句話：**a 是「這是什麼顏色」，b 是「這個顏色在哪裡」。**

| 通道 | 物件在哪塊板 | 手臂做什麼 | 程式做什麼 | 程式回什麼 |
|---|---|---|---|---|
| a | 放置板（位置固定） | 夾起物件舉到鏡頭前，送 `A_REQ`，讀 `$A,code`，再送 `A_DONE` | 辨識顏色 | `$A,<code>`（由 `IO_CODES` 編成數字） |
| b | 隨機位置放置板 | 送 `GET`，照回覆去夾 | 開場快照算座標 | `$B,x,y`（照 `PICK_ORDER`，不回顏色） |

**手臂可貼上的 Script：**

- 讀顏色（a）：`docs/tm-a-flow-v1.txt` → 回覆 `$A,1`
- 要座標（b）：`docs/tm-b-flow-v1.txt` → 回覆 `$B,487.5,0.0`；沒有下一件為 `$B,-1,-1`
- `docs/a_channel_flow.txt` 只是說明，不要整份貼進 TMflow

### 為什麼 `pi_gpio_controller.py` 還有繼電器程式？

那是四家共用的母版檔，**不要改檔案裡的 GPIO 腳位邏輯**。達明的 `arm_link.py` 在載入時會把 `ready()` / `send()` 等方法換成 Socket 版：

- 原本 `ready()` → 讀 GPIO26  
- 現在 `ready()` → 是否收到手臂的 `A_REQ`  
- 原本 `send()` → 打 R1～R4 繼電器  
- 現在 `send()` → 送 `$A,<code>`（`code = R2*4 + R3*2 + R4`）

學生仍只填 `IO_CODES` 那張表；手臂端解的是 `$A,1` / `$A,2` … 而不是 DI 線。細節見 `docs/a_channel_flow.txt`。

預設代碼：`red=1`，`blue=2`，`green=3`，失敗=`7`。

---

## 一、你要改的四個地方（其他檔案都不要動）

| # | 檔案 | 位置 | 填什麼 | 怎麼確認填對 |
|---|---|---|---|---|
| 1 | affine_transform.py | 作答區 1：`PIXELS` / `ARMS` | 取樣工具印出的點位，至少 3 點、建議 5 點，不可排成一直線 | `python3 affine_transform.py` 印出六個參數 |
| 2 | affine_transform.py | 作答區 2：`fit()` 裡的計算（比賽會挖空） | 照《座標轉換教學》的公式手寫 | 同上；再拿取樣點代進 `pixel_to_arm` |
| 3 | main_contest.py | 頂端 `PICK_ORDER` | 隨機板夾取順序，顏色名小寫；同色兩件寫兩次 | 啟動主程式時快照沒有「注意」 |
| 4 | pi_gpio_controller.py | 頂端 `IO_CODES` / `FAIL_CODE` | 顏色 → (R2,R3,R4)，會編成 `$A,code` | `io_test.py` 按數字鍵，手臂端讀到對的 `$A,code` |

顏色名鐵則：**vision_profiles.json、PICK_ORDER、IO_CODES 三處一模一樣、全部小寫**。

作答區 1 還沒填完時，`python3 affine_transform.py` 可能噴 `LinAlgError: Singular matrix`——代表還沒作答，正常。

---

## 二、賽前準備（照順序做）

**第 1 步：調顏色**
```
python3 vision_tuner.py
```
物件放到鏡頭下，調 H/S/V 直到 mask 只剩物件是白的。按 `s` 存顏色名（小寫）。`n` 叫回修改，`q` 離開。

**第 2 步：取點位**
```
python3 affine_sample_tool.py
```
放物件 → 十字 → `SPACE` 鎖定 → Jog 夾爪到正上方 → `c` 輸入手臂 X,Y → 多點（四角＋中間）。`p` 印清單，抄進作答區 1。

**第 3 步：寫轉換公式，驗算**
```
python3 affine_transform.py
```
印出 `X = …`、`Y = …` 即成功。

**第 4 步：填 `PICK_ORDER` 和 `IO_CODES`**

**第 5 步：測 a 通道 Socket（原「測 IO 接線」）**
```
python3 io_test.py
```
先讓手臂（或另一台電腦）連上 `192.168.1.10:5000`。  
按 `1`～`9` 送顏色 → 對端應收到 `$A,code`；`f` 失敗碼；`0` 送 `$A_OFF`；`r` 送鏡頭看到的顏色。  
手臂送 `A_REQ` 時畫面 `ready=` 會變 1，送 `A_DONE` 後變 0。

**第 6 步：只測通訊（選用）**
```
python3 arm_link_test_tm.py
```
不開相機。`GET` → 假座標；`A_REQ` → 假 `$A,1`。假座標手臂會真的過去，填安全點。

**第 7 步：練習跑一次**
```
python3 main_contest.py --practice
```
有畫面。熱鍵：`r` 重拍快照、`c` 順序歸零、`q` 離開。

---

## 三、比賽當天（照順序做）

1. 手臂停在鏡頭畫面**外面**。
2. 跑正式指令：
   ```
   python3 main_contest.py --no-ui
   ```
3. 看終端機出現快照與「階段二」之後才按手臂：
   ```
   [b] 快照完成, 共 3 件:
   [main] === 階段二: 可以按手臂了 (0.0.0.0:5000) ===
   [io] a 通道走 Socket: A_REQ/A_DONE → $A,code ...
   ```
4. 比賽中不要碰程式。  
   - 隨機板：`[b] 給 red → 手臂(…)`  
   - 放置板：`[a] 判定 … → 送 IO`，以及 `[io] … → $A,…`
5. 結束後 Ctrl+C。

---

## 四、終端最後一行 → 原因 → 怎麼辦

| 最後一行 | 原因 | 怎麼辦 |
|---|---|---|
| `LinAlgError: Singular matrix` | 點太少／共線／公式錯 | 重取點／檢查公式 |
| `ValueError: matmul ... mismatch` | PIXELS 與 ARMS 點數不同 | 數一數 |
| `[camera] 試過 [0..5] 都讀不到畫面` | 相機沒接或被佔用 | 插好；關掉 tuner／sample |
| `找不到 vision_profiles.json` | 還沒存顏色 | 做第 1 步 |
| `[b] 注意: PICK_ORDER 有 'xxx'…` | 顏色名錯或被擋住 | 對名字；練習模式按 `r` 重拍 |
| `手臂一直收到 $NONE` | 順序用完 | 正式賽正常結束；練習加 `--practice` |
| `尚未連線, 無法送` | 手臂沒連上 5000 | 等階段二再連；檢查 IP |
| 送了 `A_REQ` 但 ready 一直 0 | 句子沒到／沒換行 | 確認 `A_REQ\n`；看終端有無「收到 A_REQ」 |
| 下一件 a 不辨識 | 忘了 `A_DONE` | 每件讀完 `$A` 後一定要送 `A_DONE` |

---

## 五、三個絕對不要

- **相機動過不重取點位**
- **啟動主程式時手臂在畫面內**
- **顏色名不一致**（`Red`、`red ` 都不算）

也不需要再接 R1～R4 / ready 實體線；接了也不會被這版程式使用。
