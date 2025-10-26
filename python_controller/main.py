# main.py
"""
Gesture + Voice + Cursor controller (smooth version)
----------------------------------------------------
- Cursor: smoothed & lerped index fingertip
- Scroll: index finger vertical zones (up/down)
- Click: toggle fingers (index <-> middle)
- Voice: click/open/scroll synonyms
- WebSocket: sends hover coords and commands to ws://localhost:8765

Requirements:
  pip install opencv-python mediapipe pyautogui speechrecognition websocket-client
(Windows: pyaudio may be needed for microphone)
"""
'''
import time
import threading
import json
import re
from collections import deque

import cv2
import mediapipe as mp
import pyautogui
import speech_recognition as sr
import websocket  # websocket-client

# ---------------- CONFIG ----------------
WS_URL = "ws://localhost:8765"
CAM_INDEX = 0
SMOOTHING_WINDOW = 7        # moving average window (larger = smoother)
LERP_FACTOR = 0.3           # linear interpolation smoothing between frames
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.6

# Scroll zones
SCROLL_ZONE_TOP = 0.36
SCROLL_ZONE_BOTTOM = 0.64
SCROLL_INTERVAL = 0.12
SCROLL_SENSITIVITY = 1200

# Toggle-click settings
TOGGLE_WINDOW = 0.6
TOGGLE_COOLDOWN = 0.6

# Voice command patterns
CLICK_VERBS_RE = r"(?:click|press|tap|select|activate|open|go to|goto|go|take me to|navigate to|show)"
HERE_WORDS = {"here", "that", "this", ""}

# Finger enums
FINGER_TIPS_ENUMS = [
    mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP,
    mp.solutions.hands.HandLandmark.MIDDLE_FINGER_TIP,
    mp.solutions.hands.HandLandmark.RING_FINGER_TIP,
    mp.solutions.hands.HandLandmark.PINKY_TIP
]

# ---------------- GLOBAL STATE ----------------
prev_positions = deque(maxlen=SMOOTHING_WINDOW)
last_toggle_time = 0.0
last_extended_single = None
last_click_time = 0.0
SCREEN_W, SCREEN_H = pyautogui.size()
ws = None
ws_lock = threading.Lock()
stop_threads = False
last_smoothed = (SCREEN_W // 2, SCREEN_H // 2)

# ---------------- WebSocket client ----------------
def ws_connect_background():
    global ws
    while not stop_threads:
        with ws_lock:
            try:
                if ws is None:
                    ws = websocket.create_connection(WS_URL, timeout=3)
                    print("[ws] Connected to", WS_URL)
            except Exception:
                ws = None
        time.sleep(2)

def ws_send_safe(payload: dict):
    global ws
    try:
        with ws_lock:
            if ws:
                ws.send(json.dumps(payload))
                return True
    except Exception:
        try:
            ws.close()
        except:
            pass
        with ws_lock:
            ws = None
    return False

# ---------------- Mediapipe helpers ----------------
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

def finger_extended(hand_landmarks, tip_enum):
    tip = hand_landmarks.landmark[tip_enum.value]
    pip = hand_landmarks.landmark[tip_enum.value - 2]
    return tip.y < pip.y

def single_extended_finger(hand_landmarks):
    idx_ext = finger_extended(hand_landmarks, mp_hands.HandLandmark.INDEX_FINGER_TIP)
    mid_ext = finger_extended(hand_landmarks, mp_hands.HandLandmark.MIDDLE_FINGER_TIP)
    ring_ext = finger_extended(hand_landmarks, mp_hands.HandLandmark.RING_FINGER_TIP)
    pinky_ext = finger_extended(hand_landmarks, mp_hands.HandLandmark.PINKY_TIP)
    extended_count = sum([idx_ext, mid_ext, ring_ext, pinky_ext])
    if extended_count == 1:
        if idx_ext:
            return "index"
        if mid_ext:
            return "middle"
    return None

# ---------------- Smooth cursor helpers ----------------
def lerp(a, b, t):
    return a + (b - a) * t

def smooth_cursor(new_pos):
    """Combine rolling average + lerp smoothing."""
    global prev_positions, last_smoothed
    prev_positions.append(new_pos)
    avg_x = sum(p[0] for p in prev_positions) / len(prev_positions)
    avg_y = sum(p[1] for p in prev_positions) / len(prev_positions)
    smoothed_x = int(lerp(last_smoothed[0], avg_x, LERP_FACTOR))
    smoothed_y = int(lerp(last_smoothed[1], avg_y, LERP_FACTOR))
    last_smoothed = (smoothed_x, smoothed_y)
    return smoothed_x, smoothed_y

# ---------------- Gesture loop ----------------
def gesture_loop():
    global last_toggle_time, last_extended_single, last_click_time, stop_threads

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print("[camera] ERROR: cannot open camera index", CAM_INDEX)
        return

    hands = mp_hands.Hands(max_num_hands=1,
                           min_detection_confidence=MIN_DETECTION_CONFIDENCE,
                           min_tracking_confidence=MIN_TRACKING_CONFIDENCE)
    print("[camera] Camera started. Press ESC to stop.")

    last_scroll_time = 0.0

    while not stop_threads:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)
        gesture_text = "No hand"

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]
            index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP.value]
            nx = max(0.0, min(1.0, index_tip.x))
            ny = max(0.0, min(1.0, index_tip.y))

            # Map to screen + smooth
            sx = int(nx * SCREEN_W)
            sy = int(ny * SCREEN_H)
            smx, smy = smooth_cursor((sx, sy))

            try:
                pyautogui.moveTo(smx, smy, duration=0.01)
            except Exception:
                pass

            ws_send_safe({"x": smx, "y": smy})

            # Scroll control
            now = time.time()
            if ny < SCROLL_ZONE_TOP and (now - last_scroll_time) >= SCROLL_INTERVAL:
                dist = (SCROLL_ZONE_TOP - ny) / SCROLL_ZONE_TOP
                scroll_amount = int(max(20, dist * SCROLL_SENSITIVITY))
                pyautogui.scroll(scroll_amount)
                last_scroll_time = now
                gesture_text = f"Scroll Up ({scroll_amount})"
                ws_send_safe({"command": "scroll up"})
            elif ny > SCROLL_ZONE_BOTTOM and (now - last_scroll_time) >= SCROLL_INTERVAL:
                dist = (ny - SCROLL_ZONE_BOTTOM) / (1.0 - SCROLL_ZONE_BOTTOM)
                scroll_amount = int(max(20, dist * SCROLL_SENSITIVITY))
                pyautogui.scroll(-scroll_amount)
                last_scroll_time = now
                gesture_text = f"Scroll Down ({scroll_amount})"
                ws_send_safe({"command": "scroll down"})

            # Toggle-finger click
            current_single = single_extended_finger(hand_landmarks)
            if current_single is not None:
                if last_extended_single and last_extended_single != current_single:
                    if (now - last_toggle_time) <= TOGGLE_WINDOW and (now - last_click_time) > TOGGLE_COOLDOWN:
                        pyautogui.click()
                        last_click_time = now
                        gesture_text = f"Click ({last_extended_single}->{current_single})"
                        ws_send_safe({"command": "click"})
                        last_extended_single = None
                    else:
                        last_toggle_time = now
                        last_extended_single = current_single
                else:
                    last_toggle_time = now
                    last_extended_single = current_single

            mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
            frame_x = int(smx * (w / SCREEN_W))
            frame_y = int(smy * (h / SCREEN_H))
            cv2.circle(frame, (frame_x, frame_y), 8, (0, 0, 255), -1)

        cv2.putText(frame, gesture_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
        cv2.imshow("Gesture Mouse (ESC to quit)", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            stop_threads = True
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()
    print("[camera] Stopped.")

# ---------------- Voice ----------------
def start_voice_listener():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        print("[voice] Calibrating ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("[voice] Ready for commands!")

    def voice_callback(recognizer_obj, audio):
        try:
            raw = recognizer_obj.recognize_google(audio)
            text = raw.strip().lower()
            print("[voice] Heard:", repr(raw))

            # click-like phrases
            m = re.search(rf'\b{CLICK_VERBS_RE}\b\s*(?:the\s)?(.+)?', text)
            if m:
                target = (m.group(1) or "").strip()
                target = re.sub(r'\b(button|link|page|menu)\b$', '', target).strip()
                if target in HERE_WORDS:
                    pyautogui.click()
                    ws_send_safe({"command": "click"})
                    return
                if target:
                    target = re.sub(r'^(on|to|the)\s+', '', target).strip()
                    cmd_text = "click " + target
                    ws_send_safe({"command": cmd_text})
                    return

            # scrolls
            if any(p in text for p in ["scroll up", "go up", "move up", "page up", "up"]):
                pyautogui.scroll(300)
                ws_send_safe({"command": "scroll up"})
                return
            if any(p in text for p in ["scroll down", "go down", "move down", "page down", "down", "go to bottom"]):
                pyautogui.scroll(-300)
                ws_send_safe({"command": "scroll down"})
                return

            # fallback
            ws_send_safe({"command": text})

        except sr.UnknownValueError:
            print("[voice] Unrecognized speech")
        except sr.RequestError as e:
            print("[voice] STT request error:", e)
        except Exception as e:
            print("[voice] Unexpected voice error:", e)

    stop_fn = recognizer.listen_in_background(mic, voice_callback, phrase_time_limit=4)
    return stop_fn

# ---------------- MAIN ----------------
if __name__ == "__main__":
    try:
        t_ws = threading.Thread(target=ws_connect_background, daemon=True)
        t_ws.start()
        stop_listen = start_voice_listener()
        gesture_loop()
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        stop_threads = True
        try:
            stop_listen(wait_for_stop=False)
        except Exception:
            pass
        with ws_lock:
            try:
                if ws:
                    ws.close()
            except:
                pass
        print("Shutting down.")
        '''


