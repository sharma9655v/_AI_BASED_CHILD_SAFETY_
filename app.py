import streamlit as st
import sqlite3
import cv2
import numpy as np
import threading
import time
from datetime import datetime
from twilio.rest import Client
from streamlit_geolocation import streamlit_geolocation

# ==================================================
# 1. CONFIGURATION
# ==================================================

TWILIO_SID = "ACc9b9941c778de30e2ed7ba57f87cdfbc"
TWILIO_AUTH_TOKEN = "2b2cf2200be3a515c496ffd9137d63c4"

# SMS & Call Number (Your purchased number)
TWILIO_PHONE_NUMBER = "+15075195618"           

# WhatsApp Sandbox Number (ALWAYS use this for WhatsApp)
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886" 

# Emergency Contacts (Both will receive WhatsApp + Call)
EMERGENCY_CONTACTS = [
    "+918130631551", 
    "+917678495189" 
]

DB_FILE = "child_safety.db"

# Load Face Cascade
try:
    FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except:
    st.error("Error loading Haarcascade XML. Please check OpenCV installation.")

st.set_page_config(page_title="SafeGuard AI", page_icon="🛡️", layout="centered")

# ==================================================
# 2. DATABASE SETUP
# ==================================================
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
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
            latitude REAL, longitude REAL, time TEXT, status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ==================================================
# 3. HELPER FUNCTIONS
# ==================================================

def extract_face(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = FACE_CASCADE.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0: return None
    x, y, w, h = faces[0]
    return cv2.resize(gray[y:y+h, x:x+w], (200, 200))

def compare_faces(f1, f2):
    if f1 is None or f2 is None: return False
    err = np.sum((f1.astype("float") - f2.astype("float")) ** 2)
    err /= float(f1.shape[0] * f1.shape[1])
    return err < 4000 

def send_alert_thread(contact, msg_body, speech, lang_code, log_container):
    """
    Sends WhatsApp, SMS, and Call to ONE contact.
    """
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    status_log = {}

    # --- 1. WHATSAPP (Sandbox Number) ---
    try:
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER, 
            body=msg_body,
            to=f"whatsapp:{contact}"
        )
        status_log["WhatsApp"] = "✅ Sent"
    except Exception as e:
        status_log["WhatsApp"] = f"❌ Failed: {str(e)}"

    # --- 2. SMS (Your Number) ---
    try:
        message = client.messages.create(
            from_=TWILIO_PHONE_NUMBER,
            body=msg_body,
            to=contact
        )
        status_log["SMS"] = "✅ Sent"
    except Exception as e:
        status_log["SMS"] = f"❌ Failed: {str(e)}"

    # --- 3. VOICE CALL (Your Number) ---
    try:
        call = client.calls.create(
            twiml=f'<Response><Say language="{lang_code}">{speech}</Say></Response>',
            from_=TWILIO_PHONE_NUMBER,
            to=contact
        )
        status_log["Call"] = "✅ Initiated"
    except Exception as e:
        status_log["Call"] = f"❌ Failed: {str(e)}"
    
    # Store log for UI display
    log_container[contact] = status_log

def trigger_sos(lat, lon, language_choice):
    timestamp = datetime.now().strftime("%d-%m-%Y %I:%M %p")
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    
    conn = sqlite3.connect(DB_FILE)
    child_data = conn.execute("SELECT name, age, clothing_color FROM child ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    if child_data:
        c_name, c_age, c_clothes = child_data
        details = f"Name: {c_name}\nAge: {c_age}\nClothes: {c_clothes}"
    else:
        c_name = "Unknown Child"
        details = "No registered details found."

    msg_body = (
        f"🚨 *SOS EMERGENCY* 🚨\n\n"
        f"Child Status: MISSING / DANGER\n"
        f"{details}\n\n"
        f"📍 *Live Location:* {maps_link}\n"
        f"⏰ *Time:* {timestamp}"
    )

    if language_choice == "English":
        speech = f"Emergency Alert! {c_name} has triggered the SOS. Check WhatsApp for location."
        lang_code = "en-US"
    else:
        speech = f"Aapaatkaaleen Alert. {c_name} ne SOS dabaya hai. Location WhatsApp par bheji gayi hai."
        lang_code = "hi-IN"

    threads = []
    log_results = {} 

    # LOOP: This ensures BOTH numbers get the alerts
    for contact in EMERGENCY_CONTACTS:
        t = threading.Thread(target=send_alert_thread, args=(contact, msg_body, speech, lang_code, log_results))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT INTO sos_log(latitude, longitude, time, status) VALUES (?,?,?,?)", 
                 (lat, lon, timestamp, "Triggered"))
    conn.commit()
    conn.close()
    
    return log_results

