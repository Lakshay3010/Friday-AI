import ollama
import pyttsx3
import speech_recognition as sr
import pyautogui
import subprocess
import mss
import base64
import time
import os
import threading
import tkinter as tk
import math
import random
import json
import cv2
import webbrowser
import re
import queue
import urllib.parse
import urllib.request
from PIL import Image
import io
from datetime import datetime
import glob
from difflib import get_close_matches
import numpy as np

# ── Optional: soundcard for WASAPI loopback (call mode) ──
try:
    import soundcard as sc
    SOUNDCARD_AVAILABLE = True
except ImportError:
    SOUNDCARD_AVAILABLE = False
    print("[Warning]: 'soundcard' not installed. Call mode will use microphone fallback.")

# ── Optional: face_recognition for identity verification ──
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    print("[Warning]: 'face_recognition' not installed. Using basic OpenCV detection only.")
    print("           Run: pip install face_recognition")

# ── CONFIG ──────────────────────────────────────────────
ASSISTANT_NAME  = "FRIDAY"
USER_NAME       = "Boss"
BOSS_REAL_NAME  = "Lakshay"
LLM_MODEL       = "llama3.1:8b"
VISION_MODEL    = "llava:7b"
SCREEN_INTERVAL = 20
MEMORY_FILE     = "C:\\friday\\memory.json"
DASHBOARD_PATH  = "C:\\friday\\friday_dashboard.html"
FACES_DIR       = "C:\\friday\\faces"
BOSS_FACE_FILE  = "C:\\friday\\faces\\boss_encoding.npy"
KNOWN_FACES_FILE= "C:\\friday\\faces\\known_faces.json"
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5
# ────────────────────────────────────────────────────────

screen_context       = "Initializing..."
is_speaking          = False
is_listening         = False
conversation_history = []
conversation_lock    = threading.Lock()
user_present         = False
call_mode_active     = False
call_mode_lock       = threading.Lock()

# Face identity state
current_user_identity  = None   # None = unknown, "boss" = Boss, str = registered guest
unknown_face_pending   = False  # True when an unknown face is waiting for Boss approval
pending_face_encoding  = None   # encoding of face waiting to be named
pending_face_name      = None   # name given by unknown person
access_granted         = False  # True only when Boss (or Boss-approved guest) is active
identity_lock          = threading.Lock()

# ── DASHBOARD TRIGGER KEYWORDS ──
DASHBOARD_TRIGGERS = [
    "what's happening", "whats happening", "what is happening",
    "show me", "open dashboard", "show dashboard",
    "market briefing", "give me a briefing", "brief me",
    "what's the market", "whats the market",
    "news", "headlines", "world news",
    "stock", "crypto", "bitcoin", "finance",
    "bloomberg", "situation report", "sitrep",
    "what's going on", "whats going on",
    "open friday", "intel", "briefing",
    "market update", "financial update",
    "what's in the news", "whats in the news",
    "local news", "india news", "noida news",
]

# ══════════════════════════════════════════════════════════
#  TEXT → SPEAKABLE PREPROCESSOR
# ══════════════════════════════════════════════════════════
def make_speakable(text):
    text = re.sub(r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)',
                  lambda m: f"{m.group(1)} {m.group(2)} {m.group(3).upper()}", text)
    text = re.sub(r'(\d{1,2}):(\d{2})', r'\1 \2', text)
    text = re.sub(r'(\d)\.(\d)', r'\1 point \2', text)
    text = re.sub(r'[*_`#\[\]<>]', '', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()

# ══════════════════════════════════════════════════════════
#  TTS ENGINE
# ══════════════════════════════════════════════════════════
_tts_lock = threading.Lock()

def speak(text, gui=None, tag="friday", volume=1.0):
    global is_speaking

    if not _tts_lock.acquire(blocking=False):
        print(f"[Speak Skipped]: busy")
        return

    try:
        is_speaking = True
        print(f"\n[{ASSISTANT_NAME}]: {text}")

        if gui:
            gui.root.after(0, lambda t=text, tg=tag: gui.add_message(ASSISTANT_NAME, t, tg))
            gui.root.after(0, lambda: gui.set_status("SPEAKING...", gui.ACCENT))

        clean = make_speakable(text)

        def _do_speak():
            try:
                e = pyttsx3.init()
                voices = e.getProperty('voices')
                for v in voices:
                    if 'zira' in v.name.lower() or 'female' in v.name.lower():
                        e.setProperty('voice', v.id)
                        break
                e.setProperty('rate', 168)
                e.setProperty('volume', volume)
                e.say(clean)
                e.runAndWait()
                e.stop()
                del e
            except Exception as ex:
                print(f"[TTS Error]: {ex}")

        t = threading.Thread(target=_do_speak)
        t.start()
        t.join()

    finally:
        is_speaking = False
        _tts_lock.release()
        if gui:
            gui.root.after(0, lambda: gui.set_status(
                "CALL MODE ACTIVE" if call_mode_active else "AWAITING INPUT",
                gui.PINK if call_mode_active else gui.GREEN
            ))

# ══════════════════════════════════════════════════════════
#  MEMORY SYSTEM
# ══════════════════════════════════════════════════════════
def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
    except:
        pass
    return {"facts": [], "last_seen": None}

def save_memory(mem):
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
        with open(MEMORY_FILE, "w") as f:
            json.dump(mem, f, indent=2)
    except Exception as e:
        print(f"[Memory Error]: {e}")

def add_memory(text):
    mem = load_memory()
    mem["facts"].append({
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "day":  datetime.now().strftime("%A")
    })
    mem["facts"] = mem["facts"][-100:]
    save_memory(mem)

def get_relevant_memories(user_input):
    mem = load_memory()
    if not mem["facts"]:
        return ""
    keywords = [w for w in user_input.lower().split() if len(w) > 3]
    relevant = []
    for fact in mem["facts"][-30:]:
        if any(kw in fact["text"].lower() for kw in keywords):
            relevant.append(f"- [{fact['day']} {fact['time']}] {fact['text']}")
    return ("Relevant memories:\n" + "\n".join(relevant[-5:])) if relevant else ""

def should_remember(text):
    triggers = ["my ","i have","i am","i'm","i need","i want","remember",
                "don't forget","exam","meeting","birthday","deadline",
                "appointment","remind","tomorrow","next week","i like",
                "i hate","i prefer","my friend","my mom","my dad"]
    t = text.lower()
    return any(t.startswith(tr) or f" {tr}" in t for tr in triggers)

def update_last_seen():
    mem = load_memory()
    mem["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_memory(mem)

def get_last_seen_greeting():
    mem = load_memory()
    last = mem.get("last_seen")
    if not last:
        return None
    try:
        diff = datetime.now() - datetime.strptime(last, "%Y-%m-%d %H:%M")
        hours = diff.total_seconds() / 3600
        if hours < 1:    return None
        elif hours < 8:  return f"Welcome back, {USER_NAME}. Been about {int(hours)} hours."
        elif hours < 24: return f"Good to see you, {USER_NAME}. You were last here {int(hours)} hours ago."
        else:
            days = int(hours / 24)
            return f"Welcome back, {USER_NAME}. It's been {days} day{'s' if days>1 else ''} since you were last here."
    except:
        return None

# ══════════════════════════════════════════════════════════
#  FACE IDENTITY SYSTEM
# ══════════════════════════════════════════════════════════
def ensure_faces_dir():
    os.makedirs(FACES_DIR, exist_ok=True)

def load_known_faces():
    """Load all registered face encodings except boss."""
    known = {}
    try:
        if os.path.exists(KNOWN_FACES_FILE):
            with open(KNOWN_FACES_FILE, "r") as f:
                data = json.load(f)
            for name, enc_list in data.items():
                known[name] = np.array(enc_list)
    except Exception as e:
        print(f"[FaceDB Error]: {e}")
    return known

def save_known_face(name, encoding):
    """Save a new face encoding to the known faces database."""
    ensure_faces_dir()
    data = {}
    if os.path.exists(KNOWN_FACES_FILE):
        try:
            with open(KNOWN_FACES_FILE, "r") as f:
                data = json.load(f)
        except:
            pass
    data[name] = encoding.tolist()
    with open(KNOWN_FACES_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[FaceDB]: Saved encoding for '{name}'")

def register_boss_face(gui=None):
    """
    Capture Boss's face from webcam (5 shots, averaged encoding).
    Called on first run or when Boss says 'register me'.
    """
    ensure_faces_dir()
    if not FACE_RECOGNITION_AVAILABLE:
        msg = "Face recognition library not available. Install face_recognition package."
        speak(msg, gui)
        return False

    speak(f"Starting Boss registration. Please look at the camera. I'll take 5 photos.", gui)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        speak("I can't access the camera, Boss.", gui)
        return False

    encodings = []
    attempts = 0
    max_attempts = 30

    while len(encodings) < 5 and attempts < max_attempts:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.3)
            attempts += 1
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")
        if locations:
            encs = face_recognition.face_encodings(rgb, locations)
            if encs:
                encodings.append(encs[0])
                speak(f"Got sample {len(encodings)} of 5.", gui)
                time.sleep(0.8)
        attempts += 1
        time.sleep(0.2)

    cap.release()

    if len(encodings) < 3:
        speak("Registration failed. Not enough clear face samples. Please try again in better lighting.", gui)
        return False

    avg_encoding = np.mean(encodings, axis=0)
    np.save(BOSS_FACE_FILE, avg_encoding)
    speak(f"Boss registered successfully with {len(encodings)} samples. Identity confirmed.", gui)
    return True

def register_new_person(name, encoding, gui=None):
    """Register a Boss-approved guest."""
    save_known_face(name, encoding)
    speak(f"{name} has been registered and granted access, {USER_NAME}.", gui)

def identify_face(frame_rgb):
    """
    Returns: 'boss', known_name, or None (unknown).
    Uses face_recognition library for reliable matching.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return "boss"  # fallback: can't verify, assume boss

    locations = face_recognition.face_locations(frame_rgb, model="hog")
    if not locations:
        return None

    encodings = face_recognition.face_encodings(frame_rgb, locations)
    if not encodings:
        return None

    face_enc = encodings[0]

    # Check boss first
    if os.path.exists(BOSS_FACE_FILE):
        boss_enc = np.load(BOSS_FACE_FILE)
        distance = face_recognition.face_distance([boss_enc], face_enc)[0]
        if distance < 0.50:  # strict threshold for boss
            return "boss"

    # Check known guests
    known = load_known_faces()
    for name, enc in known.items():
        distance = face_recognition.face_distance([enc], face_enc)[0]
        if distance < 0.55:
            return name

    return None  # unknown face

def capture_face_for_registration(gui=None):
    """
    Capture a single face encoding for guest registration.
    Returns (encoding, success).
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return None, False

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None, False

    encoding = None
    attempts = 0
    while attempts < 20:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.3)
            attempts += 1
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")
        if locations:
            encs = face_recognition.face_encodings(rgb, locations)
            if encs:
                encoding = encs[0]
                break
        attempts += 1
        time.sleep(0.2)

    cap.release()
    return encoding, encoding is not None

# ══════════════════════════════════════════════════════════
#  TIME AWARENESS
# ══════════════════════════════════════════════════════════
def get_time_context():
    now = time.localtime()
    hour = now.tm_hour
    weekday = now.tm_wday
    day = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][weekday]
    if 5 <= hour < 12:    period = "morning"
    elif 12 <= hour < 17: period = "afternoon"
    elif 17 <= hour < 21: period = "evening"
    else:                 period = "night"
    return {"hour": hour, "minute": now.tm_min, "period": period,
            "day": day, "is_weekend": weekday >= 5,
            "time_str": time.strftime("%I:%M %p")}

