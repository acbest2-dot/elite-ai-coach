import streamlit as st
import requests
import pandas as pd
import numpy as np
import os
import google.generativeai as genai
import polyline
import folium
from streamlit_folium import st_folium
from streamlit_calendar import calendar
from datetime import datetime

# --- 1. CONFIGURAZIONE CHIAVI & URL ---
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app"

try:
    CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
    GEMINI_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
    CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
    GEMINI_KEY = os.getenv("GOOGLE_API_KEY")

# Configurazione AI sicura
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. STILE & MODALITÀ ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .stMetric { background-color: #F8F9FA; padding: 15px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI TECNICHE ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    minutes = int(seconds_per_km // 60)
    seconds = int(seconds_per_km % 60)
    return f"{minutes}:{seconds:02d}"

def get_ai_response(model_type, prompt, context=""):
    try:
        # Seleziona il modello in base alla modalità
        model_name = 'gemini-1.5-flash' if model_type == "LIGHT" else 'gemini-1.5-pro'
        model = genai.GenerativeModel(model_name)
        full_prompt = f"{context}\n\nUser Question: {prompt}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Errore AI ({model_type}): Modello non disponibile o chiave non valida. Dettaglio: {str(e)}"

# --- 4. LOGIN & SESSION STATE ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []

query_params = st.query_params
if "code" in query_params and st.session_state.strava_token is None:
    code = query_params["code"]
    res = requests.post('https://www.strava.com/oauth/token', 
                        data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 
                              'code': code, 'grant_type': 'authorization_code'}).json()
    if 'access_token' in res:
        st.session_state.strava_token = res['access_token']
        st.query_params.clear()
        st.rerun()

# --- 5. INTERFACCIA ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=10", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        activities = r.json()
        df = pd.DataFrame(activities)
        
        with st.sidebar:
            st.title("Settings AI")
            ai_mode = st.radio("Seleziona Modalità AI:", ["LIGHT", "PRO"], help="LIGHT è veloce, PRO è più profonda.")
            if st.button("Logout"):
                st.session_state.strava_token = None
                st.rerun()

        st.title("🏆 Dashboard Elite AI")
        
        tab1, tab2, tab3 = st.tabs(["Ultima Attività", "Calendario", "AI Coach Chat"])
        
        with tab1:
            if not df.empty:
                last = df.iloc[0]
                dist = last['distance']/1000
                st.subheader(f"Sessione: {last['name']}")
                c1, c2, c3 = st.columns(3)
                c1.metric("Distanza", f"{dist:.2f} km")
                c2.metric("Passo", format_pace(last['moving_time']/dist))
                c3.metric("Dislivello", f"{last['total_elevation_gain']} m")
        
        with tab2:
            events = [{"title": a['name'], "start": a['start_date_local']} for a in activities]
            calendar(events=events)

        with tab3:
            st.subheader(f"Coach AI ({ai_mode} Mode)")
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if user_input := st.chat_input("Chiedi al coach..."):
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"): st.markdown(user_input)
                
                # Genera contesto per l'AI
                context = f"L'atleta ha appena corso {dist:.2f}km a {format_pace(last['moving_time']/dist)} min/km."
                
                with st.chat_message("assistant"):
                    with st.spinner("Il coach sta riflettendo..."):
                        response = get_ai_response(ai_mode, user_input, context)
                        st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

else:
    st.title("🚀 Elite AI Performance Hub")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti il tuo Strava", auth_url)
