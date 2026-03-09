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

# --- 1. CONFIGURAZIONE & SICUREZZA ---
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

st.set_page_config(page_title="Elite AI Coach PRO", page_icon="🏆", layout="wide")

# --- 2. STILE CUSTOM ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .stMetric { background-color: #F0F2F6; padding: 20px; border-radius: 12px; border-left: 5px solid #FF4B4B; }
    .css-1r6slb0 { background-color: #f8f9fa; border-radius: 15px; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MOTORE DI CALCOLO (IL "CUORE" DELL'APP) ---
def format_pace(seconds_per_km):
    if seconds_per_km <= 0 or pd.isna(seconds_per_km): return "0:00"
    return f"{int(seconds_per_km // 60)}:{int(seconds_per_km % 60):02d}"

def calculate_swimming_pace(seconds, distance_meters):
    if distance_meters <= 0: return "0:00"
    pace_100m = (seconds / distance_meters) * 100
    return f"{int(pace_100m // 60)}:{int(pace_100m % 60):02d}"

def calculate_tss(row, fc_min, fc_max):
    """Calcola lo stress score (TSS) basato sulla riserva cardiaca"""
    try:
        duration_min = row.get('moving_time', 0) / 60
        hr_avg = row.get('average_heartrate', 0)
        if hr_avg > 0 and fc_max > fc_min:
            intensity = (hr_avg - fc_min) / (fc_max - fc_min)
            # Formula: (Durata * FC_avg * Intensity) / (FC_max * 3600) * 100
            return (duration_min * hr_avg * intensity) / (fc_max * 60) * 100
        return duration_min * 0.7 # Stima se manca la fascia cardio
    except: return 0

def draw_map(encoded_polyline):
    if not encoded_polyline: return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=14, tiles='CartoDB positron')
        folium.PolyLine(points, color="#FF4B4B", weight=4, opacity=0.7).add_to(m)
        return m
    except: return None

# --- 4. SESSION STATE ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"eta": 35, "peso": 75.0, "fc_min": 52, "fc_max": 188}

# OAuth Logica
if "code" in st.query_params and st.session_state.strava_token is None:
    res = requests.post('https://www.strava.com/oauth/token', 
                        data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 
                              'code': st.query_params["code"], 'grant_type': 'authorization_code'}).json()
    if 'access_token' in res:
        st.session_state.strava_token = res['access_token']
        st.rerun()

# --- 5. INTERFACCIA UTENTE ---
if st.session_state.strava_token:
    token = st.session_state.strava_token
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {token}'})
    
    if r.status_code == 200:
        df = pd.DataFrame(r.json())
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # --- ANALISI CARICO DI LAVORO ---
        u = st.session_state.user_data
        df['tss'] = df.apply(lambda x: calculate_tss(x, u['fc_min'], u['fc_max']), axis=1)
        df = df.sort_values('start_date')
        
        # CTL (Fitness) = Media mobile 42 gg | ATL (Fatica) = Media mobile 7 gg
        daily_tss = df.groupby(df['start_date'].dt.date)['tss'].sum()
        all_dates = pd.date_range(start=df['start_date'].min().date(), end=datetime.now().date(), freq='D')
        daily_full = daily_tss.reindex(all_dates.date, fill_value=0)
        ctl = daily_full.ewm(span=42).mean()
        atl = daily_full.ewm(span=7).mean()
        tsb = ctl - atl

        # Dati ultima attività per context
        last = df.iloc[-1]
        d_km = last['distance']/1000
        p_min = format_pace(last['moving_time']/d_km) if last['type'] != 'Swim' else calculate_swimming_pace(last['moving_time'], last['distance'])

        with st.sidebar:
            st.title("🏆 Elite Coach")
            menu = st.radio("NAVIGAZIONE", ["DASHBOARD", "CALENDARIO", "AI COACH", "PROFILO"])
            st.divider()
            ai_choice = st.selectbox("Modello AI:", ["Gemini 2.0 Flash (Veloce)", "Gemini 1.5 Pro (Analitico)"])
            if st.button("🚪 Logout"):
                st.session_state.strava_token = None
                st.rerun()

        # --- SEZIONE 1: DASHBOARD ---
        if menu == "DASHBOARD":
            st.header("📊 Performance & Fitness")
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}", delta=f"{ctl.iloc[-1]-ctl.iloc[-7]:.1f}")
            c2.metric("Fatica (ATL)", f"{atl.iloc[-1]:.1f}")
            c3.metric("Forma (TSB)", f"{tsb.iloc[-1]:.1f}", delta_color="normal")
            
            st.area_chart(pd.DataFrame({'Fitness (CTL)': ctl, 'Fatica (ATL)': atl, 'Forma (TSB)': tsb}))
            
            st.subheader(f"🏁 Ultima sessione: {last['name']}")
            col_map, col_data = st.columns([2, 1])
            with col_data:
                st.write(f"**Distanza:** {d_km:.2f} km")
                st.write(f"**Passo:** {p_min} {'/100m' if last['type'] == 'Swim' else '/km'}")
                st.write(f"**TSS:** {last['tss']:.1f}")
            with col_map:
                m = draw_map(last.get('map', {}).get('summary_polyline'))
                if m: st_folium(m, width=700, height=300, key="main_map")

        # --- SEZIONE 2: CALENDARIO ---
        elif menu == "CALENDARIO":
            st.header("📅 Storico Attività")
            events = [{"title": f"{row['type']} - {row['tss']:.0f} TSS", "start": row['start_date'].isoformat()} for _, row in df.iterrows()]
            calendar(events=events, options={"initialView": "dayGridMonth"})

        # --- SEZIONE 3: AI COACH ---
        elif menu == "AI COACH":
            h_col, b_col = st.columns([3, 1])
            h_col.header(f"💬 Coach AI ({ai_choice})")
            if b_col.button("🗑️ Pulisci Chat"):
                st.session_state.messages = []
                st.rerun()

            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            
            if prompt := st.chat_input("Chiedi al tuo coach..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                m_id = "gemini-2.0-flash" if "2.0" in ai_choice else "gemini-1.5-pro"
                try:
                    model = genai.GenerativeModel(m_id)
                    context = f"Atleta {u['peso']}kg, FC {u['fc_min']}-{u['fc_max']}. Fitness CTL: {ctl.iloc[-1]:.1f}. Ultimo allenamento: {last['type']}, {d_km:.2f}km a {p_min}."
                    response = model.generate_content(f"{context}\n\nDomanda: {prompt}").text
                except Exception as e:
                    response = f"⚠️ Errore AI: {str(e)}"

                with st.chat_message("assistant"): st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

        # --- SEZIONE 4: PROFILO ---
        elif menu == "PROFILO":
            st.header("👤 Impostazioni Atleta")
            with st.form("settings_form"):
                u['peso'] = st.number_input("Peso attuale (kg)", value=float(u['peso']))
                u['fc_min'] = st.number_input("FC Min (a riposo)", value=int(u['fc_min']))
                u['fc_max'] = st.number_input("FC Max (sotto sforzo)", value=int(u['fc_max']))
                if st.form_submit_button("Aggiorna Parametri"):
                    st.session_state.user_data = u
                    st.success("Dati aggiornati! Il calcolo TSS è stato ricalcolato.")
                    st.rerun()

else:
    st.title("🚀 Elite AI Performance Hub")
    st.write("Analizza i tuoi dati Strava con algoritmi di training professionale e intelligenza artificiale.")
    url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti il tuo Account Strava", url)
