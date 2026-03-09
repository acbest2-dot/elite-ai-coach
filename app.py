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

# --- 1. CONFIGURAZIONE ---
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app"

def get_secret(key): return st.secrets.get(key) or os.getenv(key)

CLIENT_ID = get_secret("STRAVA_CLIENT_ID")
CLIENT_SECRET = get_secret("STRAVA_CLIENT_SECRET")
GEMINI_KEY = get_secret("GOOGLE_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach Pro", page_icon="🏆", layout="wide")

# --- 2. LOGICHE TECNICHE E CATEGORIZZAZIONE ---
def get_sport_info(a_type):
    # Categorizzazione e icone
    sports = {
        "Run": {"icon": "🏃", "label": "Corsa"},
        "Ride": {"icon": "🚴", "label": "Ciclismo"},
        "Swim": {"icon": "🏊", "label": "Nuoto"},
        "NordicSki": {"icon": "⛷️", "label": "Sci di Fondo"},
        "AlpineSki": {"icon": "🎿", "label": "Sci Alpino"},
        "Hike": {"icon": "🥾", "label": "Escursionismo"},
        "Walk": {"icon": "🚶", "label": "Camminata"}
    }
    return sports.get(a_type, {"icon": "👟", "label": a_type})

def format_metrics(row):
    a_type = row['type']
    dist = row['distance'] / 1000
    time = row['moving_time']
    if a_type == "Swim":
        pace = (time / (dist * 10))
        return f"{dist:.2f} km", f"{int(pace // 60)}:{int(pace % 60):02d} /100m"
    elif a_type == "Ride":
        speed = dist / (time / 3600)
        return f"{dist:.2f} km", f"{speed:.1f} km/h"
    else:
        pace = (time / dist)
        return f"{dist:.2f} km", f"{int(pace // 60)}:{int(pace % 60):02d} /km"

def draw_map(encoded_polyline):
    if not encoded_polyline: return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=13, tiles='CartoDB positron')
        folium.PolyLine(points, color="#FF4B4B", weight=5).add_to(m)
        return m
    except: return None

# --- 3. SESSION STATE ---
if "strava_token" not in st.session_state: st.session_state.strava_token = None
if "messages" not in st.session_state: st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {"peso": 75.0, "fc_min": 50, "fc_max": 190}

# OAuth
if "code" in st.query_params and st.session_state.strava_token is None:
    res = requests.post('https://www.strava.com/oauth/token', 
                        data={'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 
                              'code': st.query_params["code"], 'grant_type': 'authorization_code'}).json()
    if 'access_token' in res:
        st.session_state.strava_token = res['access_token']
        st.rerun()

