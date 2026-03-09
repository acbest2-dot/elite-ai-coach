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

# --- 1. INIZIALIZZAZIONE & CHIAVI ---
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app"

# Inizializziamo le variabili per evitare NameError
CLIENT_ID = st.secrets.get("STRAVA_CLIENT_ID") or os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = st.secrets.get("STRAVA_CLIENT_SECRET") or os.getenv("STRAVA_CLIENT_SECRET")
GEMINI_KEY = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. FUNZIONI TECNICHE ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    minutes = int(seconds_per_km // 60)
    seconds = int(seconds_per_km % 60)
    return f"{minutes}:{seconds:02d}"

def safe_calculate_tss(row, fc_min, fc_max):
    try:
        duration_min = row.get('moving_time', 0) / 60
        hr_avg = row.get('average_heartrate', 0)
        if hr_avg > 0 and fc_max > fc_min:
            intensity = (hr_avg - fc_min) / (fc_max - fc_min)
            return (duration_min * hr_avg * intensity) / (fc_max * 60) * 100
        return duration_min * 0.6
    except: return 0

def draw_map(encoded_polyline):
    if not encoded_polyline: return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=14)
        folium.PolyLine(points, color="#FF4B4B", weight=5).add_to(m)
        return m
    except: return None

# --- 3. GESTIONE SESSIONE ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"eta": 35, "peso": 75.0, "fc_min": 50, "fc_max": 190}

# OAuth Strava
query_params = st.query_params
if "code" in query_params and st.session_state.strava_token is None:
    res = requests.post('https://www.strava.com/oauth/token', 
                        data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 
                              'code': query_params["code"], 'grant_type': 'authorization_code'}).json()
    if 'access_token' in res:
        st.session_state.strava_token = res['access_token']
        st.query_params.clear()
        st.rerun()

# --- 4. APP PRINCIPALE ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        activities = r.json()
        df = pd.DataFrame(activities)
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # Calcoli Fitness
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: safe_calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')
        daily_tss = df.groupby(df['start_date'].dt.date)['tss'].sum()
        all_dates = pd.date_range(start=df['start_date'].min().date(), end=datetime.now().date(), freq='D')
        daily_full = daily_tss.reindex(all_dates.date, fill_value=0)
        ctl = daily_full.ewm(span=42).mean()
        atl = daily_full.ewm(span=7).mean()
        tsb = ctl - atl

        # Dati ultima attività (Sempre pronti per la chat)
        last_act = df.iloc[-1]
        d_km = last_act['distance'] / 1000
        p_min = format_pace(last_act['moving_time'] / d_km)

        with st.sidebar:
            st.title("Elite AI Settings")
            menu = st.radio("SEZIONE:", ["DASHBOARD", "CALENDARIO", "AI COACH", "PROFILO"])
            st.divider()
            ai_mode = st.radio("Cervello AI:", ["LIGHT", "PRO"])
            if st.button("Esci"):
                st.session_state.strava_token = None
                st.rerun()

        if menu == "DASHBOARD":
            st.header("📊 Performance")
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            c2.metric("Fatica (ATL)", f"{atl.iloc[-1]:.1f}")
            c3.metric("Forma (TSB)", f"{tsb.iloc[-1]:.1f}")
            st.area_chart(pd.DataFrame({'Fitness': ctl, 'Fatica': atl, 'Forma': tsb}))
            
            st.subheader(f"🏁 {last_act['name']}")
            m = draw_map(last_act.get('map', {}).get('summary_polyline'))
            if m: st_folium(m, width=700, height=350, key="map")

        elif menu == "CALENDARIO":
            events = [{"title": f"{a['type']} ({a['distance']/1000:.1f}k)", "start": a['start_date_local']} for a in activities]
            calendar(events=events)

        elif menu == "AI COACH":
            head_col, clear_col = st.columns([3, 1])
            with head_col: st.header(f"💬 Coach AI ({ai_mode})")
            with clear_col:
                if st.button("🗑️ Svuota Chat"):
                    st.session_state.messages = []
                    st.rerun()

            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Chiedi al coach..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                # Context Robusto
                context = f"Dati: {u['peso']}kg. Fitness: {ctl.iloc[-1]:.1f}. Ultima corsa: {d_km:.2f}km a {p_min}."
                
                # Nomi modelli aggiornati per evitare il 404
                m_name = "gemini-1.5-flash-latest" if ai_mode == "LIGHT" else "gemini-1.5-pro-latest"
                
                try:
                    model = genai.GenerativeModel(m_name)
                    # Forziamo l'uso del modello corretto senza prefisso "models/" manuale
                    response = model.generate_content(f"{context}\n\nDomanda: {prompt}").text
                except Exception as e:
                    response = f"⚠️ Errore AI: {str(e)}. Assicurati che la chiave sia valida."

                with st.chat_message("assistant"): st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

        elif menu == "PROFILO":
            st.header("👤 Profilo")
            with st.form("p"):
                u['peso'] = st.number_input("Peso (kg)", value=float(u['peso']))
                u['fc_max'] = st.number_input("FC Max", value=int(u['fc_max']))
                if st.form_submit_button("Salva"):
                    st.session_state.user_data = u
                    st.success("Dati aggiornati!")
else:
    st.title("🚀 Elite AI Performance Hub")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti con Strava", auth_url)
