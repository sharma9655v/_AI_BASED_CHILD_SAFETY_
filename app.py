import streamlit as st
import sqlite3
import os
import uuid
import threading  # Integrated for simultaneous alerts
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
# It is highly recommended to use st.secrets["KEY_NAME"] for these!
TWILIO_SID = "ACa12e602647785572ebaf765659d26d23"
TWILIO_AUTH_TOKEN = "0e150a10a98b74ddc7d57e44fa3e01c6"
TWILIO_PHONE = "+14176076960"

# List of phone numbers to alert (Update second number here)
EMERGENCY_CONTACTS = [
    "+918130631551", 
    "+917678495189" # Ensure this is verified in Twilio Console
]

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
    if img is None: return None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def extract_face_from_np(img_np):
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return extract_face_gray(gray)

def match_faces(stored_path, test_np):
    stored_face = extract_face_from_path(stored_path)
    test_face = extract_face_from_np(test_np)

    if stored_face is None:
        return False, "No face in registered image"
    if test_face is None:
        return False, "No face detected"

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train([stored_face], np.array([0]))
        _, confidence = recognizer.predict(test_face)

        if confidence < 75:
            return True, f"Match Found (Confidence: {confidence:.2f})"
        return False, f"No Match (Confidence: {confidence:.2f})"
    except AttributeError:
        return False, "Error: LBPH module missing. Use opencv-contrib-python."

# ================== HELPERS ==================
def get_latest_child():
    cursor.execute("""
        SELECT child_name, age, clothing_color, lost_location, image_path
        FROM child_registry
        ORDER BY created_at DESC LIMIT 1
    """)
    return cursor.fetchone()

def send_individual_alert(client, contact, msg_body, t_lang, speech):
    """Function to alert a single contact (used for threading)"""
    try:
        # 1. Send SMS
        client.messages.create(body=msg_body, from_=TWILIO_PHONE, to=contact)
        # 2. Trigger Call
        client.calls.create(
            twiml=f'<Response><Say language="{t_lang}">{speech}</Say></Response>',
            from_=TWILIO_PHONE,
            to=contact
        )
    except Exception as e:
        print(f"Error alerting {contact}: {e}")

def trigger_emergency(lat, lon, lang):
    try:
        child = get_latest_child()
        if not child:
            return "No child registered."

        name, age, clothes, last_loc, _ = child
        time_now = datetime.now().strftime("%d-%m-%Y | %I:%M %p")
        maps = f"https://www.google.com/maps?q={lat},{lon}"

        msg_body = (
            f"🚨 CHILD SAFETY ALERT 🚨\n"
            f"Name: {name}\nAge: {age}\nClothes: {clothes}\n"
            f"Last Location: {last_loc}\nGPS: {maps}\nTime: {time_now}"
        )

        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        
        if lang == "English":
            speech = f"Emergency alert. {name} has triggered SOS. Location sent."
            twilio_lang = "en-US"
        else:
            speech = f"आपातकालीन अलर्ट। {name} ने मदद के लिए संदेश भेजा है। स्थान भेज दिया गया है।"
            twilio_lang = "hi-IN"

        # Threading: Trigger all alerts at the same time
        threads = []
        for contact in EMERGENCY_CONTACTS:
            if "X" not in contact:
                t = threading.Thread(target=send_individual_alert, 
                                     args=(client, contact, msg_body, twilio_lang, speech))
                threads.append(t)
                t.start()

        # Wait for threads to finish to confirm the process started
        for t in threads:
            t.join()

        return True
    except Exception as e:
        return f"Twilio Error: {str(e)}"

# ================== UI ==================
st.title("🛡️ SafeGuard Child Safety AI")

tab1, tab2, tab3 = st.tabs([
    "👨‍👩‍👧 Parent Registration",
    "🆘 SOS Emergency",
    "🧠 AI Face Matching"
])

# ================== TAB 1: REGISTRATION ==================
with tab1:
    with st.form("register"):
        name = st.text_input("Child Name")
        age = st.number_input("Age", 0, 18)
        clothes = st.text_input("Clothing Color")
        last_loc = st.text_area("Location Where Child Was Last Seen")
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

# ================== TAB 2: SOS ==================
with tab2:
    st.warning("Pressing SOS will alert both emergency contacts simultaneously.")
    location = streamlit_geolocation()
    if st.button("🆘 TRIGGER SOS"):
        if location.get('latitude') and location.get('longitude'):
            with st.spinner("Sending simultaneous alerts..."):
                result = trigger_emergency(
                    location['latitude'],
                    location['longitude'],
                    voice_lang
                )
            if result is True:
                st.success("All Contacts Alerted Successfully")
                st.balloons()
            else:
                st.error(result)
        else:
            st.error("Please enable/allow location access to trigger SOS.")

# ================== TAB 3: FACE MATCHING ==================
with tab3:
    st.subheader("AI Face Detection & Matching")
    mode = st.radio("Choose Image Source", ["📷 Live Camera", "🖼️ Upload Image"])
    test_np = None

    if mode == "📷 Live Camera":
        cam_img = st.camera_input("Capture Image")
        if cam_img:
            test_np = np.array(Image.open(cam_img).convert("RGB"))

    if mode == "🖼️ Upload Image":
        upload_img = st.file_uploader("Upload Image", ["jpg", "png", "jpeg"])
        if upload_img:
            test_np = np.array(Image.open(upload_img).convert("RGB"))

    if test_np is not None:
        child = get_latest_child()
        if child:
            _, _, _, _, stored_path = child
            with st.spinner("Analyzing faces..."):
                matched, msg = match_faces(stored_path, test_np)

            if matched:
                st.success(f"✅ {msg}")
                st.balloons()
            else:
                st.error(f"❌ {msg}")
        else:
            st.warning("No registered child found.")