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

def get_secret(key):
    return st.secrets.get(key) or os.getenv(key)

CLIENT_ID = get_secret("STRAVA_CLIENT_ID")
CLIENT_SECRET = get_secret("STRAVA_CLIENT_SECRET")
GEMINI_KEY = get_secret("GOOGLE_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. FUNZIONI TECNICHE ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    return f"{int(seconds_per_km // 60)}:{int(seconds_per_km % 60):02d}"

def safe_calculate_tss(row, fc_min, fc_max):
    try:
        duration_min = row.get('moving_time', 0) / 60
        hr_avg = row.get('average_heartrate', 0)
        if hr_avg > 0 and fc_max > fc_min:
            intensity = (hr_avg - fc_min) / (fc_max - fc_min)
            return (duration_min * hr_avg * intensity) / (fc_max * 60) * 100
        return duration_min * 0.5
    except: return 0

# --- 3. SESSION STATE ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"peso": 75.0, "fc_min": 50, "fc_max": 190}

# Gestione OAuth Strava
if "code" in st.query_params and st.session_state.strava_token is None:
    res = requests.post('https://www.strava.com/oauth/token', 
                        data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 
                              'code': st.query_params["code"], 'grant_type': 'authorization_code'}).json()
    if 'access_token' in res:
        st.session_state.strava_token = res['access_token']
        st.rerun()

# --- 4. LOGICA APPLICATIVA ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        df = pd.DataFrame(r.json())
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # Calcoli Fitness
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: safe_calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')
        ctl = df['tss'].ewm(span=42).mean()
        tsb = ctl - df['tss'].ewm(span=7).mean()

        # Variabili per la chat
        last_act = df.iloc[-1]
        dist_km = last_act['distance'] / 1000
        pace_str = format_pace(last_act['moving_time'] / dist_km)

        with st.sidebar:
            st.title("Elite Menu")
            menu = st.radio("VAI A:", ["DASHBOARD", "CALENDARIO", "AI COACH", "PROFILO"])
            st.divider()
            
            # --- AUTO-DISCOVERY DEI MODELLI ---
            st.write("🧠 **Status AI**")
            available_models = []
            try:
                # Chiede a Google quali modelli esistono davvero per questa chiave
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
            except Exception as e:
                st.error("Errore API Key!")

            if available_models:
                # Pre-seleziona un modello valido (es. cerca flash)
                default_idx = 0
                for i, name in enumerate(available_models):
                    if "flash" in name:
                        default_idx = i
                        break
                ai_model_name = st.selectbox("Modello Attivo:", available_models, index=default_idx)
            else:
                st.warning("Nessun modello trovato.")
                ai_model_name = None

            if st.button("Logout"):
                st.session_state.strava_token = None
                st.rerun()

        if menu == "DASHBOARD":
            st.header("📊 Performance")
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            c2.metric("Forma (TSB)", f"{tsb.iloc[-1]:.1f}")
            c3.metric("Ultima", f"{dist_km:.1f} km")
            st.area_chart(pd.DataFrame({'Fitness': ctl, 'Forma': tsb}))

        elif menu == "AI COACH":
            col_h, col_b = st.columns([3, 1])
            col_h.header("💬 Elite Coach")
            if col_b.button("🗑️ Pulisci Chat"):
                st.session_state.messages = []
                st.rerun()

            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Come sto andando?"):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                context = f"Atleta {u['peso']}kg. CTL {ctl.iloc[-1]:.1f}. Ultima corsa {dist_km:.2f}km a {pace_str}."
                
                if ai_model_name:
                    try:
                        # Ora usiamo un nome che siamo CERTI esista
                        model = genai.GenerativeModel(ai_model_name)
                        response = model.generate_content(f"{context}\n\nDomanda: {prompt}").text
                    except Exception as e:
                        response = f"⚠️ Errore di connessione col modello {ai_model_name}: {str(e)}"
                else:
                    response = "⚠️ Nessun modello selezionato o API Key non valida."

                with st.chat_message("assistant"): st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

        elif menu == "PROFILO":
            st.header("👤 Impostazioni")
            with st.form("p"):
                u['peso'] = st.number_input("Peso (kg)", value=float(u['peso']))
                u['fc_min'] = st.number_input("FC Riposo", value=int(u['fc_min']))
                u['fc_max'] = st.number_input("FC Max", value=int(u['fc_max']))
                if st.form_submit_button("Salva"):
                    st.session_state.user_data = u
                    st.success("Dati aggiornati!")
else:
    st.title("🚀 Elite AI Performance Hub")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti Strava", auth_url)
