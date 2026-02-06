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
# Using the credentials provided in your previous snippet
TWILIO_SID = "ACc9b9941c778de30e2ed7ba57f87cdfbc"
TWILIO_AUTH_TOKEN = "b524116dc4b14af314a5919594df9121"
TWILIO_PHONE = "+15075195618"

# Both numbers will receive SMS and Calls simultaneously
EMERGENCY_CONTACTS = [
    "+918130631551", 
    "+917678495189" # Ensure you replace this with your actual 2nd verified number
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

def send_individual_alert(contact, msg_body, t_lang, speech):
    """Refined parallel dispatch for SMS and Calling"""
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        
        # 1. DISPATCH SMS
        sms = client.messages.create(
            body=msg_body, 
            from_=TWILIO_PHONE, 
            to=contact
        )
        print(f"SMS sent to {contact}: {sms.sid}")
        
        # 2. DISPATCH CALL
        call = client.calls.create(
            twiml=f'<Response><Say language="{t_lang}">{speech}</Say></Response>',
            from_=TWILIO_PHONE,
            to=contact
        )
        print(f"Call initiated to {contact}: {call.sid}")
        
    except Exception as e:
        print(f"FAILED ALERT for {contact}: {str(e)}")

def trigger_emergency(lat, lon, lang):
    try:
        child = get_latest_child()
        if not child:
            return "No child registered."

        name, age, clothes, last_loc, _ = child
        time_now = datetime.now().strftime("%d-%m-%Y | %I:%M %p")
        # Standard Maps URL for mobile redirection
        maps_link = f"https://www.google.com/maps?q={lat},{lon}"

        msg_body = (
            f"🚨 CHILD SAFETY ALERT 🚨\n\n"
            f"Child: {name}\n"
            f"Age: {age}\n"
            f"Clothes: {clothes}\n"
            f"Last Seen: {last_loc}\n"
            f"Location: {maps_link}\n"
            f"Time: {time_now}"
        )

        if lang == "English":
            speech = f"Emergency alert. {name} has triggered SOS. Location details sent via SMS."
            twilio_lang = "en-US"
        else:
            speech = f"आपातकालीन अलर्ट। {name} ने मदद के लिए संदेश भेजा है। स्थान की जानकारी भेज दी गई है।"
            twilio_lang = "hi-IN"

        # Threaded logic for simultaneous delivery to BOTH numbers
        threads = []
        for contact in EMERGENCY_CONTACTS:
            if "X" not in contact:
                t = threading.Thread(
                    target=send_individual_alert, 
                    args=(contact, msg_body, twilio_lang, speech)
                )
                threads.append(t)
                t.start()

        for t in threads:
            t.join()

        return True
    except Exception as e:
        return f"System Error: {str(e)}"

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
        submit = st.form_submit_button("Register Child")

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
    st.warning("SOS will trigger parallel Calls and SMS to all linked contacts.")
    location = streamlit_geolocation()
    if st.button("🆘 TRIGGER SOS"):
        if location.get('latitude') and location.get('longitude'):
            with st.spinner("Dispatching Emergency Alerts..."):
                result = trigger_emergency(
                    location['latitude'],
                    location['longitude'],
                    voice_lang
                )
            if result is True:
                st.success("Alerts (Call + SMS) Sent to All Contacts!")
                st.balloons()
            else:
                st.error(result)
        else:
            st.error("Enable location access to use the SOS feature.")

# ================== TAB 3: FACE MATCHING ==================
with tab3:
    st.subheader("AI Face Detection & Matching")
    mode = st.radio("Source", ["📷 Live Camera", "🖼️ Upload Image"])
    test_np = None

    if mode == "📷 Live Camera":
        cam_img = st.camera_input("Scanner")
        if cam_img:
            test_np = np.array(Image.open(cam_img).convert("RGB"))

    if mode == "🖼️ Upload Image":
        upload_img = st.file_uploader("CCTV Image", ["jpg", "png", "jpeg"])
        if upload_img:
            test_np = np.array(Image.open(upload_img).convert("RGB"))

    if test_np is not None:
        child = get_latest_child()
        if child:
            _, _, _, _, stored_path = child
            with st.spinner("Analyzing..."):
                matched, msg = match_faces(stored_path, test_np)

            if matched:
                st.success(f"✅ {msg}")
                st.balloons()
            else:
                st.error(f"❌ {msg}")
        else:
            st.warning("Please register a child first.")