"""
Updated controller WITH closed-fist click and voice click.
- Cursor: smoothed index fingertip
- Scroll: index finger vertical zones (up/down)
- Click: closed fist + voice click
- Voice: flexible commands (click/open/scroll synonyms)
- WebSocket: sends hover coords and commands to ws://localhost:8765
Requirements:
 pip install opencv-python mediapipe pyautogui speechrecognition websocket-client numpy
(Windows: pyaudio may be needed for microphone)
"""

import time
import threading
import json
import re
from collections import deque

import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import speech_recognition as sr
import websocket  # websocket-client

# ---------------- CONFIG ----------------
WS_URL = "ws://localhost:8765"
CAM_INDEX = 0
SMOOTHING_WINDOW = 5        # moving average window
MIN_DETECTION_CONFIDENCE = 0.6
MIN_TRACKING_CONFIDENCE = 0.6

# Scrolling control (normalized coords)
SCROLL_ZONE_TOP = 0.36
SCROLL_ZONE_BOTTOM = 0.64
SCROLL_INTERVAL = 0.12
SCROLL_SENSITIVITY = 1200

# Click settings
CLICK_COOLDOWN = 0.8        # seconds between consecutive clicks

# voice grammar helpers
CLICK_VERBS_RE = r"(?:click|press|tap|select|activate|open|go to|goto|go|take me to|navigate to|show)"
HERE_WORDS = {"here", "that", "this", ""}