def get_greeting():
    back = get_last_seen_greeting()
    if back: return back
    t = get_time_context()
    h = t["hour"]
    if 5 <= h < 7:    return f"You're up early — it's only {t['time_str']}. Good morning, {USER_NAME}."
    elif 7 <= h < 12: return f"Good morning, {USER_NAME}. It's {t['time_str']} on {t['day']}. I'm online."
    elif 12 <= h < 14:return f"Good afternoon, {USER_NAME}. It's {t['time_str']}. Hope the morning was good."
    elif 14 <= h < 17:return f"Afternoon, {USER_NAME}. {t['time_str']} on {t['day']}. What do you need?"
    elif 17 <= h < 20:return f"Good evening, {USER_NAME}. It's {t['time_str']}. Wrapping up or getting started?"
    elif 20 <= h < 23:return f"Evening. It's {t['time_str']}. Getting late — what are we working on?"
    elif h == 23:      return f"It's {t['time_str']}, {USER_NAME}. Almost midnight. You sure about this?"
    elif 0 <= h < 2:   return f"Past midnight — {t['time_str']}. Burning the midnight oil again, {USER_NAME}."
    elif 2 <= h < 5:   return f"It's {t['time_str']}. This late? I hope it's worth it."
    else:              return f"Online. {t['time_str']}. Ready when you are."

def get_time_nudge():
    t = get_time_context()
    h, m = t["hour"], t["minute"]
    if m not in [0, 30]: return None
    nudges = {
        23: ["Just so you know, it's 11 PM. Might want to wrap up soon.",
             "It's getting late. Don't forget to rest."],
        0:  ["Midnight. You're still here. Sleep is important.",
             "It's midnight. Your body needs rest."],
        1:  [f"1 AM, {USER_NAME}. Whatever this is, it can wait till morning."],
        2:  [f"2 AM. I'm on silicon — you're not. Get some rest, {USER_NAME}."],
        3:  ["3 AM. At this point just own the all-nighter."],
        6:  [f"Good morning. 6 AM — did you sleep at all, {USER_NAME}?"],
        8:  ["Morning! 8 AM. Productive hours ahead."],
        12: ["It's noon. Good time for a break."],
        18: ["6 PM. Time to wind down a bit?"],
        22: [f"It's 10 PM, {USER_NAME}. Your brain works better rested."],
    }
    if h in nudges and m == 0:
        return random.choice(nudges[h])
    if h in [23,0,1,2] and m == 30:
        return f"Still going at {t['time_str']}. You sure you don't need a break?"
    return None

def time_watcher(gui):
    last_nudge_time = (-1, -1)
    while True:
        try:
            now = time.localtime()
            h, m = now.tm_hour, now.tm_min
            if (h, m) != last_nudge_time:
                nudge = get_time_nudge()
                if nudge and not is_speaking and not is_listening and not call_mode_active:
                    last_nudge_time = (h, m)
                    speak(nudge, gui, tag="proactive")
        except Exception as e:
            print(f"[Time Error]: {e}")
        time.sleep(60)

