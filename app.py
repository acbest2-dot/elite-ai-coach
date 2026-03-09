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
from datetime import datetime, timezone

# ============================================================
# 1. CONFIGURAZIONE
# ============================================================
REDIRECT_URI = "https://elite-ai-coach-4lm2ecs6qfslfkkzaeacrd.streamlit.app"

def get_secret(key):
    return st.secrets.get(key) or os.getenv(key)

CLIENT_ID     = get_secret("STRAVA_CLIENT_ID")
CLIENT_SECRET = get_secret("STRAVA_CLIENT_SECRET")
GEMINI_KEY    = get_secret("GOOGLE_API_KEY")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

st.set_page_config(page_title="Elite AI Coach Pro", page_icon="🏆", layout="wide")

# ============================================================
# 2. SPORT INFO & METRICHE
# ============================================================
def get_sport_info(a_type):
    sports = {
        "Run":        {"icon": "🏃", "label": "Corsa"},
        "Ride":       {"icon": "🚴", "label": "Ciclismo"},
        "Swim":       {"icon": "🏊", "label": "Nuoto"},
        "NordicSki":  {"icon": "⛷️", "label": "Sci di Fondo"},
        "AlpineSki":  {"icon": "🎿", "label": "Sci Alpino"},
        "Hike":       {"icon": "🥾", "label": "Escursionismo"},
        "Walk":       {"icon": "🚶", "label": "Camminata"},
    }
    return sports.get(a_type, {"icon": "👟", "label": a_type})

def format_metrics(row):
    a_type = row["type"]
    dist   = row["distance"] / 1000
    time   = row["moving_time"]
    if a_type == "Swim":
        pace = time / (dist * 10)
        return f"{dist:.2f} km", f"{int(pace // 60)}:{int(pace % 60):02d} /100m"
    elif a_type == "Ride":
        speed = dist / (time / 3600) if time > 0 else 0
        return f"{dist:.2f} km", f"{speed:.1f} km/h"
    else:
        pace = time / dist if dist > 0 else 0
        return f"{dist:.2f} km", f"{int(pace // 60)}:{int(pace % 60):02d} /km"

# ============================================================
# 3. CALCOLO TSS CORRETTO
# ============================================================
def calc_tss(row, u):
    """
    Calcolo TSS con priorità:
      1. FC media  → modello HR-based
      2. Watt medi → modello potenza (FTP stimato dal profilo)
      3. Fallback  → durata * intensità moderata
    """
    dur = row["moving_time"] / 60  # minuti

    hr = row["average_heartrate"] if pd.notna(row.get("average_heartrate")) else 0
    watts = row["average_watts"] if pd.notna(row.get("average_watts")) else 0
    ftp   = u.get("ftp", 200)

    if hr > 0 and u["fc_max"] > u["fc_min"]:
        intensity = (hr - u["fc_min"]) / (u["fc_max"] - u["fc_min"])
        intensity = max(0.0, min(intensity, 1.0))
        return (dur * hr * intensity) / (u["fc_max"] * 60) * 100

    if watts > 0 and ftp > 0:
        # IF = NP/FTP  →  TSS = (durata_sec * NP * IF) / (FTP * 3600) * 100
        duration_sec = row["moving_time"]
        IF = watts / ftp
        return (duration_sec * watts * IF) / (ftp * 3600) * 100

    # Fallback: durata moderata
    return dur * 0.4

# ============================================================
# 4. CTL / ATL / TSB  (con resample giornaliero)
# ============================================================
def compute_fitness(df):
    """
    Raggruppa il TSS per giorno prima di calcolare gli EWM,
    così più allenamenti nello stesso giorno non distorcono i valori.
    Ritorna una Series indicizzata per data, allineata a df.
    """
    daily = df.groupby(df["start_date"].dt.date)["tss"].sum()
    daily.index = pd.to_datetime(daily.index)

    # Riindexiamo su ogni giorno del range per riempire i giorni di riposo con 0
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)

    ctl = daily.ewm(span=42, adjust=False).mean()
    atl = daily.ewm(span=7,  adjust=False).mean()
    tsb = ctl - atl

    # Riportiamo i valori sulle righe originali del df
    df_dates = df["start_date"].dt.date.map(lambda d: pd.Timestamp(d))
    ctl_mapped = df_dates.map(ctl)
    atl_mapped = df_dates.map(atl)
    tsb_mapped = df_dates.map(tsb)

    return ctl_mapped, atl_mapped, tsb_mapped, ctl, atl, tsb

