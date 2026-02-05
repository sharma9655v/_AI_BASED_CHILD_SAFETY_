
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
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================== TWILIO ==================
TWILIO_SID = "ACa12e602647785572ebaf765659d26d23"
TWILIO_AUTH_TOKEN = "0e150a10a98b74ddc7d57e44fa3e01c6"
TWILIO_PHONE = "+14176076960"
PARENT_PHONE = "+918130631551"

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
    st.success("👨‍👩‍👧 Parent Connected")
    voice_lang = st.radio("Voice Language", ["English", "Hindi"])

# ================== FACE AI ==================
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

def extract_face_gray(gray_img):
    faces = face_cascade.detectMultiScale(gray_img, 1.3, 5)
    if len(faces) == 0:
        return None
    x, y, w, h = faces[0]
    return cv2.resize(gray_img[y:y+h, x:x+w], (200, 200))

def extract_face_from_path(path):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def extract_face_from_np(img_np):
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def match_faces(stored_path, test_np):
    stored_face = extract_face_from_path(stored_path)
    test_face = extract_face_from_np(test_np)

    if stored_face is None:
        return False, "No face in registered image"
    if test_face is None:
        return False, "No face detected"

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train([stored_face], np.array([0]))

    _, confidence = recognizer.predict(test_face)

    if confidence < 70:
        return True, f"Match Found (Confidence: {confidence:.2f})"
    return False, f"No Match (Confidence: {confidence:.2f})"

# ================== HELPERS ==================
def get_latest_child():
    cursor.execute("""
        SELECT child_name, age, clothing_color, lost_location, image_path
        FROM child_registry
        ORDER BY created_at DESC LIMIT 1
    """)
    return cursor.fetchone()

def trigger_emergency(lat, lon, lang):
    try:
        child = get_latest_child()
        if not child:
            return "No child registered."

        name, age, clothes, last_loc, _ = child
        time_now = datetime.now().strftime("%d-%m-%Y | %I:%M %p")
        maps = f"https://www.google.com/maps?q={lat},{lon}"

        msg = (
            f"🚨 CHILD SAFETY ALERT 🚨\n"
            f"Name: {name}\nAge: {age}\nClothes: {clothes}\n"
            f"Last Location: {last_loc}\nGPS: {maps}\nTime: {time_now}"
        )

        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=msg, from_=TWILIO_PHONE, to=PARENT_PHONE)

        speech = (
            f"Emergency alert. {name} has triggered SOS. Location sent."
            if lang == "English"
            else f"आपातकालीन अलर्ट। {name} ने एसओएस दबाया है।"
        )

        client.calls.create(
            twiml=f"<Response><Say>{speech}</Say></Response>",
            from_=TWILIO_PHONE,
            to=PARENT_PHONE
        )

        return True
    except Exception as e:
        return str(e)

# ================== UI ==================
st.title("🛡️ SafeGuard Child Safety AI")

tab1, tab2, tab3 = st.tabs([
    "👨‍👩‍👧 Parent Registration",
    "🆘 SOS Emergency",
    "🧠 AI Face Matching"
])

# ================== TAB 1 ==================
with tab1:
    with st.form("register"):
        name = st.text_input("Child Name")
        age = st.number_input("Age", 0, 18)
        clothes = st.text_input("Clothing Color")
        last_loc = st.text_area("Location Where Child Was Lost")
        photo = st.file_uploader("Recent Photo", ["jpg", "png", "jpeg"])
        submit = st.form_submit_button("Register")

    if submit:
        if not all([name, clothes, last_loc, photo]):
            st.error("All fields required")
        else:
            cid = str(uuid.uuid4())
            img = Image.open(photo).convert("RGB")
            path = os.path.join(UPLOAD_DIR, f"{cid}.jpg")
            img.save(path)

            cursor.execute("""
            INSERT INTO child_registry VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (cid, name, age, clothes, last_loc, path, datetime.now().isoformat()))
            conn.commit()

            st.success("Child Registered Successfully")
            st.image(img, width=200)

# ================== TAB 2 ==================
with tab2:
    location = streamlit_geolocation()
    if st.button("🆘 SOS"):
        if location['latitude'] and location['longitude']:
            result = trigger_emergency(
                location['latitude'],
                location['longitude'],
                voice_lang
            )
            if result is True:
                st.success("Parent Alerted Successfully")
                st.balloons()
            else:
                st.error(result)
        else:
            st.error("Enable location access")

# ================== TAB 3 ==================
with tab3:
    st.subheader("AI Face Detection & Matching")

    mode = st.radio(
        "Choose Image Source",
        ["📷 Live Camera", "🖼️ Upload Image"]
    )

    test_np = None

    if mode == "📷 Live Camera":
        cam_img = st.camera_input("Capture Image")
        if cam_img:
            test_np = np.array(Image.open(cam_img).convert("RGB"))
            st.image(test_np, width=300)

    if mode == "🖼️ Upload Image":
        upload_img = st.file_uploader(
            "Upload CCTV / Gallery Image",
            ["jpg", "png", "jpeg"]
        )
        if upload_img:
            test_np = np.array(Image.open(upload_img).convert("RGB"))
            st.image(test_np, width=300)

    if test_np is not None:
        child = get_latest_child()
        if child:
            _, _, _, _, stored_path = child
            matched, msg = match_faces(stored_path, test_np)

            if matched:
                st.success(f"✅ {msg}")
                st.balloons()
            else:
                st.error(f"❌ {msg}")
        else:
            st.warning("No registered child found.")