# ══════════════════════════════════════════════════════════
#  FACE WATCHER — WITH IDENTITY VERIFICATION
# ══════════════════════════════════════════════════════════
def face_watcher(gui):
    global user_present, current_user_identity, unknown_face_pending
    global pending_face_encoding, pending_face_name, access_granted

    try:
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    except Exception as e:
        print(f"[Face Init Error]: {e}")
        return

    # If boss face not registered yet, register now
    if FACE_RECOGNITION_AVAILABLE and not os.path.exists(BOSS_FACE_FILE):
        speak(f"Hello! I don't have your face on file yet, {USER_NAME}. Let's get you registered.", gui)
        register_boss_face(gui)

    cap = None
    was_present = False
    absent_count = 0
    present_count = 0
    last_identity = None
    identity_check_interval = 0  # check identity every N frames

    while True:
        try:
            if cap is None:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    time.sleep(10)
                    continue

            ret, frame = cap.read()
            if not ret:
                time.sleep(2)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))
            seen = len(faces) > 0

            if seen:
                present_count += 1
                absent_count = 0
            else:
                absent_count += 1
                present_count = 0

            # ── Face appeared ──
            if present_count == 3 and not was_present:
                was_present = True
                user_present = True
                gui.root.after(0, lambda: gui.update_face_status(True, "DETECTING..."))

                # Identify who it is
                if FACE_RECOGNITION_AVAILABLE:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    identity = identify_face(rgb)
                else:
                    identity = "boss"  # fallback

                with identity_lock:
                    current_user_identity = identity

                if identity == "boss":
                    access_granted = True
                    update_last_seen()
                    gui.root.after(0, lambda: gui.update_face_status(True, f"{BOSS_REAL_NAME.upper()} — BOSS"))
                    if not is_speaking and not call_mode_active:
                        speak(get_greeting(), gui, tag="proactive")

                elif identity is not None:
                    # Known guest
                    access_granted = True
                    gui.root.after(0, lambda i=identity: gui.update_face_status(True, f"GUEST: {i.upper()}"))
                    if not is_speaking:
                        speak(f"Welcome back, {identity}. You have limited access. {USER_NAME} has approved your profile.", gui, tag="proactive")

                else:
                    # Unknown face — hold access
                    access_granted = False
                    unknown_face_pending = True
                    gui.root.after(0, lambda: gui.update_face_status(True, "⚠ UNKNOWN — RESTRICTED"))

                    # Capture encoding for later registration
                    if FACE_RECOGNITION_AVAILABLE:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        locs = face_recognition.face_locations(rgb, model="hog")
                        if locs:
                            encs = face_recognition.face_encodings(rgb, locs)
                            if encs:
                                pending_face_encoding = encs[0]

                    if not is_speaking:
                        speak("Unrecognized face detected. Who are you? Please state your name.", gui, tag="proactive")
                        # Listen for the name in a background thread
                        threading.Thread(
                            target=_handle_unknown_visitor,
                            args=(gui,),
                            daemon=True
                        ).start()

                last_identity = identity

            # ── Periodic re-identification (every ~5 seconds) ──
            if was_present and present_count % 15 == 0 and FACE_RECOGNITION_AVAILABLE:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                identity = identify_face(rgb)
                if identity != last_identity and identity is not None:
                    last_identity = identity
                    with identity_lock:
                        current_user_identity = identity
                    if identity == "boss":
                        access_granted = True
                        gui.root.after(0, lambda: gui.update_face_status(True, f"{BOSS_REAL_NAME.upper()} — BOSS"))
                    elif identity:
                        access_granted = True
                        gui.root.after(0, lambda i=identity: gui.update_face_status(True, f"GUEST: {i.upper()}"))

            # ── Face left ──
            if absent_count >= 10 and was_present:
                user_present = False
                was_present = False
                access_granted = False
                with identity_lock:
                    current_user_identity = None
                gui.root.after(0, lambda: gui.update_face_status(False))

        except Exception as e:
            print(f"[Face Error]: {e}")
            if cap:
                cap.release()
            cap = None
            time.sleep(5)
        time.sleep(0.5)

def _handle_unknown_visitor(gui):
    """Listen for the unknown visitor's name, then alert Boss."""
    global pending_face_name, unknown_face_pending

    time.sleep(1)
    r = sr.Recognizer()
    name = None
    try:
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=8, phrase_time_limit=6)
            name = r.recognize_google(audio).strip()
    except:
        name = "Unknown"

    pending_face_name = name
    print(f"[Visitor]: Identified themselves as '{name}'")

    speak(f"Hello {name}. Please wait while I alert {USER_NAME} for access verification.", gui, tag="proactive")

    # Alert boss
    speak(f"{USER_NAME}, someone named {name} is at the terminal. Say 'register {name}' to grant access, or 'deny {name}' to block them.", gui, tag="system")
    gui.add_message("SECURITY", f"⚠ Unknown visitor: '{name}' — awaiting Boss approval", "system")

def handle_registration_command(text, gui):
    """
    Returns True if this was a registration/denial command.
    Called from the main loop.
    """
    global unknown_face_pending, pending_face_name, pending_face_encoding
    global access_granted

    t = text.lower().strip()

    # Boss says: "register me" → re-register boss
    if "register me" in t or "register yourself" in t or "register boss" in t:
        threading.Thread(target=register_boss_face, args=(gui,), daemon=True).start()
        return True

    # Boss says: "register [name]" → approve pending visitor
    register_match = re.search(r"register\s+(\w+)", t)
    if register_match:
        name_to_register = register_match.group(1).capitalize()

        # If there's a pending face, use it
        if pending_face_encoding is not None:
            register_new_person(name_to_register, pending_face_encoding, gui)
            access_granted = True
            unknown_face_pending = False
            pending_face_encoding = None
            pending_face_name = None
        else:
            # No pending face — capture a fresh one
            speak(f"Please have {name_to_register} look at the camera. Capturing now.", gui)
            encoding, success = capture_face_for_registration(gui)
            if success:
                register_new_person(name_to_register, encoding, gui)
                access_granted = True
                unknown_face_pending = False
                pending_face_encoding = None
                pending_face_name = None
            else:
                speak(f"Couldn't capture a clear face for {name_to_register}. Please try again.", gui)
        return True

    # Boss says: "deny [name]"
    deny_match = re.search(r"deny\s+(\w+)", t)
    if deny_match:
        name = deny_match.group(1).capitalize()
        unknown_face_pending = False
        pending_face_encoding = None
        pending_face_name = None
        speak(f"Access denied for {name}. They will not be registered.", gui)
        return True

    return False

# ══════════════════════════════════════════════════════════
#  DASHBOARD LAUNCHER
# ══════════════════════════════════════════════════════════
def open_dashboard(query=""):
    try:
        path = DASHBOARD_PATH.replace("\\", "/")
        if query:
            encoded = urllib.parse.quote(query)
            url = f"file:///{path}?q={encoded}"
        else:
            url = f"file:///{path}"
        webbrowser.open(url)
        return True
    except Exception as e:
        print(f"[Dashboard Error]: {e}")
        return False

# ══════════════════════════════════════════════════════════
#  NEWS FETCH + SPEAK
# ══════════════════════════════════════════════════════════
# All RSS feeds including Indian sources
RSS_FEEDS = {
    "world": [
        {"name": "BBC World",   "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "Al Jazeera",  "url": "https://www.aljazeera.com/xml/rss/all.xml"},
        {"name": "Reuters",     "url": "https://feeds.reuters.com/reuters/worldNews"},
    ],
    "india": [
        {"name": "NDTV India",       "url": "https://feeds.feedburner.com/ndtvnews-india-news"},
        {"name": "Times of India",   "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"},
        {"name": "The Hindu",        "url": "https://www.thehindu.com/news/national/feeder/default.rss"},
        {"name": "India Today",      "url": "https://www.indiatoday.in/rss/home"},
        {"name": "Hindustan Times",  "url": "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml"},
        {"name": "NDTV Top Stories", "url": "https://feeds.feedburner.com/ndtvnews-top-stories"},
        {"name": "Economic Times",   "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms"},
    ],
    "tech": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "Wired",      "url": "https://www.wired.com/feed/rss"},
    ],
    "business": [
        {"name": "Economic Times", "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms"},
        {"name": "Mint",           "url": "https://www.livemint.com/rss/news"},
    ]
}