# ==================================================
# 4. STREAMLIT UI
# ==================================================

st.title("🛡️ SafeGuard AI")

tab1, tab2, tab3 = st.tabs(["📝 Register", "🔍 AI Face Match", "🆘 Emergency SOS"])

# --- TAB 1: REGISTRATION ---
with tab1:
    st.header("Register Child")
    with st.form("reg_form"):
        name = st.text_input("Child Name")
        age = st.number_input("Age", 1, 18)
        cloth = st.text_input("Clothing Color")
        loc = st.text_input("Last Known Location")
        photo = st.file_uploader("Upload Photo", type=["jpg", "png", "jpeg"])
        
        if st.form_submit_button("Save Profile"):
            if photo and name:
                file_bytes = np.frombuffer(photo.read(), np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                face = extract_face(img)
                
                if face is not None:
                    conn = sqlite3.connect(DB_FILE)
                    conn.execute("""
                        INSERT INTO child (name, age, clothing_color, lost_location, photo, face_encoding, registered_at) 
                        VALUES (?,?,?,?,?,?,?)
                    """, (name, age, cloth, loc, file_bytes.tobytes(), face.tobytes(), datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Registered {name} successfully!")
                else:
                    st.error("❌ No face detected.")
            else:
                st.warning("⚠️ Name and Photo are required.")

# --- TAB 2: AI FACE MATCH ---
with tab2:
    st.header("Search & Verify")
    mode = st.radio("Input Mode", ["Live Camera", "Upload Image"])
    
    conn = sqlite3.connect(DB_FILE)
    record = conn.execute("SELECT face_encoding, name FROM child ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    
    target_face = None
    if record:
        target_face = np.frombuffer(record[0], dtype=np.uint8).reshape((200, 200))
        st.info(f"🔎 Searching for: **{record[1]}**")

    input_img = None
    if mode == "Live Camera":
        cam = st.camera_input("Scan Face")
        if cam: input_img = cv2.imdecode(np.frombuffer(cam.read(), np.uint8), cv2.IMREAD_COLOR)
    else:
        upl = st.file_uploader("Upload Image to Check", type=["jpg", "png"])
        if upl: input_img = cv2.imdecode(np.frombuffer(upl.read(), np.uint8), cv2.IMREAD_COLOR)

    if input_img is not None and target_face is not None:
        curr_face = extract_face(input_img)
        if curr_face is not None:
            match = compare_faces(target_face, curr_face)
            if match:
                st.success("✅ **MATCH CONFIRMED! Child Identified.**")
                st.balloons()
            else:
                st.error("❌ **NO MATCH FOUND.**")
        else:
            st.warning("⚠️ No face detected.")

# --- TAB 3: SOS SYSTEM ---
with tab3:
    st.header("Emergency Broadcast System")
    st.markdown("""
    **Triggering SOS will:**
    1. Send **WhatsApp** Location & Details to 2 Contacts.
    2. Send **SMS** Backup to 2 Contacts.
    3. Make a **Voice Call** to 2 Contacts simultaneously.
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        sos_lang = st.selectbox("Voice Alert Language", ["English", "Hindi"])
    
    st.markdown("""
    <style>
    div.stButton > button:first-child {
        background-color: #d32f2f; color: white; height: 120px; width: 100%;
        font-size: 30px; border-radius: 15px; font-weight: bold;
    }
    div.stButton > button:first-child:hover {
        background-color: #b71c1c; border: 2px solid white;
    }
    </style>
    """, unsafe_allow_html=True)
    
    location = streamlit_geolocation()
    
    st.write("") 
    if st.button("🆘 ACTIVATE SOS"):
        if location.get("latitude"):
            with st.spinner("Dispatching Alerts..."):
                logs = trigger_sos(location["latitude"], location["longitude"], sos_lang)
                time.sleep(1) 
            
            st.success("✅ SOS Triggered!")
            st.write("### 📊 Delivery Report (Debug Log)")
            st.json(logs)
            st.balloons()
        else:
            st.error("⚠️ GPS Location not found.")