# fingertip enums
FINGER_TIPS_ENUMS = [
    mp.solutions.hands.HandLandmark.INDEX_FINGER_TIP,
    mp.solutions.hands.HandLandmark.MIDDLE_FINGER_TIP,
    mp.solutions.hands.HandLandmark.RING_FINGER_TIP,
    mp.solutions.hands.HandLandmark.PINKY_TIP
]

# ---------------- GLOBAL STATE ----------------
prev_positions = deque(maxlen=SMOOTHING_WINDOW)
last_click_time = 0.0
SCREEN_W, SCREEN_H = pyautogui.size()
ws = None
ws_lock = threading.Lock()
stop_threads = False

# ---------------- WebSocket client w/ reconnect ----------------
def ws_connect_background():
    global ws
    while not stop_threads:
        with ws_lock:
            try:
                if ws is None:
                    ws = websocket.create_connection(WS_URL, timeout=3)
                    print("[ws] Connected to", WS_URL)
            except Exception:
                ws = None
        time.sleep(2)

def ws_send_safe(payload: dict):
    global ws
    try:
        with ws_lock:
            if ws:
                ws.send(json.dumps(payload))
                return True
    except Exception:
        try:
            ws.close()
        except:
            pass
        with ws_lock:
            ws = None
    return False

# ---------------- Mediapipe helpers ----------------
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

def finger_extended(hand_landmarks, tip_enum):
    """Return True if a finger tip is above (smaller y) its PIP joint (i.e., extended)."""
    tip = hand_landmarks.landmark[tip_enum.value]
    pip = hand_landmarks.landmark[tip_enum.value - 2]
    return tip.y < pip.y

def is_fist(hand_landmarks):
    """
    Detects a closed fist: all four fingers folded near MCP joints.
    Returns True if 3 or more fingers folded.
    """
    folded_count = 0
    tips = [8, 12, 16, 20]  # Index, middle, ring, pinky tips
    mcps = [5, 9, 13, 17]   # respective MCP joints
    for tip_idx, mcp_idx in zip(tips, mcps):
        tip_y = hand_landmarks.landmark[tip_idx].y
        mcp_y = hand_landmarks.landmark[mcp_idx].y
        if tip_y > mcp_y:
            folded_count += 1
    return folded_count >= 3