# ============================================================
# 5. MAPPA
# ============================================================
def draw_map(encoded_polyline):
    if not encoded_polyline:
        return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=13, tiles="CartoDB positron")
        folium.PolyLine(points, color="#FF4B4B", weight=5).add_to(m)
        return m
    except Exception:
        return None

# ============================================================
# 6. TOKEN VALIDATION
# ============================================================
def token_is_valid():
    token_info = st.session_state.get("strava_token_info", {})
    expires_at = token_info.get("expires_at", 0)
    return token_info.get("access_token") and datetime.now(timezone.utc).timestamp() < expires_at

def refresh_token_if_needed():
    token_info = st.session_state.get("strava_token_info", {})
    if not token_info:
        return False
    expires_at = token_info.get("expires_at", 0)
    if datetime.now(timezone.utc).timestamp() < expires_at:
        return True
    # Tenta refresh
    refresh_tok = token_info.get("refresh_token")
    if not refresh_tok:
        return False
    res = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
        },
    ).json()
    if "access_token" in res:
        st.session_state.strava_token_info = res
        return True
    return False

# ============================================================
# 7. FETCH ATTIVITÀ  (con cache 5 minuti)
# ============================================================
@st.cache_data(ttl=300)
def fetch_activities(access_token: str):
    r = requests.get(
        "https://www.strava.com/api/v3/athlete/activities?per_page=100",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if r.status_code == 200:
        return r.json()
    return []

# ============================================================
# 8. SESSION STATE INIZIALIZZAZIONE
# ============================================================
if "strava_token_info" not in st.session_state:
    st.session_state.strava_token_info = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "peso":   75.0,
        "fc_min": 50,
        "fc_max": 190,
        "ftp":    200,
    }

# ============================================================
# 9. OAUTH  (scambio code → token)
# ============================================================
if "code" in st.query_params and not st.session_state.strava_token_info.get("access_token"):
    res = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id":     CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code":          st.query_params["code"],
            "grant_type":    "authorization_code",
        },
    ).json()
    if "access_token" in res:
        st.session_state.strava_token_info = res
        st.rerun()

# ============================================================
# 10. CORE APP
# ============================================================
token_ok = refresh_token_if_needed()

