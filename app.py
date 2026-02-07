import streamlit as st
import sqlite3
import cv2
import numpy as np
import threading  # <--- NEW: Required for simultaneous alerts
from datetime import datetime
from twilio.rest import Client
from streamlit_geolocation import streamlit_geolocation

# ==================================================
# TWILIO CONFIGURATION
# ==================================================

TWILIO_SID = "ACa12e602647785572ebaf765659d26d23"
TWILIO_AUTH_TOKEN = "0e150a10a98b74ddc7d57e44fa3e01c6"

TWILIO_PHONE = "+14176076960"                  # Your Twilio SMS/Voice Number
TWILIO_WHATSAPP_SENDER = "whatsapp:+14155238886"  # Your Twilio WhatsApp Sandbox Number

# List of Contacts (Add both numbers here)
# NOTE: Ensure both numbers are Verified in Twilio Console if using a Trial Account.
EMERGENCY_CONTACTS = [
    "+918130631551", 
    "+917678495189"
]

DB_FILE = "child_safety.db"

FACE_CASCADE = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

st.set_page_config(page_title="SafeGuard AI", page_icon="🛡️", layout="centered")

# ==================================================
# CUSTOM CSS FOR BIG SOS BUTTON
# ==================================================
st.markdown("""
<style>
    div.stButton > button:first-child {
        background-color: #ff0000;
        color: white;
        height: 150px;
        width: 100%;
        border-radius: 20px;
        font-size: 40px;
        font-weight: bold;
        border: 4px solid #8b0000;
        box-shadow: 0px 4px 15px rgba(255,0,0,0.6);
        transition: 0.3s;
    }
    div.stButton > button:first-child:hover {
        background-color: #cc0000;
        border-color: #ffffff;
        transform: scale(1.02);
    }
    div.stButton > button:first-child:active {
        background-color: #8b0000;
        transform: scale(0.95);
    }
</style>
""", unsafe_allow_html=True)

# ==================================================
# DATABASE INIT
# ==================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS child (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, age INTEGER, clothing_color TEXT, 
            lost_location TEXT, photo BLOB, face_encoding BLOB, registered_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sos_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL, longitude REAL, time TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================================================
