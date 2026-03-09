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

# --- 1. CONFIGURAZIONE CHIAVI & URL FISSO ---
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app"

try:
    CLIENT_ID = st.secrets["STRAVA_CLIENT_ID"]
    CLIENT_SECRET = st.secrets["STRAVA_CLIENT_SECRET"]
    GEMINI_KEY = st.secrets["GOOGLE_API_KEY"]
except:
    CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
    CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
    GEMINI_KEY = os.getenv("GOOGLE_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. STILE & CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .stMetric { background-color: #F8F9FA; padding: 15px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    .main-card { background: #f8f9fa; border-radius: 15px; padding: 20px; border: 1px solid #dee2e6; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI TECNICHE (PACE, TSS, MAPS) ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    minutes = int(seconds_per_km // 60)
    seconds = int(seconds_per_km % 60)
    return f"{minutes}:{seconds:02d}"

def calculate_swimming_pace(seconds, distance_meters):
    if distance_meters <= 0: return "0:00"
    pace_100m = (seconds / distance_meters) * 100
    minutes = int(pace_100m // 60)
    seconds = int(pace_100m % 60)
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
        folium.PolyLine(points, color="#FF4B4B", weight=5, opacity=0.8).add_to(m)
        return m
    except: return None

# --- 4. SESSION STATE & LOGIN ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"eta": 35, "peso": 75.0, "altezza": 180, "fc_min": 50, "fc_max": 190}

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

# --- 5. INTERFACCIA PRINCIPALE ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        df = pd.DataFrame(r.json())
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # Calcolo Performance (CTL/ATL/TSB)
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: safe_calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')
        daily_tss = df.groupby(df['start_date'].dt.date)['tss'].sum()
        all_dates = pd.date_range(start=df['start_date'].min().date(), end=datetime.now().date(), freq='D')
        daily_full = daily_tss.reindex(all_dates.date, fill_value=0)
        ctl = daily_full.ewm(span=42).mean()
        atl = daily_full.ewm(span=7).mean()
        tsb = ctl - atl

        with st.sidebar:
            st.title("Elite AI Coach")
            menu = st.radio("SISTEMA", ["DASHBOARD", "CALENDARIO", "AI COACH", "PROFILO"])
            if menu == "AI COACH":
                ai_mode = st.radio("Modalità AI:", ["LIGHT", "PRO"])
            if st.button("Logout"):
                st.session_state.strava_token = None
                st.rerun()

        # SEZIONE DASHBOARD
        if menu == "DASHBOARD":
            st.header("📊 Performance Metrics")
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            c2.metric("Fatica (ATL)", f"{atl.iloc[-1]:.1f}")
            c3.metric("Forma (TSB)", f"{tsb.iloc[-1]:.1f}")
            
            st.area_chart(pd.DataFrame({'Fitness': ctl, 'Fatica': atl, 'Forma': tsb}))
            
            st.divider()
            if not df.empty:
                last = df.iloc[-1]
                dist_km = last['distance']/1000
                st.subheader(f"🏁 Ultima Attività: {last['name']}")
                col_map, col_info = st.columns([2, 1])
                with col_info:
                    st.write(f"**Tipo:** {last['type']}")
                    st.write(f"**Distanza:** {dist_km:.2f} km")
                    st.write(f"**TSS:** {last['tss']:.1f}")
                with col_map:
                    m = draw_map(last.get('map', {}).get('summary_polyline'))
                    if m: st_folium(m, width=700, height=350, key="main_map")

        # SEZIONE CALENDARIO
        elif menu == "CALENDARIO":
            events = [{"title": f"{row['type']} - TSS: {row['tss']:.0f}", "start": row['start_date'].isoformat()} for _, row in df.iterrows()]
            calendar(events=events)

        # SEZIONE AI COACH (CON LIGHT/PRO)
        elif menu == "AI COACH":
            st.header(f"💬 Coach AI - Modalità {ai_mode}")
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if user_input := st.chat_input("Chiedi analisi o consigli..."):
                st.session_state.messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"): st.markdown(user_input)
                
                # Selezione modello e generazione
                m_name = 'gemini-1.5-flash' if ai_mode == "LIGHT" else 'gemini-1.5-pro'
                try:
                    model = genai.GenerativeModel(m_name)
                    context = f"Dati atleta: {u}. Fitness (CTL): {ctl.iloc[-1]:.1f}. Ultima sessione: {dist_km:.1f}km."
                    response = model.generate_content(f"{context}\n\nDomanda: {user_input}").text
                except Exception as e:
                    response = f"⚠️ Errore con {m_name}. Prova a cambiare modalità in LIGHT. Errore: {str(e)}"

                with st.chat_message("assistant"): st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

        # SEZIONE PROFILO
        elif menu == "PROFILO":
            st.header("👤 Impostazioni Atleta")
            with st.form("p_form"):
                u['peso'] = st.number_input("Peso (kg)", value=float(u['peso']))
                u['fc_min'] = st.number_input("FC Riposo", value=u['fc_min'])
                u['fc_max'] = st.number_input("FC Max", value=u['fc_max'])
                if st.form_submit_button("Salva"):
                    st.session_state.user_data = u
                    st.success("Profilo aggiornato!")

else:
    st.title("🚀 Elite AI Performance Hub")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti con Strava", auth_url)
