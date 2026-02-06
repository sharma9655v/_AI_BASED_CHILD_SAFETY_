import streamlit as st
import sqlite3
import os
import uuid
import threading
from PIL import Image
from datetime import datetime
from twilio.rest import Client
from streamlit_geolocation import streamlit_geolocation
import cv2
import numpy as np

# ================== CONFIG ==================
st.set_page_config(page_title="SafeGuard Child Safety AI", page_icon="🛡️", layout="centered")

UPLOAD_DIR = "uploads"
DB_FILE = "child_safety.db"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================== TWILIO CONFIG ==================
TWILIO_SID = "ACc9b9941c778de30e2ed7ba57f87cdfbc"
TWILIO_AUTH_TOKEN = "b524116dc4b14af314a5919594df9121"
TWILIO_PHONE = "+15075195618"

# IMPORTANT: Both numbers MUST be verified at:
# https://console.twilio.com/us1/develop/phone-numbers/manage/verified
EMERGENCY_CONTACTS = [
    "+918130631551", 
    "+917678495189" 
]

# ================== DATABASE ==================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS child_registry (
    id TEXT PRIMARY KEY, child_name TEXT, age INTEGER,
    clothing_color TEXT, lost_location TEXT, image_path TEXT, created_at TEXT
)
""")
conn.commit()

# ================== FACE AI ==================
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def extract_face_from_path(path):
    img = cv2.imread(path)
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0: return None
    x, y, w, h = faces[0]
    return cv2.resize(gray[y:y+h, x:x+w], (200, 200))

def extract_face_from_np(img_np):
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0: return None
    x, y, w, h = faces[0]
    return cv2.resize(gray[y:y+h, x:x+w], (200, 200))

def match_faces(stored_path, test_np):
    stored_face = extract_face_from_path(stored_path)
    test_face = extract_face_from_np(test_np)
    if stored_face is None or test_face is None:
        return False, "Face not detected"
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train([stored_face], np.array([0]))
        _, conf = recognizer.predict(test_face)
        return (True, f"Match Found ({conf:.2f})") if conf < 75 else (False, f"No Match ({conf:.2f})")
    except: return False, "LBPH Error: Install opencv-contrib-python-headless"

# ================== HELPERS ==================
def get_latest_child():
    cursor.execute("SELECT child_name, age, clothing_color, lost_location, image_path FROM child_registry ORDER BY created_at DESC LIMIT 1")
    return cursor.fetchone()

def send_individual_alert(contact, msg_body, t_lang, speech, status_list):
    """Refined dispatch with explicit error logging for SMS"""
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        
        # 1. ATTEMPT SMS
        sms = client.messages.create(body=msg_body, from_=TWILIO_PHONE, to=contact)
        status_list.append(f"✅ SMS sent to {contact}")
        
        # 2. ATTEMPT CALL
        client.calls.create(
            twiml=f'<Response><Say language="{t_lang}">{speech}</Say></Response>',
            from_=TWILIO_PHONE, to=contact
        )
        status_list.append(f"✅ Call sent to {contact}")
        
    except Exception as e:
        status_list.append(f"❌ Error for {contact}: {str(e)}")

def trigger_emergency(lat, lon, lang):
    child = get_latest_child()
    if not child: return ["No child registered."]

    name, age, clothes, last_loc, _ = child
    maps_link = f"https://www.google.com/maps?q={lat},{lon}" # Improved URL format

    msg_body = f"🚨 CHILD SAFETY ALERT 🚨\nName: {name}\nAge: {age}\nClothes: {clothes}\nLoc: {maps_link}"

    speech = f"Emergency alert. {name} has triggered SOS." if lang == "English" else f"आपातकालीन अलर्ट। {name} ने मदद मांगी है।"
    twilio_lang = "en-US" if lang == "English" else "hi-IN"

    status_updates = []
    threads = []
    for contact in EMERGENCY_CONTACTS:
        if "+91XX" not in contact:
            t = threading.Thread(target=send_individual_alert, args=(contact, msg_body, twilio_lang, speech, status_updates))
            threads.append(t)
            t.start()

    for t in threads: t.join()
    return status_updates

# ================== UI ==================
st.title("🛡️ SafeGuard Child Safety AI")
tab1, tab2, tab3 = st.tabs(["👨‍👩‍👧 Parent Registration", "🆘 SOS Emergency", "🧠 AI Face Matching"])

with tab1:
    with st.form("register"):
        name = st.text_input("Child Name")
        age = st.number_input("Age", 0, 18)
        clothes = st.text_input("Clothing Color")
        last_loc = st.text_area("Last Seen Location")
        photo = st.file_uploader("Recent Photo", ["jpg", "png", "jpeg"])
        if st.form_submit_button("Register"):
            if all([name, clothes, last_loc, photo]):
                cid = str(uuid.uuid4())
                path = os.path.join(UPLOAD_DIR, f"{cid}.jpg")
                Image.open(photo).convert("RGB").save(path)
                cursor.execute("INSERT INTO child_registry VALUES (?, ?, ?, ?, ?, ?, ?)", (cid, name, age, clothes, last_loc, path, datetime.now().isoformat()))
                conn.commit()
                st.success("Registered!")
            else: st.error("Fields missing")

with tab2:
    st.sidebar.header("Settings")
    voice_lang = st.sidebar.radio("Voice Language", ["English", "Hindi"])
    location = streamlit_geolocation()
    if st.button("🆘 TRIGGER SOS"):
        if location.get('latitude'):
            results = trigger_emergency(location['latitude'], location['longitude'], voice_lang)
            for r in results:
                st.write(r)
            st.balloons()
        else: st.error("Location not found.")

with tab3:
    mode = st.radio("Source", ["📷 Live", "🖼️ Upload"])
    test_img = None
    if mode == "📷 Live":
        cam = st.camera_input("Scanner")
        if cam: test_img = np.array(Image.open(cam))
    else:
        file = st.file_uploader("CCTV Image", ["jpg", "png", "jpeg"])
        if file: test_img = np.array(Image.open(file))

    if test_img is not None:
        child = get_latest_child()
        if child:
            matched, msg = match_faces(child[4], test_img)
            st.success(msg) if matched else st.error(msg)