# Region → feed category + keyword mapping
REGION_MAP = {
    "india": ("india", "india"),
    "indian": ("india", "india"),
    "noida": ("india", "noida"),
    "delhi": ("india", "delhi"),
    "mumbai": ("india", "mumbai"),
    "bangalore": ("india", "bangalore"),
    "bengaluru": ("india", "bengaluru"),
    "hyderabad": ("india", "hyderabad"),
    "chennai": ("india", "chennai"),
    "kolkata": ("india", "kolkata"),
    "up": ("india", "uttar pradesh"),
    "uttar pradesh": ("india", "uttar pradesh"),
    "tech": ("tech", None),
    "technology": ("tech", None),
    "business": ("business", None),
    "economy": ("business", None),
    "finance": ("business", None),
    "world": ("world", None),
    "global": ("world", None),
    "international": ("world", None),
}

def detect_news_region(text):
    """Returns (feed_category, keyword_filter) for the given query."""
    t = text.lower()
    for region_kw, (category, keyword) in REGION_MAP.items():
        if region_kw in t:
            return category, keyword
    return "world", None

def fetch_rss(feed_url, timeout=8):
    """Fetch articles from a single RSS feed via rss2json proxy."""
    try:
        proxy_url = f"https://api.rss2json.com/v1/api.json?rss_url={urllib.parse.quote(feed_url)}&count=10"
        req = urllib.request.Request(proxy_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode())
            items = []
            for item in data.get("items", []):
                title = item.get("title", "").strip()
                link  = item.get("link", "")
                pub   = item.get("pubDate", "")
                if title:
                    items.append({"title": title, "link": link, "pubDate": pub})
            return items
    except Exception as e:
        print(f"[RSS Error] {feed_url}: {e}")
        return []

def fetch_news_articles(category="world", keyword=None, max_per_feed=6):
    """
    Fetch articles from the right category feeds.
    If keyword is set, filter articles containing it.
    Falls back to world news if category yields nothing.
    """
    feeds = RSS_FEEDS.get(category, RSS_FEEDS["world"])
    all_articles = []

    for feed in feeds:
        articles = fetch_rss(feed["url"])
        for art in articles[:max_per_feed]:
            art["source"] = feed["name"]
        all_articles.extend(articles[:max_per_feed])

    # Apply keyword filter if needed
    if keyword and all_articles:
        filtered = [a for a in all_articles if keyword.lower() in a["title"].lower()]
        if len(filtered) >= 2:
            return filtered
        # Not enough filtered results — return all and note it
        print(f"[News]: keyword '{keyword}' matched only {len(filtered)}, returning all")
        return all_articles

    # Fallback to world if category returned nothing
    if not all_articles and category != "world":
        print(f"[News]: No articles for category '{category}', falling back to world")
        for feed in RSS_FEEDS["world"]:
            articles = fetch_rss(feed["url"])
            for art in articles[:max_per_feed]:
                art["source"] = feed["name"]
            all_articles.extend(articles[:max_per_feed])

    return all_articles

def fetch_and_speak_news(gui, query=""):
    """Fetch news based on query context and speak top headlines."""
    category, keyword = detect_news_region(query)
    articles = fetch_news_articles(category=category, keyword=keyword)

    if not articles:
        speak("I'm having trouble fetching the news right now. The dashboard will still open with cached data.", gui)
        return

    location_str = keyword.title() if keyword else (category.title() if category != "world" else "")
    intro = f"Here's what's happening{' in ' + location_str if location_str else ''}, Boss."
    speak(intro, gui)

    for i, art in enumerate(articles[:4], 1):
        clean_title = art["title"].replace("...", "").strip()
        source_note = f" — {art['source']}" if art.get("source") else ""
        speak(f"Headline {i}: {clean_title}{source_note}.", gui)
        time.sleep(0.3)

# ══════════════════════════════════════════════════════════
#  SYSTEM CONTROL
# ══════════════════════════════════════════════════════════
APP_CACHE = {}

def launch_uwp_app(app_name):
    try:
        result = subprocess.run(
            f'powershell "Get-StartApps | Where-Object {{$_.Name -like \'*{app_name}*\'}} | Select-Object -First 1"',
            shell=True, capture_output=True, text=True
        )
        output = result.stdout.strip()
        if output:
            lines = output.splitlines()
            if len(lines) >= 3:
                app_id = lines[2].split()[-1]
                os.startfile(f"shell:AppsFolder\\{app_id}")
                return True
    except:
        pass
    return False

def search_start_menu(app_name):
    start_menu_paths = [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
    ]
    for base in start_menu_paths:
        for root, _, files in os.walk(base):
            files_lower = [f.lower() for f in files if f.endswith(".lnk")]
            matches = get_close_matches(app_name, files_lower, n=1, cutoff=0.6)
            if matches:
                try:
                    path = os.path.join(root, matches[0])
                    os.startfile(path)
                    APP_CACHE[app_name] = path
                    return True
                except:
                    pass
    return False

def search_registry(app_name):
    try:
        import winreg
        for reg_path in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        if app_name in subkey_name.lower():
                            subkey = winreg.OpenKey(key, subkey_name)
                            exe_path, _ = winreg.QueryValueEx(subkey, "")
                            if exe_path and os.path.exists(exe_path):
                                subprocess.Popen([exe_path])
                                APP_CACHE[app_name] = exe_path
                                return True
                        i += 1
                    except OSError:
                        break
            except:
                pass
    except:
        pass
    return False

