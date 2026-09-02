"""
vision_tuner.py —— 調每個顏色的 HSV, 存進 vision_profiles.json (放置板與隨機板的顏色都存這一個檔)

操作:
  1. 把物件放到鏡頭下, 拉六條滑桿, 直到「mask」視窗只剩物件是白的、背景全黑
  2. 按 s → 在終端輸入顏色名 (小寫, 例 red) → 存檔 (同名會覆蓋)
  3. 換下一個物件, 重複 1~2
  4. 按 q 離開

紅色橫跨色相的頭尾 (0 和 179 相鄰): 把 H min 拉得比 H max 大, 畫面會顯示 HUE-WRAP, 代表兩段一起抓。
鍵位: s = 存檔   n = 載入下一個已存的顏色來修改   q = 離開
"""
import os
import cv2

import camera_config as cam
from color_detect import DetectConfig, detect_objects, load_profiles, save_profiles

PROFILES_FILE = "vision_profiles.json"
WIN = "tuner"

TRACKBARS = [   # (滑桿名, DetectConfig 欄位, 上限)
    ("H min", "h_min", 179), ("H max", "h_max", 179),
    ("S min", "s_min", 255), ("S max", "s_max", 255),
    ("V min", "v_min", 255), ("V max", "v_max", 255),
]


def set_trackbars(cfg):
    """把 cfg 的值填到滑桿上。"""
    for name, field, maxv in TRACKBARS:
        cv2.setTrackbarPos(name, WIN, getattr(cfg, field))


def read_trackbars(cfg):
    """把滑桿的值讀回 cfg。"""
    for name, field, _ in TRACKBARS:
        setattr(cfg, field, cv2.getTrackbarPos(name, WIN))


def save(cfg, profiles):
    """按 s: 問顏色名, 同名覆蓋, 存檔。"""
    name = input("  顏色名 (小寫, 例 red; 直接 Enter 取消): ").strip().lower()
    if not name:
        return
    cfg = DetectConfig(**vars(cfg))     # 複製一份再存, 免得之後拉滑桿改到存進去的那份
    cfg.name = name
    profiles[:] = [p for p in profiles if p.name != name] + [cfg]
    save_profiles(profiles, PROFILES_FILE)
    print(f"  已存 '{name}' → {PROFILES_FILE}  (目前有: {', '.join(p.name for p in profiles)})")


def main():
    profiles = load_profiles(PROFILES_FILE) if os.path.exists(PROFILES_FILE) else []
    cfg = DetectConfig(**vars(profiles[0])) if profiles else DetectConfig()
    idx = 0

    cap = cam.open_camera()
    if cap is None:
        print("[tuner] 開不了相機")
        return
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 540)
    for name, _, maxv in TRACKBARS:
        cv2.createTrackbar(name, WIN, 0, maxv, lambda _v: None)
    set_trackbars(cfg)
    print(__doc__)

    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        read_trackbars(cfg)
        objs, mask = detect_objects(frame, cfg)

        view = frame.copy()
        for i, o in enumerate(objs):                # 畫輪廓 + 中心 + 像素座標
            c = (0, 255, 0) if i == 0 else (0, 220, 220)
            cv2.drawContours(view, [o["contour"]], -1, c, 2)
            px, py = int(o["cx"]), int(o["cy"])
            cv2.drawMarker(view, (px, py), c, cv2.MARKER_CROSS, 18, 2)
            cv2.putText(view, f"#{i} ({px},{py})", (px + 8, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)
        wrap = "HUE-WRAP" if cfg.h_min > cfg.h_max else ""
        cv2.putText(view, f"editing: {cfg.name or '(new)'}  objs={len(objs)} {wrap}   s=save n=next q=quit",
                    (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow(WIN, view)
        cv2.imshow("mask", mask)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27):
            break
        elif key == ord('s'):
            save(cfg, profiles)
        elif key == ord('n') and profiles:          # 切到下一個已存的顏色
            idx = (idx + 1) % len(profiles)
            cfg = DetectConfig(**vars(profiles[idx]))
            set_trackbars(cfg)
            print(f"  載入 '{cfg.name}'")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
