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
from datetime import datetime, timedelta

# --- 1. CONFIGURAZIONE CHIAVI & URL FISSO ---
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app/"

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
    model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. STILE LIGHT MODE & CUSTOM CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .stMetric { background-color: #F8F9FA; padding: 15px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    .main-card { background: #f8f9fa; border-radius: 15px; padding: 20px; border: 1px solid #dee2e6; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI TECNICHE DI CALCOLO ---
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
        return duration_min * 0.6  # Stima basata su tempo se manca FC
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
    # Dati di default (verranno sovrascritti nel profilo)
    st.session_state.user_data = {"eta": 35, "peso": 75.0, "altezza": 180, "fc_min": 50, "fc_max": 190}

# Gestione Redirect Strava
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

# --- 5. INTERFACCIA APP ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        df = pd.DataFrame(r.json())
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # Calcolo TSS e Carichi
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: safe_calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')
        
        daily_tss = df.groupby(df['start_date'].dt.date)['tss'].sum()
        all_dates = pd.date_range(start=df['start_date'].min().date(), end=datetime.now().date(), freq='D')
        daily_full = daily_tss.reindex(all_dates.date, fill_value=0)
        ctl = daily_full.ewm(span=42).mean()
        atl = daily_full.ewm(span=7).mean()
        tsb = ctl - atl

        # Sidebar
        with st.sidebar:
            st.title("🏆 Elite AI Coach")
            menu = st.radio("SISTEMA", ["DASHBOARD", "CALENDARIO", "AI CHAT", "PROFILO"])
            if st.button("🚪 Esci"):
                st.session_state.strava_token = None
                st.rerun()

        # --- SEZIONE PROFILO ---
        if menu == "PROFILO":
            st.header("👤 Profilo Atleta")
            with st.form("profile_settings"):
                u['eta'] = st.number_input("Età", value=u['eta'])
                u['peso'] = st.number_input("Peso (kg)", value=float(u['peso']))
                u['fc_min'] = st.number_input("FC Minima (Riposo)", value=u['fc_min'])
                u['fc_max'] = st.number_input("FC Massima", value=u['fc_max'])
                if st.form_submit_button("Salva Impostazioni"):
                    st.session_state.user_data = u
                    st.success("Dati aggiornati e carichi ricalcolati!")
                    st.rerun()

        # --- SEZIONE DASHBOARD ---
        elif menu == "DASHBOARD":
            st.header("📊 Performance Metrics")
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            c2.metric("Fatica (ATL)", f"{atl.iloc[-1]:.1f}")
            c3.metric("Forma (TSB)", f"{tsb.iloc[-1]:.1f}")

            st.area_chart(pd.DataFrame({'Fitness': ctl, 'Fatica': atl, 'Forma': tsb}))

            st.divider()
            last = df.iloc[-1]
            st.subheader(f"🏁 Ultima Attività: {last['name']}")
            
            col_map, col_info = st.columns([2, 1])
            with col_info:
                dist_km = last['distance']/1000
                st.write(f"**Tipo:** {last['type']}")
                st.write(f"**Distanza:** {dist_km:.2f} km")
                if last['type'] == 'Swim':
                    st.write(f"**Passo:** {calculate_swimming_pace(last['moving_time'], last['distance'])} /100m")
                else:
                    st.write(f"**Passo:** {format_pace(last['moving_time']/dist_km)} /km")
                
                if st.button("🤖 Analisi AI"):
                    prompt = f"Atleta {u}. Sessione: {last['type']}, {dist_km:.1f}km. Fornisci feedback tecnico."
                    st.info(model.generate_content(prompt).text)

            with col_map:
                m_last = draw_map(last.get('map', {}).get('summary_polyline'))
                if m_last: st_folium(m_last, width=700, height=350, key="main_map")

        # --- SEZIONE CALENDARIO ---
        elif menu == "CALENDARIO":
            st.header("📅 Diario Allenamenti")
            events = [{"title": f"{row['type']} - TSS: {row['tss']:.0f}", "start": row['start_date'].isoformat()} for _, row in df.iterrows()]
            calendar(events=events, options={"initialView": "dayGridMonth"})

        # --- SEZIONE AI CHAT ---
        elif menu == "AI CHAT":
            st.header("💬 Chiedi al tuo Coach")
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Come dovrei allenarmi oggi?"):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                context = f"Dati atleta: {u}. Fitness attuale (CTL): {ctl.iloc[-1]:.1f}. Forma (TSB): {tsb.iloc[-1]:.1f}."
                response = model.generate_content(context + "\n" + prompt).text
                
                with st.chat_message("assistant"): st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

    else: st.error("Errore nel recupero dati da Strava.")
else:
    st.title("🚀 Elite AI Performance Hub")
    st.write("Accedi per analizzare i tuoi dati Strava con l'intelligenza artificiale.")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti il tuo Strava", auth_url)