def search_where(app_name):
    try:
        result = subprocess.run(f"where {app_name}.exe", shell=True, capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            exe = result.stdout.strip().splitlines()[0]
            subprocess.Popen([exe])
            APP_CACHE[app_name] = exe
            return True
    except:
        pass
    return False

def search_folders(app_name):
    bases = [
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for base in bases:
        if not base or not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            if root[len(base):].count(os.sep) > 2:
                dirs[:] = []
                continue
            for f in files:
                if f.lower() == f"{app_name}.exe":
                    try:
                        exe_path = os.path.join(root, f)
                        subprocess.Popen([exe_path])
                        APP_CACHE[app_name] = exe_path
                        return True
                    except:
                        pass
    return False

def find_and_launch_app(app_name):
    name = app_name.lower().strip()
    if name in APP_CACHE:
        try:
            subprocess.Popen([APP_CACHE[name]])
            return f"Opening {app_name}."
        except:
            del APP_CACHE[name]
    if search_start_menu(name): return f"Opening {app_name}."
    if search_registry(name):   return f"Opening {app_name}."
    if search_where(name):      return f"Opening {app_name}."
    if launch_uwp_app(name):    return f"Opening {app_name}."
    if search_folders(name):    return f"Opening {app_name}."
    webbrowser.open(f"https://www.google.com/search?q=download+{name}")
    return f"I couldn't find {app_name} on your system. I've opened it online — want me to download it?"

def open_app(app_name):
    name = app_name.lower().strip()
    builtin_map = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "settings": "ms-settings:",
    }
    for key, path in builtin_map.items():
        if key in name:
            try:
                os.startfile(path)
                return f"Opening {key}."
            except:
                pass
    return find_and_launch_app(name)

def run_cmd(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout or r.stderr or "Done."
    except Exception as e:
        return f"Error: {e}"

# ══════════════════════════════════════════════════════════
#  HANDLE COMMAND
# ══════════════════════════════════════════════════════════
def handle_command(text, gui):
    t = text.lower()

    # ── Registration commands (always allowed regardless of access) ──
    if handle_registration_command(text, gui):
        return ""  # already handled inside

    # ── Dashboard / Intel triggers ──
    if any(trigger in t for trigger in DASHBOARD_TRIGGERS):
        threading.Thread(target=fetch_and_speak_news, args=(gui, text), daemon=True).start()
        open_dashboard(query=text)
        return "Opening your intelligence dashboard, Boss. I'll read the headlines now."

    # ── Google search ──
    if t.startswith("search ") or t.startswith("google "):
        query = re.sub(r'^(search|google)\s+', '', t).strip()
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}")
        return f"Searching for {query}, Boss."

    # ── App open ──
    match = re.search(r"(open|launch)\s+(.*)", t)
    if match:
        app = match.group(2).strip()
        return open_app(app)

    if "type " in t:
        to_type = t.split("type ", 1)[-1].strip()
        time.sleep(0.5)
        pyautogui.typewrite(to_type, interval=0.04)
        return "Typed."

    if "press " in t:
        keys = t.replace("press", "").strip()
        try:
            pyautogui.hotkey(*keys.split("+"))
            return f"Pressed {keys}."
        except:
            return "Couldn't press that."

    if "screenshot" in t:
        path = os.path.expanduser("~\\Desktop\\friday_screenshot.png")
        pyautogui.screenshot(path)
        return "Screenshot saved to your Desktop."

    if "volume up" in t:
        for _ in range(5): pyautogui.press("volumeup")
        return "Volume up."

    if "volume down" in t:
        for _ in range(5): pyautogui.press("volumedown")
        return "Volume down."

    if "mute" in t:
        pyautogui.press("volumemute")
        return "Muted."

    if "shutdown" in t and "cancel" not in t:
        run_cmd("shutdown /s /t 10")
        return "Shutting down in 10 seconds."

    if "restart" in t:
        run_cmd("shutdown /r /t 10")
        return "Restarting in 10 seconds."

    if "cancel shutdown" in t:
        run_cmd("shutdown /a")
        return "Shutdown cancelled."

    return None

# ══════════════════════════════════════════════════════════
#  BROWSER FOR VISUAL QUERIES
# ══════════════════════════════════════════════════════════
VISUAL_KW = ["latest","today","weather","buy","shop","price",
             "image","photo","who is","what is","where is","map","recipe",
             "movie","trailer","score","live","trending","video","watch","find"]

def should_open_browser(text):
    t = text.lower()
    if any(trigger in t for trigger in DASHBOARD_TRIGGERS):
        return False
    return any(kw in t for kw in VISUAL_KW)

def open_browser_search(query):
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ','+')}")

# ══════════════════════════════════════════════════════════
#  SCREEN WATCHER
# ══════════════════════════════════════════════════════════
def capture_screen():
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img = img.resize((960, 540))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

def screen_watcher(gui):
    global screen_context
    last = ""
    while True:
        try:
            img_b64 = capture_screen()
            response = ollama.chat(model=VISION_MODEL, messages=[{
                "role": "user",
                "content": "One sentence only: what is the user doing right now on screen?",
                "images": [img_b64]
            }])
            screen_context = response['message']['content'].strip()
            gui.update_screen_context(screen_context)
            print(f"[Screen]: {screen_context}")
            if screen_context != last and last and not call_mode_active:
                comment = get_proactive_comment(screen_context)
                if comment and not is_speaking and not is_listening:
                    speak(comment, gui, tag="proactive")
            last = screen_context
        except Exception as e:
            screen_context = "Screen unavailable."
            print(f"[Screen Error]: {e}")
        time.sleep(SCREEN_INTERVAL)

def get_proactive_comment(context):
    try:
        resp = ollama.chat(model=LLM_MODEL, messages=[{
            "role": "user",
            "content": f"Screen: {context}\nIf you'd say something helpful as an AI assistant, ONE short sentence max 15 words. Otherwise: NO"
        }])
        reply = resp['message']['content'].strip()
        return None if reply.upper().startswith("NO") or len(reply) < 5 else reply
    except:
        return None

# ══════════════════════════════════════════════════════════
#  AI BRAIN
# ══════════════════════════════════════════════════════════
def ask_llm(user_input):
    global conversation_history, screen_context
    t = get_time_context()
    mem = get_relevant_memories(user_input)
    system_prompt = f"""You are FRIDAY, Lakshay's personal AI assistant — inspired by Tony Stark's AI from the MCU.
Sharp, witty, intelligent, confident. Always call him '{USER_NAME}'. Speak like a real human, never robotic.
You remember things {USER_NAME} has told you and reference them naturally.
You have a live intelligence dashboard that shows real-time markets, news feeds, crypto prices, and global maps.
When {USER_NAME} asks about markets, news, or world events — confirm you're opening the dashboard AND give a brief spoken summary.

Screen: {screen_context}
Time: {t['time_str']} on {t['day']} ({t['period']})
Weekend: {t['is_weekend']}
{mem}

Rules:
- SHORT natural responses. 1-3 sentences max unless asked for detail.
- No bullet points, no markdown, no asterisks. Just natural speech.
- Reference memories naturally when relevant.
- Acknowledge late hours naturally when relevant.
- You control the PC: open apps, play music, send WhatsApp messages, open the dashboard."""

    with conversation_lock:
        conversation_history.append({"role": "user", "content": user_input})
        if len(conversation_history) > 12:
            conversation_history = conversation_history[-12:]
        history_snapshot = list(conversation_history)

    response = ollama.chat(model=LLM_MODEL,
        messages=[{"role": "system", "content": system_prompt}] + history_snapshot)
    reply = response['message']['content'].strip()

    with conversation_lock:
        conversation_history.append({"role": "assistant", "content": reply})
    return reply

# ══════════════════════════════════════════════════════════
#  CALL MODE  (FIXED)
# ══════════════════════════════════════════════════════════
_call_thread = None
_call_stop_event = threading.Event()

# Shared recognizer for call mode
call_recognizer = sr.Recognizer()
call_recognizer.energy_threshold = 300
call_recognizer.dynamic_energy_threshold = True
call_recognizer.pause_threshold = 1.0
call_recognizer.phrase_threshold = 0.3

def _listen_system_audio_wasapi():
    """Listen to system audio (what's playing through speakers) via loopback."""
    if not SOUNDCARD_AVAILABLE:
        return None

    try:
        default_speaker = sc.default_speaker()
        loopback_mic = sc.get_microphone(
            id=str(default_speaker.name),
            include_loopback=True
        )
        SAMPLE_RATE = 16000
        DURATION    = 6  # seconds per chunk

        with loopback_mic.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
            data = recorder.record(numframes=SAMPLE_RATE * DURATION)

        # Flatten to mono float32
        if data.ndim > 1:
            data = data.mean(axis=1)

        # Skip if silent
        rms = float(np.sqrt(np.mean(data ** 2)))
        if rms < 0.003:
            return ""

        # Convert to int16 bytes for speech_recognition
        audio_int16 = np.clip(data * 32767, -32768, 32767).astype(np.int16)
        audio_data  = sr.AudioData(audio_int16.tobytes(), SAMPLE_RATE, 2)

        text = call_recognizer.recognize_google(audio_data, language="en-IN")
        return text.strip()

    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[WASAPI Error]: {e}")
        return None   # Signal to fallback to mic

def _listen_mic_for_caller():
    """Listen on microphone — use when WASAPI not available or fails."""
    try:
        with sr.Microphone() as source:
            call_recognizer.adjust_for_ambient_noise(source, duration=0.4)
            audio = call_recognizer.listen(source, timeout=8, phrase_time_limit=12)
            text = call_recognizer.recognize_google(audio, language="en-IN")
            return text.strip()
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print(f"[Mic Fallback Error]: {e}")
        return ""

def _call_mode_loop(gui, call_type="mixed"):
    """Main call mode listening loop — listens, transcribes, and suggests replies."""
    global call_mode_active
    print("[Call Mode]: Loop started")
    wasapi_failed = not SOUNDCARD_AVAILABLE
    consecutive_failures = 0

    while not _call_stop_event.is_set():
        try:
            caller_said = None

            if not wasapi_failed:
                result = _listen_system_audio_wasapi()
                if result is None:
                    # WASAPI failed — switch to mic fallback
                    print("[Call Mode]: WASAPI failed, switching to mic fallback")
                    wasapi_failed = True
                    consecutive_failures += 1
                    time.sleep(1)
                    continue
                caller_said = result
            else:
                caller_said = _listen_mic_for_caller()

            if not caller_said:
                continue

            # Ignore very short utterances (ambient noise, filler words)
            if len(caller_said.split()) < 3:
                continue

            # Don't process FRIDAY's own speech
            if any(phrase in caller_said.lower() for phrase in [
                "i suggest", "you could say", "how about", USER_NAME.lower(), "friday"
            ]):
                continue

            print(f"[Call — Caller said]: {caller_said}")
            gui.root.after(0, lambda s=caller_said: gui.add_message("CALLER", s, "call_other"))

            # Generate suggestion
            suggestion = ask_llm_call(caller_said, call_type)
            if not suggestion:
                continue

            print(f"[FRIDAY Suggests]: {suggestion}")
            gui.root.after(0, lambda s=suggestion: gui.add_message("SUGGEST", s, "call_suggest"))

            # Speak suggestion quietly so Boss hears it but caller may not
            speak(suggestion, gui, tag="call_suggest", volume=0.50)
            consecutive_failures = 0

        except Exception as e:
            print(f"[Call Loop Error]: {e}")
            consecutive_failures += 1
            if consecutive_failures > 5:
                print("[Call Mode]: Too many failures, pausing 10s")
                time.sleep(10)
                consecutive_failures = 0
            else:
                time.sleep(1)

    print("[Call Mode]: Loop stopped")

def start_call_mode(gui, call_type="mixed"):
    global call_mode_active, _call_thread
    with call_mode_lock:
        if call_mode_active:
            return "Call mode is already active."
        call_mode_active = True
        _call_stop_event.clear()

    gui.root.after(0, lambda: gui.set_call_mode_ui(True))
    _call_thread = threading.Thread(
        target=_call_mode_loop, args=(gui, call_type), daemon=True
    )
    _call_thread.start()

    mode_name = {
        "professional": "professional mode — formal replies",
        "personal": "personal mode — casual replies",
        "mixed": "standard mode — I'll adapt to context"
    }.get(call_type, "standard mode")

    msg = f"Call mode activated in {mode_name}. I'll listen and whisper suggestions, {USER_NAME}."
    speak(msg, gui, tag="system")
    return msg

def stop_call_mode(gui):
    global call_mode_active
    with call_mode_lock:
        if not call_mode_active:
            return "Call mode isn't active."
        call_mode_active = False
        _call_stop_event.set()

    gui.root.after(0, lambda: gui.set_call_mode_ui(False))
    msg = f"Call mode deactivated. Back to normal, {USER_NAME}."
    speak(msg, gui, tag="system")
    return msg

def detect_call_command(text):
    t = text.lower()
    stop_kw = ["exit call mode","stop call mode","end call mode",
               "disable call mode","call mode off","deactivate call mode"]
    if any(kw in t for kw in stop_kw):
        return ("stop",)
    start_kw = ["call mode","start call mode","activate call mode",
                "enable call mode","friday call mode","call assistant",
                "i'm on a call","i am on a call","help me with my call",
                "assist my call","call help"]
    if any(kw in t for kw in start_kw):
        if "work" in t or "professional" in t or "business" in t or "meeting" in t:
            return ("start", "professional")
        elif "personal" in t or "friend" in t or "casual" in t:
            return ("start", "personal")
        else:
            return ("start", "mixed")
    return None

def ask_llm_call(caller_said, call_type="mixed"):
    t = get_time_context()
    mem = get_relevant_memories(caller_said)
    if call_type == "professional":
        tone_hint = "Professional, concise, confident. Suggest formal and clear replies."
    elif call_type == "personal":
        tone_hint = "Casual, warm, natural. Suggest friendly and relaxed replies."
    else:
        tone_hint = "Adapt tone to context — professional if work-related, casual if personal."

    system_prompt = f"""You are F.R.I.D.A.Y, assisting {USER_NAME} during a live phone or video call.
The other person just said something. Suggest a natural reply for {USER_NAME} to say.
Tone: {tone_hint}
Time: {t['time_str']} on {t['day']}
{mem}

Rules:
- Give ONLY the suggested reply text. Max 2 sentences.
- Do NOT say "I suggest", "You could say", or "How about". Just give the reply directly.
- Sound like {USER_NAME} is speaking naturally, not like an AI.
- If it's a question, answer it. If it's a statement, respond to it naturally.
- No markdown, no bullet points."""

    try:
        response = ollama.chat(model=LLM_MODEL, messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f'The person on the call said: "{caller_said}"'}
        ])
        return response['message']['content'].strip()
    except Exception as e:
        print(f"[Call LLM Error]: {e}")
        return None