# --- 4. CORE APP ---
if st.session_state.strava_token:
    r = requests.get("https://www.strava.com/api/v3/athlete/activities?per_page=100", 
                     headers={'Authorization': f'Bearer {st.session_state.strava_token}'})
    
    if r.status_code == 200:
        df = pd.DataFrame(r.json())
        df['start_date'] = pd.to_datetime(df['start_date_local']).dt.tz_localize(None)
        
        # Calcolo TSS Professionale
        u = st.session_state.user_data
        def calc_tss(row):
            hr = row.get('average_heartrate', 0)
            dur = row['moving_time'] / 60
            if hr > 0:
                intensity = (hr - u['fc_min']) / (u['fc_max'] - u['fc_min'])
                return (dur * hr * intensity) / (u['fc_max'] * 60) * 100
            return dur * 0.4
        
        df['tss'] = df.apply(calc_tss, axis=1)
        df = df.sort_values('start_date')
        ctl = df['tss'].ewm(span=42).mean()
        tsb = ctl - df['tss'].ewm(span=7).mean()

        with st.sidebar:
            st.title("🏆 Elite AI Coach")
            menu = st.radio("MENU", ["DASHBOARD", "CALENDARIO", "COACH CHAT", "PROFILO FISICO"])
            st.divider()
            # Auto-discovery modelli
            try:
                models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                sel_model = st.selectbox("Cervello AI:", models, index=0)
            except: sel_model = "gemini-1.5-flash"
            if st.button("Logout"):
                st.session_state.strava_token = None
                st.rerun()

        # --- DASHBOARD ---
        if menu == "DASHBOARD":
            st.header("📊 Performance Hub")
            
            # Row 1: Metriche Fitness
            c1, c2, c3 = st.columns(3)
            c1.metric("Fitness (CTL)", f"{ctl.iloc[-1]:.1f}")
            
            # Logica Alert TSB
            current_tsb = tsb.iloc[-1]
            status = "Ottimale" if -10 < current_tsb < 10 else "Fatica" if current_tsb < -20 else "Riposo"
            c2.metric("Forma (TSB)", f"{current_tsb:.1f}", help=f"Stato attuale: {status}")
            c3.metric("Fatica (ATL)", f"{df['tss'].tail(7).mean():.1f}")

            st.divider()

            # Row 2: Ultima Attività con Mappa
            last = df.iloc[-1]
            s_info = get_sport_info(last['type'])
            d_str, p_str = format_metrics(last)
            
            st.subheader(f"{s_info['icon']} {s_info['label']}: {last['name']}")
            
            col_map, col_stats = st.columns([2, 1])
            with col_stats:
                st.metric("Distanza", d_str)
                st.metric("Passo/Vel.", p_str)
                st.metric("Dislivello", f"{last.get('total_elevation_gain', 0)} m")
                st.write(f"**Cadenza:** {last.get('average_cadence', 'N/A')}")
                st.write(f"**Watt Medi:** {last.get('average_watts', 'N/A')}")
            
            with col_map:
                m_obj = draw_map(last.get('map', {}).get('summary_polyline'))
                if m_obj: st_folium(m_obj, width=700, height=350, key="last_map")

            # Row 3: AI Commento
            st.markdown("---")
            st.subheader("🤖 Analisi del Coach")
            with st.spinner("L'AI sta analizzando i dati..."):
                try:
                    ctx = f"Sport: {last['type']}. Dist: {d_str}. Passo: {p_str}. Salita: {last.get('total_elevation_gain')}m. Fitness CTL: {ctl.iloc[-1]:.1f}, Forma TSB: {current_tsb:.1f}."
                    prompt = "Commenta questa attività. È stata produttiva? Come influisce sulla mia forma attuale? Cosa posso fare meglio?"
                    res = genai.GenerativeModel(sel_model).generate_content(f"{ctx}\n\n{prompt}").text
                    st.info(res)
                except: st.error("Impossibile generare l'analisi AI al momento.")
            
            st.area_chart(pd.DataFrame({'Fitness (CTL)': ctl, 'Forma (TSB)': tsb}))

        # --- CALENDARIO ---
        elif menu == "CALENDARIO":
            st.header("📅 Storico Allenamenti")
            events = []
            for _, row in df.iterrows():
                events.append({
                    "title": f"{get_sport_info(row['type'])['icon']} {row['distance']/1000:.1f}km",
                    "start": row['start_date'].isoformat(),
                    "backgroundColor": "#FF4B4B"
                })
            calendar(events=events, options={"initialView": "dayGridMonth"})
            st.dataframe(df[['start_date', 'type', 'name', 'distance', 'tss']].sort_values('start_date', ascending=False))

        # --- CHAT ---
        elif menu == "COACH CHAT":
            st.header("💬 Parla con il tuo Coach")
            if st.button("🗑️ Pulisci"): st.session_state.messages = []
            for m in st.session_state.messages:
                with st.chat_message(m["role"]): st.markdown(m["content"])
            if p := st.chat_input("Chiedi info sui tuoi carichi..."):
                st.session_state.messages.append({"role": "user", "content": p})
                with st.chat_message("user"): st.markdown(p)
                # Includiamo il contesto fisico nella chat
                full_p = f"Dati atleta: {u}. Ultimi dati: CTL {ctl.iloc[-1]:.1f}, TSB {tsb.iloc[-1]:.1f}. Domanda: {p}"
                res = genai.GenerativeModel(sel_model).generate_content(full_p).text
                with st.chat_message("assistant"): st.markdown(res)
                st.session_state.messages.append({"role": "assistant", "content": res})

        # --- PROFILO ---
        elif menu == "PROFILO FISICO":
            st.header("👤 Parametri Atleta")
            with st.form("settings"):
                u['peso'] = st.number_input("Peso (kg)", value=float(u['peso']))
                u['fc_min'] = st.number_input("FC a Riposo", value=int(u['fc_min']))
                u['fc_max'] = st.number_input("FC Massima", value=int(u['fc_max']))
                if st.form_submit_button("Aggiorna Parametri"):
                    st.session_state.user_data = u
                    st.success("Parametri salvati e Fitness ricalcolato!")
                    st.rerun()
else:
    st.title("🚀 Elite AI Performance Hub")
    url = f"https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri={REDIRECT_URI}&scope=read,activity:read_all&approval_prompt=force"
    st.link_button("🔥 Connetti Strava", url)