if token_ok:
    access_token = st.session_state.strava_token_info["access_token"]
    raw          = fetch_activities(access_token)

    if not raw:
        st.error("Impossibile recuperare le attività. Prova a fare logout e ricollegarti.")
        st.stop()

    df = pd.DataFrame(raw)
    df["start_date"] = pd.to_datetime(df["start_date_local"]).dt.tz_localize(None)
    df = df.sort_values("start_date").reset_index(drop=True)

    # Assicuriamoci che le colonne opzionali esistano
    for col in ["average_heartrate", "average_watts", "total_elevation_gain",
                "average_cadence", "summary_polyline"]:
        if col not in df.columns:
            df[col] = np.nan

    # TSS per ogni riga
    u = st.session_state.user_data
    df["tss"] = df.apply(lambda row: calc_tss(row, u), axis=1)

    # CTL / ATL / TSB giornalieri
    ctl_series, atl_series, tsb_series, ctl_daily, atl_daily, tsb_daily = compute_fitness(df)
    df["ctl"] = ctl_series.values
    df["atl"] = atl_series.values
    df["tsb"] = tsb_series.values

    current_ctl = df["ctl"].iloc[-1]
    current_atl = df["atl"].iloc[-1]
    current_tsb = df["tsb"].iloc[-1]

    # ---- SIDEBAR ----
    with st.sidebar:
        st.title("🏆 Elite AI Coach")
        menu = st.radio("MENU", ["DASHBOARD", "CALENDARIO", "COACH CHAT", "PROFILO FISICO"])
        st.divider()

        # Auto-discovery modelli Gemini
        try:
            models   = [m.name for m in genai.list_models()
                        if "generateContent" in m.supported_generation_methods]
            sel_model = st.selectbox("Cervello AI:", models, index=0)
        except Exception:
            sel_model = "gemini-1.5-flash"

        if st.button("Logout"):
            st.session_state.strava_token_info = {}
            st.cache_data.clear()
            st.rerun()

    # ============================================================
    # DASHBOARD
    # ============================================================
    if menu == "DASHBOARD":
        st.header("📊 Performance Hub")

        # --- Metriche fitness ---
        def tsb_status(tsb_val):
            if tsb_val > 20:
                return "⚠️ Possibile detrain"
            elif tsb_val > -10:
                return "✅ Forma ottimale"
            elif tsb_val > -20:
                return "🟡 Accumulo fatica"
            else:
                return "🔴 Sovraccarico"

        c1, c2, c3 = st.columns(3)
        c1.metric("Fitness (CTL)", f"{current_ctl:.1f}", help="Chronic Training Load – media 42 giorni")
        c2.metric(
            "Forma (TSB)",
            f"{current_tsb:.1f}",
            help=tsb_status(current_tsb),
            delta=tsb_status(current_tsb),
        )
        c3.metric("Fatica (ATL)", f"{current_atl:.1f}", help="Acute Training Load – media 7 giorni")

        st.divider()

        # --- Ultima attività ---
        last    = df.iloc[-1]
        s_info  = get_sport_info(last["type"])
        d_str, p_str = format_metrics(last)

        st.subheader(f"{s_info['icon']} {s_info['label']}: {last['name']}")

        col_map, col_stats = st.columns([2, 1])

        with col_stats:
            st.metric("Distanza", d_str)
            st.metric("Passo / Velocità", p_str)
            st.metric("Dislivello", f"{last.get('total_elevation_gain', 0) or 0:.0f} m")
            cadence = last.get("average_cadence")
            watts   = last.get("average_watts")
            st.write(f"**Cadenza:** {f'{cadence:.0f} rpm' if pd.notna(cadence) else 'N/A'}")
            st.write(f"**Watt Medi:** {f'{watts:.0f} W' if pd.notna(watts) else 'N/A'}")
            st.write(f"**TSS Sessione:** {last['tss']:.1f}")

        with col_map:
            poly   = last.get("map", {})
            poly   = poly.get("summary_polyline") if isinstance(poly, dict) else None
            m_obj  = draw_map(poly)
            if m_obj:
                st_folium(m_obj, width=700, height=350, key="last_map")
            else:
                st.info("Nessuna traccia GPS disponibile per questa attività.")

        # --- Analisi AI ---
        st.markdown("---")
        st.subheader("🤖 Analisi del Coach")

        with st.spinner("L'AI sta analizzando i dati..."):
            try:
                ctx = (
                    f"Sport: {last['type']}. Distanza: {d_str}. Passo/Vel: {p_str}. "
                    f"Dislivello: {last.get('total_elevation_gain', 0) or 0:.0f}m. "
                    f"TSS sessione: {last['tss']:.1f}. "
                    f"Fitness CTL: {current_ctl:.1f}. Forma TSB: {current_tsb:.1f}. "
                    f"Fatica ATL: {current_atl:.1f}. Stato: {tsb_status(current_tsb)}."
                )
                prompt = (
                    "Sei un coach sportivo esperto. Commenta questa attività: "
                    "è stata produttiva in relazione alla forma attuale? "
                    "Come influisce sul carico? Cosa può migliorare l'atleta? "
                    "Suggerisci il tipo ideale di allenamento per la prossima sessione "
                    "in base ai valori CTL/ATL/TSB attuali."
                )
                result = genai.GenerativeModel(sel_model).generate_content(
                    f"{ctx}\n\n{prompt}"
                ).text
                st.info(result)
            except Exception as e:
                st.error(f"Impossibile generare l'analisi AI: {e}")

        # --- Grafico CTL/ATL/TSB ---
        chart_df = pd.DataFrame(
            {"Fitness (CTL)": ctl_daily, "Fatica (ATL)": atl_daily, "Forma (TSB)": tsb_daily}
        ).dropna()
        st.area_chart(chart_df)

    # ============================================================
    # CALENDARIO
    # ============================================================
    elif menu == "CALENDARIO":
        st.header("📅 Storico Allenamenti")

        # Filtro per sport
        sport_types = sorted(df["type"].unique().tolist())
        selected_sports = st.multiselect(
            "Filtra per sport:", sport_types, default=sport_types
        )
        df_filtered = df[df["type"].isin(selected_sports)]

        events = []
        color_map = {
            "Run":  "#FF4B4B",
            "Ride": "#4B9EFF",
            "Swim": "#4BFFE0",
            "Hike": "#7FFF4B",
            "Walk": "#FFD54B",
        }
        for _, row in df_filtered.iterrows():
            events.append({
                "title":           f"{get_sport_info(row['type'])['icon']} {row['distance']/1000:.1f}km",
                "start":           row["start_date"].isoformat(),
                "backgroundColor": color_map.get(row["type"], "#AAAAAA"),
            })

        calendar(events=events, options={"initialView": "dayGridMonth"})

        st.dataframe(
            df_filtered[["start_date", "type", "name", "distance", "tss", "ctl", "tsb"]]
            .sort_values("start_date", ascending=False)
            .rename(columns={
                "start_date": "Data", "type": "Sport", "name": "Nome",
                "distance": "Distanza (m)", "tss": "TSS", "ctl": "CTL", "tsb": "TSB"
            }),
            use_container_width=True,
        )

    # ============================================================
    # COACH CHAT
    # ============================================================
    elif menu == "COACH CHAT":
        st.header("💬 Parla con il tuo Coach")

        if st.button("🗑️ Pulisci chat"):
            st.session_state.messages = []
            st.rerun()

        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        if prompt := st.chat_input("Chiedi info sui tuoi carichi, prossimo allenamento..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Contesto fisico + fitness nel system prompt
            system_ctx = (
                f"Sei un coach sportivo esperto e motivante. "
                f"Dati atleta: peso {u['peso']}kg, FC riposo {u['fc_min']}, FC max {u['fc_max']}, FTP {u['ftp']}W. "
                f"Stato attuale: CTL (Fitness) {current_ctl:.1f}, ATL (Fatica) {current_atl:.1f}, "
                f"TSB (Forma) {current_tsb:.1f}. "
                f"Totale attività: {len(df)}. Ultimo sport: {df.iloc[-1]['type']}."
            )

            full_messages = [
                {"role": "user", "content": system_ctx + "\n\nDomanda atleta: " + prompt}
            ]

            try:
                res = genai.GenerativeModel(sel_model).generate_content(
                    full_messages[0]["content"]
                ).text
            except Exception as e:
                res = f"⚠️ Errore nella risposta AI: {e}"

            with st.chat_message("assistant"):
                st.markdown(res)
            st.session_state.messages.append({"role": "assistant", "content": res})

    # ============================================================
    # PROFILO FISICO
    # ============================================================
    elif menu == "PROFILO FISICO":
        st.header("👤 Parametri Atleta")

        st.info(
            "Questi parametri influenzano il calcolo del TSS e quindi "
            "tutti i valori di fitness (CTL/ATL/TSB). Tienili aggiornati!"
        )

        with st.form("settings"):
            col1, col2 = st.columns(2)
            with col1:
                peso   = st.number_input("Peso (kg)",      value=float(u["peso"]),   min_value=30.0, max_value=200.0)
                fc_min = st.number_input("FC a Riposo",    value=int(u["fc_min"]),   min_value=30,   max_value=100)
            with col2:
                fc_max = st.number_input("FC Massima",     value=int(u["fc_max"]),   min_value=100,  max_value=250)
                ftp    = st.number_input("FTP (Watt)",     value=int(u.get("ftp", 200)), min_value=50, max_value=600,
                                         help="Functional Threshold Power – usato per il TSS in bici")

            if st.form_submit_button("💾 Aggiorna Parametri"):
                st.session_state.user_data = {
                    "peso":   peso,
                    "fc_min": fc_min,
                    "fc_max": fc_max,
                    "ftp":    ftp,
                }
                st.cache_data.clear()   # ricalcola TSS
                st.success("✅ Parametri salvati. Il fitness verrà ricalcolato al prossimo caricamento.")
                st.rerun()

        # Statistiche aggregate
        st.divider()
        st.subheader("📈 Riepilogo Stagione")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Attività Totali",  len(df))
        col_b.metric("Km Totali",        f"{df['distance'].sum()/1000:.0f} km")
        col_c.metric("Ore Totali",       f"{df['moving_time'].sum()/3600:.0f} h")
        col_d.metric("TSS Cumulativo",   f"{df['tss'].sum():.0f}")

        sport_counts = df["type"].value_counts()
        st.bar_chart(sport_counts)

# ============================================================
# LOGIN PAGE
# ============================================================
else:
    st.title("🚀 Elite AI Performance Hub")
    st.markdown(
        "Connetti il tuo account Strava per analizzare le attività, "
        "monitorare il fitness e ricevere consigli dal tuo coach AI."
    )

    url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=read,activity:read_all"
        f"&approval_prompt=force"
    )
    st.link_button("🔥 Connetti Strava", url)