# ---------------- Gesture loop (cursor, scroll, fist-click) ----------------
def gesture_loop():
    global prev_positions, last_click_time, stop_threads

    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print("[camera] ERROR: cannot open camera index", CAM_INDEX)
        return

    hands = mp_hands.Hands(max_num_hands=1,
                           min_detection_confidence=MIN_DETECTION_CONFIDENCE,
                           min_tracking_confidence=MIN_TRACKING_CONFIDENCE)
    print("[camera] Camera started. Running in background. Press ESC to stop.")

    last_scroll_time = 0.0

    while not stop_threads:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame = cv2.flip(frame, 1)  # mirror
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        if results.multi_hand_landmarks:
            hand_landmarks = results.multi_hand_landmarks[0]

            # index fingertip normalized coords
            index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP.value]
            nx = max(0.0, min(1.0, index_tip.x))
            ny = max(0.0, min(1.0, index_tip.y))

            # map to screen coords
            sx = int(nx * SCREEN_W)
            sy = int(ny * SCREEN_H)

            # smoothing
            prev_positions.append((sx, sy))
            avg_x = int(sum(p[0] for p in prev_positions) / len(prev_positions))
            avg_y = int(sum(p[1] for p in prev_positions) / len(prev_positions))

            # move system cursor
            try:
                pyautogui.moveTo(avg_x, avg_y, duration=0.02)
            except Exception:
                pass

            # send hover coords to extension
            ws_send_safe({"x": avg_x, "y": avg_y})

            # ---------- SCROLL CONTROL ----------
            now = time.time()
            if ny < SCROLL_ZONE_TOP and (now - last_scroll_time) >= SCROLL_INTERVAL:
                dist = (SCROLL_ZONE_TOP - ny) / SCROLL_ZONE_TOP
                scroll_amount = int(max(20, dist * SCROLL_SENSITIVITY))
                pyautogui.scroll(scroll_amount)
                last_scroll_time = now
                ws_send_safe({"command": "scroll up"})
            elif ny > SCROLL_ZONE_BOTTOM and (now - last_scroll_time) >= SCROLL_INTERVAL:
                dist = (ny - SCROLL_ZONE_BOTTOM) / (1.0 - SCROLL_ZONE_BOTTOM)
                scroll_amount = int(max(20, dist * SCROLL_SENSITIVITY))
                pyautogui.scroll(-scroll_amount)
                last_scroll_time = now
                ws_send_safe({"command": "scroll down"})

            # ---------- FIST CLICK ----------
            if is_fist(hand_landmarks) and (now - last_click_time) > CLICK_COOLDOWN:
                pyautogui.click()
                last_click_time = now
                ws_send_safe({"command": "click"})

        # background mode: no window
        if cv2.waitKey(1) & 0xFF == 27:
            stop_threads = True
            break

    hands.close()
    cap.release()
    cv2.destroyAllWindows()
    print("[camera] Stopped.")

# ---------------- Voice (non-blocking) ----------------
def start_voice_listener():
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        print("[voice] Calibrating ambient noise... please be quiet")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("[voice] Calibration complete; listening in background.")

    def voice_callback(recognizer_obj, audio):
        try:
            raw = recognizer_obj.recognize_google(audio)
            text = raw.strip().lower()
            print("[voice] Heard:", repr(raw))

            # ---------- Voice click ----------
            if any(word in text for word in ["click", "tap", "press", "select"]):
                pyautogui.click()
                ws_send_safe({"command": "click"})
                print("[voice] Click executed")
                return

            # click-like phrases (open/go to/etc.)
            m = re.search(rf'\b{CLICK_VERBS_RE}\b\s*(?:the\s)?(.+)?', text)
            if m:
                target = (m.group(1) or "").strip()
                target = re.sub(r'\b(button|link|page|menu)\b$', '', target).strip()
                if target in HERE_WORDS:
                    pyautogui.click()
                    ws_send_safe({"command": "click"})
                    return
                if target:
                    target = re.sub(r'^(on|to|the)\s+', '', target).strip()
                    cmd_text = "click " + target
                    ws_send_safe({"command": cmd_text})
                    return

            # scroll commands
            if any(p in text for p in ["scroll up", "go up", "move up", "page up", "up"]):
                pyautogui.scroll(300)
                ws_send_safe({"command": "scroll up"})
                return
            if any(p in text for p in ["scroll down", "go down", "move down", "page down", "down", "go to bottom"]):
                pyautogui.scroll(-300)
                ws_send_safe({"command": "scroll down"})
                return

            # fallback
            ws_send_safe({"command": text})

        except sr.UnknownValueError:
            print("[voice] Could not understand audio")
        except sr.RequestError as e:
            print("[voice] STT request error:", e)
        except Exception as e:
            print("[voice] Unexpected voice error:", e)

    stop_fn = recognizer.listen_in_background(mic, voice_callback, phrase_time_limit=4)
    return stop_fn

# ---------------- MAIN ----------------
if __name__ == "__main__":
    try:
        t_ws = threading.Thread(target=ws_connect_background, daemon=True)
        t_ws.start()

        stop_listen = start_voice_listener()

        gesture_loop()

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        stop_threads = True
        try:
            stop_listen(wait_for_stop=False)
        except Exception:
            pass
        with ws_lock:
            try:
                if ws:
                    ws.close()
            except:
                pass
        print("Shutting down.")