# ══════════════════════════════════════════════════════════
#  LISTEN (main loop microphone)
# ══════════════════════════════════════════════════════════
recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8

def listen(gui):
    global is_listening
    with sr.Microphone() as source:
        is_listening = True
        if call_mode_active:
            gui.set_status("CALL MODE — LISTENING FOR YOU...", gui.PINK)
        else:
            gui.set_status("LISTENING...", gui.GREEN)
        print("\n[Listening...]")
        recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
            is_listening = False
            gui.set_status("PROCESSING...", gui.GOLD)
            text = recognizer.recognize_google(audio, language="en-IN")
            print(f"[You]: {text}")
            gui.root.after(0, lambda: gui.add_message("YOU", text, "you"))
            return text
        except sr.WaitTimeoutError:
            is_listening = False
            return ""
        except sr.UnknownValueError:
            is_listening = False
            return ""
        except Exception as e:
            is_listening = False
            print(f"[Listen Error]: {e}")
            return ""

# ══════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════
class FridayGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("F.R.I.D.A.Y")
        self.root.geometry("420x920+20+20")
        self.root.configure(bg="#000000")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.resizable(False, False)

        self.BG     = "#000000"
        self.PANEL  = "#030d1a"
        self.ACCENT = "#00c8ff"
        self.ACCENT2= "#0066ff"
        self.DIM    = "#003a5c"
        self.TEXT   = "#cceeff"
        self.SUBTEXT= "#4488aa"
        self.RED    = "#ff3344"
        self.GREEN  = "#00ffaa"
        self.GOLD   = "#ffa500"
        self.PINK   = "#ff69b4"
        self.ORANGE = "#ff8800"

        self.arc_angle  = 0
        self.pulse      = 0
        self.ring_radii = [60, 72, 85, 95]
        self.ring_speeds= [1.2, -0.8, 0.5, -1.5]
        self.ring_angles= [0, 45, 90, 135]

        self._build_ui()
        self._animate()

    def _build_ui(self):
        r = self.root

        # ── Title bar ──
        tb = tk.Frame(r, bg=self.PANEL, height=36)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Label(tb, text="  F.R.I.D.A.Y  ",
                 bg=self.PANEL, fg=self.ACCENT,
                 font=("Courier New", 9, "bold")).pack(side="left", padx=12, pady=8)
        tk.Label(tb, text="● ONLINE", bg=self.PANEL, fg=self.GREEN,
                 font=("Courier New", 8)).pack(side="right", padx=12)

        # ── Arc reactor canvas ──
        self.canvas = tk.Canvas(r, width=420, height=240,
                                bg=self.BG, highlightthickness=0)
        self.canvas.pack()

        # ── Status ──
        sf = tk.Frame(r, bg=self.BG)
        sf.pack(fill="x", padx=20)
        self.status_dot = tk.Label(sf, text="◉", fg=self.GREEN, bg=self.BG,
                                   font=("Courier New", 11))
        self.status_dot.pack(side="left")
        self.status_label = tk.Label(sf, text="SYSTEM READY — AWAITING INPUT",
                                     fg=self.ACCENT, bg=self.BG,
                                     font=("Courier New", 9, "bold"))
        self.status_label.pack(side="left", padx=6)

        # ── Face sensor ──
        self.face_label = tk.Label(r, text="◌ FACE SENSOR: SCANNING",
                                   fg=self.SUBTEXT, bg=self.BG,
                                   font=("Courier New", 7))
        self.face_label.pack(anchor="e", padx=20)

        # ── Identity badge ──
        self.identity_label = tk.Label(r, text="",
                                       fg=self.GOLD, bg=self.BG,
                                       font=("Courier New", 7, "bold"))
        self.identity_label.pack(anchor="e", padx=20)

        tk.Frame(r, bg=self.DIM, height=1).pack(fill="x", padx=20, pady=4)

        # ── Screen analysis ──
        tk.Label(r, text="[ SCREEN ANALYSIS ]", fg=self.SUBTEXT,
                 bg=self.BG, font=("Courier New", 8)).pack(anchor="w", padx=20)
        self.screen_label = tk.Label(r, text="Initializing visual sensors...",
                                     fg=self.DIM, bg=self.BG,
                                     font=("Courier New", 8),
                                     wraplength=380, justify="left")
        self.screen_label.pack(fill="x", padx=20, pady=(2, 4))

        self.memory_label = tk.Label(r, text="[ MEMORY: LOADING ]",
                                     fg=self.SUBTEXT, bg=self.BG,
                                     font=("Courier New", 7))
        self.memory_label.pack(anchor="w", padx=20)

        tk.Frame(r, bg=self.DIM, height=1).pack(fill="x", padx=20, pady=4)

        # ── Dashboard button ──
        self.dash_btn = tk.Button(
            r, text="⬡  OPEN INTELLIGENCE DASHBOARD",
            bg="#001428", fg=self.ACCENT,
            font=("Courier New", 9, "bold"),
            relief="flat", bd=0,
            activebackground="#002040",
            activeforeground=self.ACCENT,
            cursor="hand2",
            command=lambda: open_dashboard()
        )
        self.dash_btn.pack(fill="x", padx=20, pady=(0, 4))

        # ── Call mode button ──
        self.call_btn = tk.Button(
            r, text="📞  ACTIVATE CALL MODE",
            bg="#001a0f", fg=self.GREEN,
            font=("Courier New", 9, "bold"),
            relief="flat", bd=0,
            activebackground="#003322",
            activeforeground=self.GREEN,
            cursor="hand2",
            command=self._toggle_call_mode
        )
        self.call_btn.pack(fill="x", padx=20, pady=(0, 4))

        self.call_status = tk.Label(r, text="", bg=self.BG, fg=self.PINK,
                                    font=("Courier New", 8, "bold"))
        self.call_status.pack(fill="x", padx=20)

        # ── Register face button ──
        self.reg_btn = tk.Button(
            r, text="🔐  REGISTER / MANAGE FACES",
            bg="#1a0a00", fg=self.ORANGE,
            font=("Courier New", 9, "bold"),
            relief="flat", bd=0,
            activebackground="#331400",
            activeforeground=self.ORANGE,
            cursor="hand2",
            command=lambda: threading.Thread(target=register_boss_face, args=(self,), daemon=True).start()
        )
        self.reg_btn.pack(fill="x", padx=20, pady=(0, 4))

        tk.Frame(r, bg=self.DIM, height=1).pack(fill="x", padx=20, pady=4)

        # ── Conversation log ──
        tk.Label(r, text="[ CONVERSATION LOG ]", fg=self.SUBTEXT,
                 bg=self.BG, font=("Courier New", 8)).pack(anchor="w", padx=20, pady=(4, 2))

        cf = tk.Frame(r, bg=self.PANEL,
                      highlightbackground=self.DIM, highlightthickness=1)
        cf.pack(fill="both", expand=True, padx=20, pady=(0, 6))
        self.chat_text = tk.Text(cf, bg=self.PANEL, fg=self.TEXT,
                                 font=("Courier New", 9), wrap="word",
                                 state="disabled", relief="flat", padx=10, pady=8)
        self.chat_text.pack(fill="both", expand=True)
        self.chat_text.tag_config("friday",       foreground=self.ACCENT)
        self.chat_text.tag_config("you",          foreground=self.GOLD)
        self.chat_text.tag_config("system",       foreground=self.SUBTEXT)
        self.chat_text.tag_config("proactive",    foreground=self.GREEN)
        self.chat_text.tag_config("call_other",   foreground="#ff9966")
        self.chat_text.tag_config("call_suggest", foreground=self.PINK)
        self.chat_text.tag_config("security",     foreground=self.RED)

        # ── Bottom bar ──
        bb = tk.Frame(r, bg=self.PANEL, height=28)
        bb.pack(fill="x")
        bb.pack_propagate(False)
        tk.Label(bb, text=f"USER: {USER_NAME.upper()}  |  RTX 4060  |  LOCAL",
                 bg=self.PANEL, fg=self.SUBTEXT,
                 font=("Courier New", 7)).pack(side="left", padx=10, pady=6)
        self.clock_label = tk.Label(bb, text="", bg=self.PANEL,
                                    fg=self.ACCENT, font=("Courier New", 7))
        self.clock_label.pack(side="right", padx=10)
        self._tick()

    def _toggle_call_mode(self):
        if call_mode_active:
            threading.Thread(target=stop_call_mode, args=(self,), daemon=True).start()
        else:
            threading.Thread(target=start_call_mode, args=(self, "mixed"), daemon=True).start()

    def set_call_mode_ui(self, active):
        if active:
            self.call_btn.config(text="🔴  DEACTIVATE CALL MODE",
                                 bg="#1a0010", fg=self.PINK,
                                 activebackground="#330020")
            self.call_status.config(text="◉ CALL MODE ACTIVE — Listening & suggesting replies")
        else:
            self.call_btn.config(text="📞  ACTIVATE CALL MODE",
                                 bg="#001a0f", fg=self.GREEN,
                                 activebackground="#003322")
            self.call_status.config(text="")

    def _tick(self):
        self.clock_label.config(text=time.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick)

    def _draw_arc(self):
        c = self.canvas
        c.delete("all")
        cx, cy = 210, 120
        self.pulse = (self.pulse + 0.05) % (2 * math.pi)
        glow = int(180 + 60 * math.sin(self.pulse))

        unknown_face = unknown_face_pending

        for i, (r, speed) in enumerate(zip(self.ring_radii, self.ring_speeds)):
            self.ring_angles[i] = (self.ring_angles[i] + speed) % 360
            a = self.ring_angles[i]
            al = format(max(0, glow - i * 30), '02x')
            if unknown_face:
                col = f"#{al}{al}00"   # yellow for unknown
            elif call_mode_active:
                col = f"#{al}00{al}"   # pink for call
            else:
                col = f"#00{al}ff" if i % 2 == 0 else f"#0044{al}"
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=a, extent=280,
                         outline=col, width=2, style="arc")
            dx = cx + r * math.cos(math.radians(a))
            dy = cy + r * math.sin(math.radians(a))
            dot_color = self.ORANGE if unknown_face else (self.PINK if call_mode_active else self.ACCENT)
            c.create_oval(dx - 3, dy - 3, dx + 3, dy + 3, fill=dot_color, outline="")

        self.arc_angle = (self.arc_angle + 1.5) % 360
        hex_col = self.ORANGE if unknown_face else (self.PINK if call_mode_active else self.ACCENT2)
        for i in range(6):
            ang = math.radians(self.arc_angle + i * 60)
            x1 = cx + 38 * math.cos(ang); y1 = cy + 38 * math.sin(ang)
            x2 = cx + 38 * math.cos(ang + math.radians(60))
            y2 = cy + 38 * math.sin(ang + math.radians(60))
            c.create_line(x1, y1, x2, y2, fill=hex_col, width=1)

        cs = 22 + 4 * math.sin(self.pulse * 2)
        center_col = self.ORANGE if unknown_face else (self.PINK if call_mode_active else self.ACCENT)
        for r2, al in [(cs + 14, 40), (cs + 7, 80), (cs, 160)]:
            a2 = format(al, '02x')
            if unknown_face:
                color = f"#{a2}{a2}00"
            elif call_mode_active:
                color = f"#{a2}00{a2}"
            else:
                color = f"#00{a2}ff"
            c.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill="", outline=color, width=1)
        c.create_oval(cx - cs, cy - cs, cx + cs, cy + cs, fill="#001833", outline=center_col, width=2)

        tri = []
        for i in range(3):
            ang = math.radians(-90 + i * 120 + self.arc_angle * 0.3)
            tri.extend([cx + 13 * math.cos(ang), cy + 13 * math.sin(ang)])
        c.create_polygon(tri, fill=center_col, outline="")

        for i in range(0, 240, 8):
            c.create_line(0, i, 420, i, fill="#001122", width=1, stipple="gray25")

        if unknown_face:
            st, col = "⚠ UNKNOWN FACE — RESTRICTED", self.ORANGE
        elif call_mode_active:
            st, col = "◉ CALL MODE", self.PINK
        elif is_listening:
            st, col = "◉ LISTENING", self.GREEN
        elif is_speaking:
            st, col = "◈ SPEAKING", self.ACCENT
        elif user_present:
            st, col = "◉ USER DETECTED", self.GOLD
        else:
            st, col = "◌ STANDBY", self.SUBTEXT
        c.create_text(cx, cy + 108, text=st, fill=col, font=("Courier New", 10, "bold"))

        for x, y, dx, dy in [(10, 10, 1, 1), (410, 10, -1, 1), (10, 230, 1, -1), (410, 230, -1, -1)]:
            c.create_line(x, y, x + dx * 20, y, fill=center_col, width=1)
            c.create_line(x, y, x, y + dy * 20, fill=center_col, width=1)

    def _animate(self):
        self._draw_arc()
        self.root.after(33, self._animate)

    def add_message(self, sender, text, tag="friday"):
        self.chat_text.config(state="normal")
        prefix = {
            "friday":       "[F.R.I.D.A.Y] ",
            "you":          "[YOU] ",
            "system":       "[SYS] ",
            "proactive":    "[ALERT] ",
            "call_other":   "[CALLER] ",
            "call_suggest": "[SUGGEST] ",
            "security":     "[SECURITY] ",
        }.get(tag, "")
        self.chat_text.insert("end", f"\n{prefix}", tag)
        self.chat_text.insert("end", text + "\n")
        self.chat_text.config(state="disabled")
        self.chat_text.see("end")

    def set_status(self, text, color=None):
        color = color or self.ACCENT
        self.status_label.config(text=text, fg=color)
        self.status_dot.config(fg=color)

    def update_screen_context(self, text):
        short = text[:120] + "..." if len(text) > 120 else text
        self.screen_label.config(text=short, fg=self.SUBTEXT)

    def update_memory_count(self):
        mem = load_memory()
        count = len(mem.get("facts", []))
        self.memory_label.config(
            text=f"[ MEMORY: {count} STORED FACTS ]",
            fg=self.GREEN if count > 0 else self.SUBTEXT
        )

    def update_face_status(self, present, detail="SCANNING"):
        if present:
            is_boss   = "BOSS" in detail or BOSS_REAL_NAME.upper() in detail
            is_unknown= "UNKNOWN" in detail or "RESTRICTED" in detail
            color = self.GREEN if is_boss else (self.ORANGE if is_unknown else self.GOLD)
            self.face_label.config(
                text=f"◉ FACE SENSOR: {detail}", fg=color
            )
            self.identity_label.config(
                text=f"[ ID: {detail} ]", fg=color
            )
        else:
            self.face_label.config(text="◌ FACE SENSOR: SCANNING", fg=self.SUBTEXT)
            self.identity_label.config(text="", fg=self.SUBTEXT)

    def run(self):
        self.root.mainloop()

