import streamlit as st
import sqlite3
import os
import uuid
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
# Recommendation: Use st.secrets for these!
TWILIO_SID = "ACa12e602647785572ebaf765659d26d23"
TWILIO_AUTH_TOKEN = "0e150a10a98b74ddc7d57e44fa3e01c6"
TWILIO_PHONE = "+14176076960"

# Add your second verified number here
EMERGENCY_CONTACTS = ["+918130631551", "+917678495189"] 

# ================== DATABASE ==================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS child_registry (
    id TEXT PRIMARY KEY,
    child_name TEXT,
    age INTEGER,
    clothing_color TEXT,
    lost_location TEXT,
    image_path TEXT,
    created_at TEXT
)
""")
conn.commit()

# ================== SIDEBAR ==================
with st.sidebar:
    st.header("🚨 Emergency Network")
    st.success(f"👨‍👩‍👧 {len(EMERGENCY_CONTACTS)} Contacts Linked")
    voice_lang = st.radio("Voice Language", ["English", "Hindi"])

# ================== FACE AI ==================
# Load Haar Cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def extract_face_gray(gray_img):
    faces = face_cascade.detectMultiScale(gray_img, 1.1, 5)
    if len(faces) == 0:
        return None
    x, y, w, h = faces[0]
    return cv2.resize(gray_img[y:y+h, x:x+w], (200, 200))

def extract_face_from_path(path):
    img = cv2.imread(path)
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def extract_face_from_np(img_np):
    # Convert RGB (from PIL/Streamlit) to BGR (for OpenCV)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def match_faces(stored_path, test_np):
    stored_face = extract_face_from_path(stored_path)
    test_face = extract_face_from_np(test_np)

    if stored_face is None: return False, "No face in registered image"
    if test_face is None: return False, "No face detected in current view"

    # NOTE: Requires opencv-contrib-python
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train([stored_face], np.array([0]))
        label, confidence = recognizer.predict(test_face)
        
        # LBPH: Lower confidence score = Better match
        if confidence < 80:
            return True, f"Match Found! (Score: {round(confidence, 2)})"
        return False, f"Not a Match (Score: {round(confidence, 2)})"
    except AttributeError:
        return False, "Error: LBPH module not found. Install opencv-contrib-python."

# ================== HELPERS ==================
def get_latest_child():
    cursor.execute("SELECT child_name, age, clothing_color, lost_location, image_path FROM child_registry ORDER BY created_at DESC LIMIT 1")
    return cursor.fetchone()

def trigger_emergency(lat, lon, lang):
    try:
        child = get_latest_child()
        if not child: return "No child registered."

        name, age, clothes, last_loc, _ = child
        time_now = datetime.now().strftime("%d-%m-%Y | %I:%M %p")
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"

        msg_body = (
            f"🚨 CHILD SAFETY ALERT 🚨\n"
            f"Name: {name}\nAge: {age}\nClothes: {clothes}\n"
            f"Location: {maps_link}\nTime: {time_now}"
        )

        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        
        # Audio setup
        if lang == "English":
            speech = f"Emergency. {name} has triggered SOS. Location sent."
            t_lang = "en-US"
        else:
            speech = f"आपातकालीन अलर्ट। {name} ने मदद मांगी है। स्थान भेज दिया गया है।"
            t_lang = "hi-IN"

        for contact in EMERGENCY_CONTACTS:
            if "X" not in contact: # Skip placeholders
                client.messages.create(body=msg_body, from_=TWILIO_PHONE, to=contact)
                client.calls.create(
                    twiml=f'<Response><Say language="{t_lang}">{speech}</Say></Response>',
                    from_=TWILIO_PHONE, to=contact
                )
        return True
    except Exception as e:
        return str(e)

# ================== UI ==================
st.title("🛡️ SafeGuard Child Safety AI")

tab1, tab2, tab3 = st.tabs(["👨‍👩‍👧 Parent Registration", "🆘 SOS Emergency", "🧠 AI Face Matching"])

with tab1:
    with st.form("register"):
        c_name = st.text_input("Child Name")
        c_age = st.number_input("Age", 0, 18)
        c_clothes = st.text_input("Clothing Color")
        c_loc = st.text_area("Last Seen Location")
        photo = st.file_uploader("Recent Photo", type=["jpg", "png", "jpeg"])
        submit = st.form_submit_button("Register Child")

    if submit:
        if not all([c_name, c_clothes, c_loc, photo]):
            st.error("Please fill all fields and upload a photo.")
        else:
            cid = str(uuid.uuid4())
            img = Image.open(photo).convert("RGB")
            path = os.path.join(UPLOAD_DIR, f"{cid}.jpg")
            img.save(path)

            cursor.execute("INSERT INTO child_registry VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (cid, c_name, c_age, c_clothes, c_loc, path, datetime.now().isoformat()))
            conn.commit()
            st.success("Child Registered Successfully!")

with tab2:
    st.subheader("Emergency SOS")
    location = streamlit_geolocation()
    if st.button("🆘 TRIGGER EMERGENCY ALERT"):
        if location.get('latitude'):
            with st.spinner("Notifying Emergency Contacts..."):
                res = trigger_emergency(location['latitude'], location['longitude'], voice_lang)
                if res is True:
                    st.success("Alerts Sent Successfully!")
                    st.balloons()
                else:
                    st.error(f"Alert Failed: {res}")
        else:
            st.error("Please wait for GPS to lock or enable location access.")

with tab3:
    st.subheader("AI Surveillance Mode")
    mode = st.radio("Source", ["📷 Live Camera", "🖼️ Upload Image"])
    test_img = None

    if mode == "📷 Live Camera":
        cam = st.camera_input("Scanner")
        if cam: test_img = np.array(Image.open(cam))
    else:
        file = st.file_uploader("Upload Image", type=["jpg", "jpeg", "png"])
        if file: test_img = np.array(Image.open(file))

    if test_img is not None:
        child_data = get_latest_child()
        if child_data:
            match, msg = match_faces(child_data[4], test_img)
            if match:
                st.success(msg)
            else:
                st.error(msg)
        else:
            st.warning("No registered child to compare against.")