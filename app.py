import streamlit as st
import requests
import pandas as pd
import numpy as np
import os
import google.generativeai as genai
from dotenv import load_dotenv
import polyline
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta

# --- 1. CONFIGURAZIONE CHIAVI (Locali o Cloud) ---
load_dotenv()
# Se sei su Streamlit Cloud, userà st.secrets, altrimenti os.getenv
CLIENT_ID = st.secrets.get("STRAVA_CLIENT_ID") or os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = st.secrets.get("STRAVA_CLIENT_SECRET") or os.getenv("STRAVA_CLIENT_SECRET")
GEMINI_KEY = st.secrets.get("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Determina URL di reindirizzamento
if "streamlit.app" in st.get_option("browser.serverAddress") or "share.streamlit.io" in st.get_option("browser.serverAddress"):
    # Sostituisci con il tuo URL reale dopo il primo deploy
    REDIRECT_URI = "https://acbest2-dot-elite-ai-coach.streamlit.app"
else:
    REDIRECT_URI = 'http://localhost:8501'

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]

st.set_page_config(page_title="Elite AI Coach", page_icon="🏃‍♂️", layout="wide")

# --- 2. STILE LIGHT MODE ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; color: #31333F; }
    .stMetric { background-color: #F0F2F6; padding: 15px; border-radius: 10px; border-left: 5px solid #FF4B4B; }
    .main-card { background: #f8f9fa; border-radius: 15px; padding: 25px; border: 1px solid #dee2e6; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI TECNICHE ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    minutes = int(seconds_per_km // 60)
    seconds = int(seconds_per_km % 60)
    return f"{minutes}:{seconds:02d}"

def calculate_swimming_pace(seconds, distance_meters):
    if distance_meters <= 0: return "0:00"
    pace_100m = (seconds / distance_meters) * 100
    return format_pace(pace_100m)

def safe_calculate_tss(row, fc_min, fc_max):
    try:
        duration_min = row.get('moving_time', 0) / 60
        hr_avg = row.get('average_heartrate', 0)
        if hr_avg > 0 and fc_max > fc_min:
            intensity = (hr_avg - fc_min) / (fc_max - fc_min)
            return (duration_min * hr_avg * intensity) / (fc_max * 60) * 100
        return duration_min * 0.5
    except: return 0

def draw_map(encoded_polyline):
    if not encoded_polyline: return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=14, tiles="OpenStreetMap")
        folium.PolyLine(points, color="#FF4B4B", weight=5, opacity=0.8).add_to(m)
        return m
    except: return None

# --- 4. SESSION STATE & AUTH ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"eta": 35, "peso": 75.0, "altezza": 180, "fc_min": 50, "fc_max": 190}

# Gestione Token Strava (Anti-Loop)
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
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: safe_calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')

        # Calcoli Performance
        daily_tss = df.groupby(df['start_date'].dt.date)['tss'].sum()
        all_dates = pd.date_range(start=df['start_date'].min().date(), end=datetime.now().date(), freq='D')
        daily_full = daily_tss.reindex(all_dates.date, fill_value=0)
        ctl = daily_full.ewm(span=42).mean()
        atl = daily_full.ewm(span=7).mean()
        tsb = ctl - atl
        curr_acwr = atl.iloc[-1] / ctl.iloc[-1] if ctl.iloc[-1] > 0 else 0

        # Sidebar Navigazione
        with st.sidebar:
            st.title("🏆 Elite AI")
            model_choice = st.selectbox("Cervello AI", ["⚡ Gemini Flash", "🧠 Gemini Pro"])
            target_model_name = '1.5-pro' if "Pro" in model_choice else '1.5-flash'
            target_model = next((m for m in available_models if target_model_name in m), available_models[0])
            model = genai.GenerativeModel(target_model)
            
            st.divider()
            menu = st.radio("SISTEMA", ["DASHBOARD", "CALENDARIO", "CHAT COACH", "PROFILO & SETTINGS"])
            if st.button("🚪 Logout"):
                st.session_state.strava_token = None
                st.rerun()

        # --- A. PROFILO & SETTINGS ---
        if menu == "PROFILO & SETTINGS":
            st.title("👤 Impostazioni Atleta")
            with st.form("profile_form"):
                c1, c2 = st.columns(2)
                with c1:
                    u['eta'] = st.number_input("Età", value=u['eta'])
                    u['peso'] = st.number_input("Peso (kg)", value=u['peso'])
                    u['altezza'] = st.number_input("Altezza (cm)", value=u['altezza'])
                with c2:
                    u['fc_min'] = st.number_input("FC Riposo", value=u['fc_min'])
                    u['fc_max'] = st.number_input("FC Massima", value=u['fc_max'])
                if st.form_submit_button("Salva e Ricalcola"):
                    st.session_state.user_data = u
                    st.success("Dati aggiornati!")
                    st.rerun()

        # --- B. DASHBOARD ---
        elif menu == "DASHBOARD":
            st.title("📊 Performance Hub")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            c2.metric("Fatica (ATL)", f"{atl.iloc[-1]:.1f}")
            c3.metric("Fresco (TSB)", f"{tsb.iloc[-1]:.1f}")
            c4.metric("ACWR", f"{curr_acwr:.2f}")

            st.area_chart(pd.DataFrame({'Fitness': ctl, 'Fatica': atl, 'Forma': tsb}))

            st.divider()
            last = df.iloc[-1]
            st.subheader(f"🏁 Ultima Sessione: {last['name']}")
            col_m, col_d = st.columns([2, 1])
            with col_m:
                m_last = draw_map(last.get('map', {}).get('summary_polyline'))
                if m_last: st_folium(m_last, width=800, height=400, key="dashboard_map")
            with col_d:
                dist_km = last['distance'] / 1000
                st.write(f"**Sport:** {last['type']}")
                st.write(f"**Distanza:** {dist_km:.2f} km")
                if last['type'] in ["Run", "TrailRun"]:
                    st.write(f"**Passo:** {format_pace(last['moving_time']/dist_km)} min/km")
                elif last['type'] == "Swim":
                    st.write(f"**Passo:** {calculate_swimming_pace(last['moving_time'], last['distance'])} /100m")
                
                with st.expander("🤖 Analisi Coach", expanded=True):
                    try:
                        p = f"Atleta {u}. Sessione: {last['type']}, {dist_km:.1f}km. Commento tecnico."
                        st.write(model.generate_content(p).text)
                    except: st.write("Servizio AI momentaneamente saturo.")

        # --- C. CALENDARIO ---
        elif menu == "CALENDARIO":
            from streamlit_calendar import calendar
            st.title("📅 Diario Tecnico")
            events = [{"title": f"{row['type']} ({row['tss']:.0f})", "start": row['start_date'].isoformat(), "id": str(row['id'])} for _, row in df.iterrows()]
            res = calendar(events=events, options={"initialView": "dayGridMonth"}, key="cal_v13")
            if res.get("eventClick"):
                eid = int(res["eventClick"]["event"]["id"])
                st.session_state.selected_activity = df[df['id'] == eid].iloc[0]
            
            if "selected_activity" in st.session_state:
                act = st.session_state.selected_activity
                st.markdown(f"#### Analisi: {act['name']}")
                m_sel = draw_map(act.get('map', {}).get('summary_polyline'))
                if m_sel: st_folium(m_sel, width=1000, height=400, key=f"map_{act['id']}")

        # --- D. CHAT COACH ---
        elif menu == "CHAT COACH":
            st.title("💬 AI Professional Coach")
            if st.button("🗑️ Reset Chat"): st.session_state.messages = []; st.rerun()
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            if prompt := st.chat_input("Chiedi un consiglio..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                with st.chat_message("assistant"):
                    ctx = f"Atleta: {u}. Carico: CTL {ctl.iloc[-1]:.1f}, TSB {tsb.iloc[-1]:.1f}."
                    r = model.generate_content(ctx + "\n" + prompt).text
                    st.markdown(r)
                    st.session_state.messages.append({"role": "assistant", "content": r})

    else: st.error("Errore API Strava. Verifica le chiavi.")
else:
    st.title("🚀 Elite AI Performance Hub")
    st.write("Analisi avanzata multisport potenziata da Google Gemini.")
    auth_url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti il tuo Strava", auth_url)