# ══════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════
def assistant_loop(gui):
    time.sleep(2)
    subprocess.Popen("ollama serve", shell=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    threading.Thread(target=screen_watcher, args=(gui,), daemon=True).start()
    threading.Thread(target=time_watcher,   args=(gui,), daemon=True).start()
    threading.Thread(target=face_watcher,   args=(gui,), daemon=True).start()
    gui.root.after(500, gui.update_memory_count)

    speak(get_greeting(), gui)
    update_last_seen()

    while True:
        try:
            gui.root.after(0, lambda: gui.update_face_status(user_present,
                current_user_identity.upper() if current_user_identity else "SCANNING"))

            user_input = listen(gui)
            if not user_input:
                continue

            t = user_input.lower()

            # ── Goodbye ──
            if any(x in t for x in ["goodbye friday", "shut down friday",
                                     "bye friday", "good bye friday"]):
                speak(f"Going offline. Stay sharp, {USER_NAME}.", gui)
                gui.root.after(2000, gui.root.destroy)
                break

            # ── Access control: non-boss, non-approved gets limited help ──
            with identity_lock:
                identity = current_user_identity
            if identity is None and unknown_face_pending:
                speak("I'm sorry, I can't process that until your identity is verified by Boss.", gui)
                continue

            # ── Call mode commands ──
            call_cmd = detect_call_command(user_input)
            if call_cmd:
                if call_cmd[0] == "start":
                    ctype = call_cmd[1] if len(call_cmd) > 1 else "mixed"
                    threading.Thread(target=start_call_mode, args=(gui, ctype), daemon=True).start()
                elif call_cmd[0] == "stop":
                    threading.Thread(target=stop_call_mode, args=(gui,), daemon=True).start()
                continue

            # ── Memory ──
            if should_remember(user_input):
                add_memory(user_input)
                gui.root.after(100, gui.update_memory_count)

            # ── System commands ──
            result = handle_command(user_input, gui)
            if result is not None:
                if result:  # empty string = handled silently (registration)
                    speak(result, gui)
                if should_open_browser(user_input):
                    open_browser_search(user_input)
                continue

            # ── Browser search ──
            if should_open_browser(user_input):
                open_browser_search(user_input)

            # ── LLM ──
            reply = ask_llm(user_input)
            speak(reply, gui)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Error]: {e}")
            continue

if __name__ == "__main__":
    gui = FridayGUI()
    threading.Thread(target=assistant_loop, args=(gui,), daemon=True).start()
    gui.run()