# FACE RECOGNITION HELPERS
# ==================================================
def extract_face(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0: return None
    x, y, w, h = faces[0]
    return cv2.resize(gray[y:y+h, x:x+w], (200, 200))

def compare_faces(f1, f2):
    if f1 is None or f2 is None: return False
    # Simple Mean Squared Error comparison
    err = np.sum((f1.astype("float") - f2.astype("float")) ** 2)
    err /= float(f1.shape[0] * f1.shape[1])
    return err < 4000  # Threshold for similarity

# ==================================================
# PARALLEL SOS ALERT SYSTEM
# ==================================================

def send_single_alert(contact, message, speech, twiml_lang):
    """
    Sends WhatsApp, SMS, and Call to a SINGLE contact.
    This function is designed to be run in a separate thread.
    """
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    
    # 1. WHATSAPP (Most Rich Media)
    try:
        client.messages.create(
            from_=TWILIO_WHATSAPP_SENDER,
            to=f"whatsapp:{contact}",
            body=message
        )
        print(f"✅ WhatsApp sent to {contact}")
    except Exception as e:
        print(f"❌ WhatsApp failed for {contact}: {e}")

    # 2. SMS (Backup)
    try:
        client.messages.create(
            from_=TWILIO_PHONE,
            to=contact,
            body=message
        )
        print(f"✅ SMS sent to {contact}")
    except Exception as e:
        print(f"❌ SMS failed for {contact}: {e}")

    # 3. VOICE CALL (Immediate Attention)
    try:
        client.calls.create(
            twiml=f'<Response><Say language="{twiml_lang}">{speech}</Say></Response>',
            from_=TWILIO_PHONE,
            to=contact
        )
        print(f"✅ Call initiated for {contact}")
    except Exception as e:
        print(f"❌ Call failed for {contact}: {e}")


def trigger_sos_broadcast(lat, lon, lang):
    """
    Spawns threads to alert ALL contacts simultaneously.
    """
    # 1. Prepare Data
    now = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    
    # Fetch Child Info if available
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    child = c.execute("SELECT name, age, clothing_color FROM child ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    if child:
        c_name, c_age, c_cloth = child
        details = f"\nName: {c_name}\nAge: {c_age}\nClothes: {c_cloth}"
    else:
        c_name = "Unknown"
        details = "\n(No child registered locally)"

    # 2. Prepare Message & Speech
    message_body = (
        f"🚨 *SOS EMERGENCY ALERT* 🚨\n\n"
        f"Child Discovered / Alert Triggered!{details}\n\n"
        f"📍 *Location:* {maps_link}\n"
        f"⏰ *Time:* {now}"
    )

    if lang == "English":
        speech_text = f"Emergency Alert! {c_name} has triggered the SOS system. Location details sent to your WhatsApp."
        twiml_lang = "en-US"
    else:
        speech_text = f"Aapaatkaaleen Alert. {c_name} ne SOS system dabaya hai. Location bhej di gayi hai."
        twiml_lang = "hi-IN"

    # 3. THREADING: Fire alerts to everyone at once
    threads = []
    for contact in EMERGENCY_CONTACTS:
        t = threading.Thread(target=send_single_alert, args=(contact, message_body, speech_text, twiml_lang))
        threads.append(t)
        t.start()

    # 4. Log to DB
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO sos_log(latitude, longitude, time) VALUES (?,?,?)", (lat, lon, now))
    conn.commit()
    conn.close()

    # Wait for all threads to ensure delivery before returning UI control
    for t in threads:
        t.join()

# ==================================================
# MAIN UI
# ==================================================

st.title("🛡️ SafeGuard AI")

tab1, tab2, tab3 = st.tabs(["📝 Register", "📸 Verify", "🚨 SOS"])

# --- TAB 1: REGISTER ---
with tab1:
    st.subheader("Parent Registration")
    with st.form("reg_form"):
        name = st.text_input("Name")
        age = st.number_input("Age", 1, 18)
        cloth = st.text_input("Clothing Color")
        loc = st.text_input("Last Seen Location")
        photo = st.file_uploader("Photo", type=["jpg", "png"])
        if st.form_submit_button("Save Profile"):
            if photo and name:
                img_bytes = photo.read()
                img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
                face = extract_face(img)
                if face is not None:
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute("INSERT INTO child (name, age, clothing_color, lost_location, photo, face_encoding, registered_at) VALUES (?,?,?,?,?,?,?)",
                                 (name, age, cloth, loc, img_bytes, face.tobytes(), datetime.now().strftime("%Y-%m-%d %H:%M")))
                    conn.commit()
                    conn.close()
                    st.success("Child Registered!")
                else:
                    st.error("No face detected in photo.")

# --- TAB 2: VERIFY ---
with tab2:
    st.subheader("Face Search")
    verify_mode = st.radio("Input Source", ["Live Camera", "Upload Image"])
    
    # Get stored face
    conn = sqlite3.connect(DB_FILE)
    res = conn.execute("SELECT face_encoding, name FROM child ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    
    target_face = None
    if res:
        target_face = np.frombuffer(res[0], dtype=np.uint8).reshape((200, 200))
        st.info(f"Searching for: {res[1]}")

    captured_img = None
    if verify_mode == "Live Camera":
        cam = st.camera_input("Scan Face")
        if cam: captured_img = cv2.imdecode(np.frombuffer(cam.read(), np.uint8), cv2.IMREAD_COLOR)
    else:
        upl = st.file_uploader("Upload Image", type=["jpg","png"])
        if upl: captured_img = cv2.imdecode(np.frombuffer(upl.read(), np.uint8), cv2.IMREAD_COLOR)

    if captured_img is not None and target_face is not None:
        curr_face = extract_face(captured_img)
        if curr_face is not None:
            if compare_faces(target_face, curr_face):
                st.success("MATCH CONFIRMED! ✅")
            else:
                st.error("NO MATCH FOUND ❌")
        else:
            st.warning("No face detected in input.")

# --- TAB 3: SOS BROADCAST ---
with tab3:
    st.header("Emergency Broadcast")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.write("Clicking SOS will alert **2 contacts** via **WhatsApp, SMS, and Voice Call** instantly.")
    with col2:
        lang_choice = st.selectbox("Language", ["English", "Hindi"])

    loc = streamlit_geolocation()

    st.write("") # Spacer
    if st.button("🆘 TRIGGER SOS"):
        if loc.get("latitude") is not None:
            with st.spinner("Broadcasting Alerts..."):
                trigger_sos_broadcast(loc['latitude'], loc['longitude'], lang_choice)
            st.success("✅ SOS Broadcast Complete!")
            st.balloons()
        else:
            st.error("⚠️ Waiting for Location... Allow GPS permission.")