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
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import calendar as cal_module

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
# CSS CUSTOM
# ============================================================
st.markdown("""
<style>
    /* Card attività */
    .activity-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 16px;
    }
    .activity-header {
        font-size: 18px;
        font-weight: 700;
        color: #e94560;
        margin-bottom: 12px;
    }
    .metric-row {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
    }
    .metric-pill {
        background: rgba(233,69,96,0.12);
        border: 1px solid rgba(233,69,96,0.3);
        border-radius: 20px;
        padding: 4px 12px;
        font-size: 13px;
        color: #ccc;
    }
    .metric-pill span { color: #e94560; font-weight: 700; }

    /* Zone badge */
    .zone-badge {
        display: inline-block;
        border-radius: 8px;
        padding: 2px 10px;
        font-size: 12px;
        font-weight: 700;
    }

    /* Pulsanti sport filter */
    div[data-testid="stHorizontalBlock"] .stButton button {
        border-radius: 20px;
        font-size: 13px;
        padding: 4px 14px;
    }

    /* Sezione stato fisico */
    .fitness-indicator {
        border-radius: 12px;
        padding: 16px;
        text-align: center;
    }

    /* Heatmap cell */
    .hm-cell {
        display: inline-block;
        width: 14px;
        height: 14px;
        border-radius: 3px;
        margin: 1px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 2. DIZIONARIO SPORT COMPLETO
# ============================================================
SPORT_INFO = {
    "Run":                  {"icon": "🏃", "label": "Corsa",          "color": "#FF4B4B"},
    "TrailRun":             {"icon": "🏔️", "label": "Trail Run",      "color": "#FF7043"},
    "Ride":                 {"icon": "🚴", "label": "Ciclismo",        "color": "#2196F3"},
    "VirtualRide":          {"icon": "🖥️", "label": "Ciclismo Virtuale","color": "#42A5F5"},
    "MountainBikeRide":     {"icon": "🚵", "label": "MTB",            "color": "#1565C0"},
    "Swim":                 {"icon": "🏊", "label": "Nuoto",           "color": "#00BCD4"},
    "NordicSki":            {"icon": "⛷️", "label": "Sci di Fondo",   "color": "#B3E5FC"},
    "AlpineSki":            {"icon": "🎿", "label": "Sci Alpino",      "color": "#81D4FA"},
    "BackcountrySki":       {"icon": "🎿", "label": "Sci Alpinismo",   "color": "#4FC3F7"},
    "Snowboard":            {"icon": "🏂", "label": "Snowboard",       "color": "#80DEEA"},
    "Hike":                 {"icon": "🥾", "label": "Escursionismo",   "color": "#4CAF50"},
    "Walk":                 {"icon": "🚶", "label": "Camminata",       "color": "#8BC34A"},
    "Workout":              {"icon": "💪", "label": "Allenamento",     "color": "#FF9800"},
    "WeightTraining":       {"icon": "🏋️", "label": "Pesi",           "color": "#FFA726"},
    "Yoga":                 {"icon": "🧘", "label": "Yoga",            "color": "#CE93D8"},
    "Rowing":               {"icon": "🚣", "label": "Canottaggio",     "color": "#26C6DA"},
    "Kayaking":             {"icon": "🛶", "label": "Kayak",           "color": "#00ACC1"},
    "Crossfit":             {"icon": "🔥", "label": "CrossFit",        "color": "#EF5350"},
    "Soccer":               {"icon": "⚽", "label": "Calcio",          "color": "#66BB6A"},
    "Tennis":               {"icon": "🎾", "label": "Tennis",          "color": "#FFEE58"},
}

def get_sport_info(a_type):
    return SPORT_INFO.get(a_type, {"icon": "🏅", "label": a_type, "color": "#9E9E9E"})

# ============================================================
# 3. METRICHE FORMATTATE
# ============================================================
def format_metrics(row):
    a_type = row["type"]
    dist   = row["distance"] / 1000
    time   = row["moving_time"]
    elev   = row.get("total_elevation_gain", 0) or 0
    hr_avg = row.get("average_heartrate")
    hr_max = row.get("max_heartrate")
    cad    = row.get("average_cadence")
    watts  = row.get("average_watts")
    cal_   = row.get("kilojoules") or row.get("calories", 0) or 0
    suffer = row.get("suffer_score")
    hrs    = int(time // 3600)
    mins   = int((time % 3600) // 60)
    secs   = int(time % 60)
    dur_str = f"{hrs}h {mins:02d}m" if hrs > 0 else f"{mins}m {secs:02d}s"

    if a_type == "Swim":
        pace_raw = time / (dist * 10) if dist > 0 else 0
        pace_str = f"{int(pace_raw // 60)}:{int(pace_raw % 60):02d} /100m"
        speed_str = f"{dist / (time / 3600):.1f} km/h" if time > 0 else "N/A"
    elif a_type in ("Ride", "VirtualRide", "MountainBikeRide"):
        speed = dist / (time / 3600) if time > 0 else 0
        pace_str = f"{speed:.1f} km/h"
        speed_str = pace_str
    else:
        pace_raw = time / dist if dist > 0 else 0
        pace_str = f"{int(pace_raw // 60)}:{int(pace_raw % 60):02d} /km"
        speed_str = f"{dist / (time / 3600):.1f} km/h" if time > 0 else "N/A"

    return {
        "dist_str":  f"{dist:.2f} km",
        "pace_str":  pace_str,
        "speed_str": speed_str,
        "dur_str":   dur_str,
        "elev":      f"{elev:.0f} m",
        "hr_avg":    f"{hr_avg:.0f} bpm" if pd.notna(hr_avg) else "N/A",
        "hr_max":    f"{hr_max:.0f} bpm" if pd.notna(hr_max) else "N/A",
        "cadence":   f"{cad:.0f} rpm" if pd.notna(cad) else "N/A",
        "watts":     f"{watts:.0f} W"  if pd.notna(watts) else "N/A",
        "calories":  f"{cal_:.0f} kcal" if cal_ else "N/A",
        "suffer":    f"{suffer:.0f}" if pd.notna(suffer) else "N/A",
        "dist_km":   dist,
        "time_sec":  time,
    }

# ============================================================
# 4. ZONE FC
# ============================================================
def get_hr_zone(hr_pct):
    if hr_pct < 0.60: return 1, "#4CAF50", "Z1 Recupero"
    if hr_pct < 0.70: return 2, "#8BC34A", "Z2 Base"
    if hr_pct < 0.80: return 3, "#FFC107", "Z3 Aerobico"
    if hr_pct < 0.90: return 4, "#FF9800", "Z4 Soglia"
    return 5, "#F44336", "Z5 VO2max"

def get_zone_for_activity(row, fc_max):
    hr = row.get("average_heartrate")
    if pd.notna(hr) and fc_max > 0:
        pct = hr / fc_max
        z, color, label = get_hr_zone(pct)
        return z, color, label
    return 0, "#9E9E9E", "N/A"

# ============================================================
# 5. CALCOLO TSS
# ============================================================
def calc_tss(row, u):
    dur   = row["moving_time"] / 60
    hr    = row["average_heartrate"] if pd.notna(row.get("average_heartrate")) else 0
    watts = row["average_watts"]     if pd.notna(row.get("average_watts"))     else 0
    ftp   = u.get("ftp", 200)

    if hr > 0 and u["fc_max"] > u["fc_min"]:
        intensity = (hr - u["fc_min"]) / (u["fc_max"] - u["fc_min"])
        intensity = max(0.0, min(intensity, 1.0))
        return (dur * hr * intensity) / (u["fc_max"] * 60) * 100

    if watts > 0 and ftp > 0:
        duration_sec = row["moving_time"]
        IF = watts / ftp
        return (duration_sec * watts * IF) / (ftp * 3600) * 100

    return dur * 0.4

# ============================================================
# 6. CTL / ATL / TSB
# ============================================================
def compute_fitness(df):
    daily = df.groupby(df["start_date"].dt.date)["tss"].sum()
    daily.index = pd.to_datetime(daily.index)
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)

    ctl = daily.ewm(span=42, adjust=False).mean()
    atl = daily.ewm(span=7,  adjust=False).mean()
    tsb = ctl - atl

    df_dates   = df["start_date"].dt.date.map(lambda d: pd.Timestamp(d))
    ctl_mapped = df_dates.map(ctl)
    atl_mapped = df_dates.map(atl)
    tsb_mapped = df_dates.map(tsb)

    return ctl_mapped, atl_mapped, tsb_mapped, ctl, atl, tsb, daily

# ============================================================
# 7. MAPPA
# ============================================================
def draw_map(encoded_polyline, height=300):
    if not encoded_polyline:
        return None
    try:
        points = polyline.decode(encoded_polyline)
        m = folium.Map(location=points[0], zoom_start=13, tiles="CartoDB positron")
        folium.PolyLine(points, color="#e94560", weight=4, opacity=0.9).add_to(m)
        folium.CircleMarker(points[0],  radius=6, color="#4CAF50", fill=True).add_to(m)
        folium.CircleMarker(points[-1], radius=6, color="#F44336", fill=True).add_to(m)
        return m
    except Exception:
        return None

# ============================================================
# 8. TOKEN
# ============================================================
def refresh_token_if_needed():
    token_info = st.session_state.get("strava_token_info", {})
    if not token_info:
        return False
    if datetime.now(timezone.utc).timestamp() < token_info.get("expires_at", 0):
        return True
    refresh_tok = token_info.get("refresh_token")
    if not refresh_tok:
        return False
    res = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": refresh_tok,
    }).json()
    if "access_token" in res:
        st.session_state.strava_token_info = res
        return True
    return False

# ============================================================
# 9. FETCH
# ============================================================
@st.cache_data(ttl=300)
def fetch_activities(access_token: str):
    r = requests.get(
        "https://www.strava.com/api/v3/athlete/activities?per_page=100",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return r.json() if r.status_code == 200 else []

@st.cache_data(ttl=300)
def fetch_athlete(access_token: str):
    r = requests.get(
        "https://www.strava.com/api/v3/athlete",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return r.json() if r.status_code == 200 else {}

# ============================================================
# 10. SESSION STATE
# ============================================================
for key, val in {
    "strava_token_info": {},
    "messages": [],
    "user_data": {"peso": 75.0, "fc_min": 50, "fc_max": 190, "ftp": 200},
    "sport_filter": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================================
# 11. OAUTH
# ============================================================
if "code" in st.query_params and not st.session_state.strava_token_info.get("access_token"):
    res = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": st.query_params["code"], "grant_type": "authorization_code",
    }).json()
    if "access_token" in res:
        st.session_state.strava_token_info = res
        st.rerun()

# ============================================================
# 12. CORE APP
# ============================================================
token_ok = refresh_token_if_needed()

if token_ok:
    access_token = st.session_state.strava_token_info["access_token"]
    raw          = fetch_activities(access_token)
    athlete      = fetch_athlete(access_token)

    if not raw:
        st.error("Impossibile recuperare le attività.")
        st.stop()

    df = pd.DataFrame(raw)
    df["start_date"] = pd.to_datetime(df["start_date_local"]).dt.tz_localize(None)
    df = df.sort_values("start_date").reset_index(drop=True)

    for col in ["average_heartrate", "max_heartrate", "average_watts", "total_elevation_gain",
                "average_cadence", "kilojoules", "calories", "suffer_score"]:
        if col not in df.columns:
            df[col] = np.nan

    u = st.session_state.user_data
    df["tss"] = df.apply(lambda row: calc_tss(row, u), axis=1)

    ctl_s, atl_s, tsb_s, ctl_daily, atl_daily, tsb_daily, tss_daily = compute_fitness(df)
    df["ctl"] = ctl_s.values
    df["atl"] = atl_s.values
    df["tsb"] = tsb_s.values

    current_ctl = df["ctl"].iloc[-1]
    current_atl = df["atl"].iloc[-1]
    current_tsb = df["tsb"].iloc[-1]

    # Zone per ogni attività
    df["zone_num"]   = df.apply(lambda r: get_zone_for_activity(r, u["fc_max"])[0], axis=1)
    df["zone_color"] = df.apply(lambda r: get_zone_for_activity(r, u["fc_max"])[1], axis=1)
    df["zone_label"] = df.apply(lambda r: get_zone_for_activity(r, u["fc_max"])[2], axis=1)

    def tsb_status(v):
        if v > 20:  return "⚠️ Possibile detrain",  "#FF9800"
        if v > -10: return "✅ Forma ottimale",      "#4CAF50"
        if v > -20: return "🟡 Accumulo fatica",     "#FFC107"
        return "🔴 Sovraccarico", "#F44336"

    status_label, status_color = tsb_status(current_tsb)

    # ---- SIDEBAR ----
    with st.sidebar:
        st.markdown(f"### 🏆 Elite AI Coach")
        if athlete:
            name = f"{athlete.get('firstname','')} {athlete.get('lastname','')}".strip()
            if name:
                st.markdown(f"**{name}**")
            if athlete.get("profile_medium"):
                st.image(athlete["profile_medium"], width=60)
        st.divider()

        menu = st.radio("", [
            "📊 Dashboard",
            "💪 Stato Fisico",
            "📅 Calendario",
            "💬 Coach Chat",
            "🏅 Record Personali",
            "👤 Profilo Fisico",
        ], label_visibility="collapsed")

        st.divider()
        try:
            models    = [m.name for m in genai.list_models()
                         if "generateContent" in m.supported_generation_methods]
            sel_model = st.selectbox("🧠 Modello AI:", models, index=0)
        except Exception:
            sel_model = "gemini-1.5-flash"

        st.divider()
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("CTL", f"{current_ctl:.0f}")
        col_s2.metric("ATL", f"{current_atl:.0f}")
        col_s3.metric("TSB", f"{current_tsb:.0f}")
        st.markdown(f"<div style='text-align:center; color:{status_color}; font-size:13px'>{status_label}</div>", unsafe_allow_html=True)

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.strava_token_info = {}
            st.cache_data.clear()
            st.rerun()

    # ============================================================
    # DASHBOARD
    # ============================================================
    if menu == "📊 Dashboard":
        st.markdown("## 📊 Performance Hub")

        # KPI row
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Fitness (CTL)", f"{current_ctl:.1f}", help="Chronic Training Load – carico cronico 42gg")
        c2.metric("Forma (TSB)",   f"{current_tsb:.1f}", delta=status_label)
        c3.metric("Fatica (ATL)",  f"{current_atl:.1f}", help="Acute Training Load – carico acuto 7gg")
        c4.metric("Attività Totali", len(df))
        c5.metric("Km Totali", f"{df['distance'].sum()/1000:.0f}")

        st.divider()

        # --- Ultime 3 attività ---
        st.markdown("### 🕐 Ultime 3 Attività")
        last3 = df.iloc[-3:][::-1]

        for idx, (_, row) in enumerate(last3.iterrows()):
            s   = get_sport_info(row["type"])
            m   = format_metrics(row)
            z_n, z_c, z_l = get_zone_for_activity(row, u["fc_max"])
            is_last = (idx == 0)

            with st.container():
                st.markdown(f"""
                <div class="activity-card" style="border-color: {s['color']}40;">
                    <div class="activity-header" style="color:{s['color']}">
                        {s['icon']} {row['name']}
                        <span style="font-size:12px; color:#888; font-weight:400; margin-left:8px">
                            {row['start_date'].strftime('%d %b %Y · %H:%M')}
                        </span>
                        <span class="zone-badge" style="background:{z_c}22; color:{z_c}; border:1px solid {z_c}44; float:right; font-size:12px">
                            {z_l}
                        </span>
                    </div>
                    <div class="metric-row">
                        <div class="metric-pill">📏 Distanza <span>{m['dist_str']}</span></div>
                        <div class="metric-pill">⏱️ Durata <span>{m['dur_str']}</span></div>
                        <div class="metric-pill">⚡ {('Passo' if row['type'] not in ('Ride','VirtualRide','MountainBikeRide') else 'Velocità')} <span>{m['pace_str']}</span></div>
                        <div class="metric-pill">⛰️ Dislivello <span>{m['elev']}</span></div>
                        <div class="metric-pill">❤️ FC Media <span>{m['hr_avg']}</span></div>
                        <div class="metric-pill">💓 FC Max <span>{m['hr_max']}</span></div>
                        <div class="metric-pill">🔄 Cadenza <span>{m['cadence']}</span></div>
                        <div class="metric-pill">⚡ Watt <span>{m['watts']}</span></div>
                        <div class="metric-pill">🔥 Calorie <span>{m['calories']}</span></div>
                        <div class="metric-pill">📊 TSS <span>{row['tss']:.1f}</span></div>
                        <div class="metric-pill">😓 Suffer Score <span>{m['suffer']}</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Mappa solo per l'ultima attività
            if is_last:
                poly  = row.get("map", {})
                poly  = poly.get("summary_polyline") if isinstance(poly, dict) else None
                m_obj = draw_map(poly)
                if m_obj:
                    col_m, col_info = st.columns([3, 1])
                    with col_m:
                        st_folium(m_obj, width=None, height=280, key=f"map_{idx}")
                    with col_info:
                        st.markdown(f"**Sport:** {s['label']}")
                        st.markdown(f"**Data:** {row['start_date'].strftime('%d %b %Y')}")
                        st.markdown(f"**Zona dominante:** {z_l}")
                        pct_fc = (row.get('average_heartrate', 0) or 0) / u['fc_max'] * 100
                        st.markdown(f"**%FC Max:** {pct_fc:.0f}%")

        # --- AI Analisi ultima attività ---
        st.divider()
        st.markdown("### 🤖 Analisi Coach — Ultima Attività")
        last    = df.iloc[-1]
        m_last  = format_metrics(last)
        s_last  = get_sport_info(last["type"])

        with st.spinner("Il coach sta analizzando..."):
            try:
                ctx = (
                    f"Sport: {last['type']} ({s_last['label']}). "
                    f"Distanza: {m_last['dist_str']}. Durata: {m_last['dur_str']}. "
                    f"Passo/Vel: {m_last['pace_str']}. Dislivello: {m_last['elev']}. "
                    f"FC Media: {m_last['hr_avg']}, FC Max: {m_last['hr_max']}. "
                    f"Watt: {m_last['watts']}. TSS: {last['tss']:.1f}. "
                    f"CTL attuale: {current_ctl:.1f}, TSB: {current_tsb:.1f}, ATL: {current_atl:.1f}. "
                    f"Stato forma: {status_label}."
                )
                prompt = (
                    "Sei un coach sportivo di alto livello. "
                    "Commenta questa sessione: qualità dell'allenamento, punti di forza e debolezze, "
                    "come influisce sul carico settimanale, e suggerisci cosa fare nella prossima sessione "
                    "in base allo stato di forma attuale. Sii specifico e pratico. Usa massimo 4 paragrafi."
                )
                result = genai.GenerativeModel(sel_model).generate_content(f"{ctx}\n\n{prompt}").text
                st.info(result)
            except Exception as e:
                st.error(f"Errore AI: {e}")

        # --- Grafico CTL/ATL/TSB ---
        st.divider()
        st.markdown("### 📈 Andamento Fitness")
        chart_df = pd.DataFrame({
            "Fitness (CTL)": ctl_daily,
            "Fatica (ATL)":  atl_daily,
            "Forma (TSB)":   tsb_daily,
        }).dropna().tail(120)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["Fitness (CTL)"],
                                  name="CTL", line=dict(color="#2196F3", width=2.5), fill="tozeroy",
                                  fillcolor="rgba(33,150,243,0.08)"))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["Fatica (ATL)"],
                                  name="ATL", line=dict(color="#FF9800", width=2)))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["Forma (TSB)"],
                                  name="TSB", line=dict(color="#4CAF50", width=2, dash="dot")))
        fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)", line_width=1)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=1.1),
            margin=dict(l=0, r=0, t=30, b=0), height=300,
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ============================================================
    # STATO FISICO
    # ============================================================
    elif menu == "💪 Stato Fisico":
        st.markdown("## 💪 Analisi Stato Fisico Attuale")

        # KPI principali
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("CTL — Fitness",  f"{current_ctl:.1f}", help="42 giorni. >60 = buon livello")
        c2.metric("ATL — Fatica",   f"{current_atl:.1f}", help="7 giorni. Alto = stanco")
        c3.metric("TSB — Forma",    f"{current_tsb:.1f}", help="-10/+10 = zona ottimale")
        # Monotonia: std / media TSS ultimi 7gg
        tss7 = df["tss"].tail(7)
        monotonia = tss7.mean() / tss7.std() if tss7.std() > 0 else 0
        c4.metric("Monotonia", f"{monotonia:.2f}", help="<2 = variazione sana. >2 = troppa routine")

        # Stato forma card
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,{status_color}22,{status_color}08);
                    border:1px solid {status_color}55; border-radius:16px; padding:20px; margin:16px 0;">
            <div style="font-size:28px; font-weight:800; color:{status_color}">{status_label}</div>
            <div style="color:#ccc; margin-top:8px; font-size:15px">
                TSB = {current_tsb:.1f} &nbsp;|&nbsp; CTL = {current_ctl:.1f} &nbsp;|&nbsp; ATL = {current_atl:.1f}
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Grafici CTL/ATL/TSB + TSS giornaliero
        col_left, col_right = st.columns([2, 1])

        with col_left:
            st.markdown("#### Andamento 90 giorni")
            chart_df = pd.DataFrame({
                "CTL": ctl_daily, "ATL": atl_daily, "TSB": tsb_daily
            }).dropna().tail(90)

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                row_heights=[0.65, 0.35], vertical_spacing=0.05)
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["CTL"],
                                      name="CTL", line=dict(color="#2196F3", width=2.5),
                                      fill="tozeroy", fillcolor="rgba(33,150,243,0.07)"), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["ATL"],
                                      name="ATL", line=dict(color="#FF9800", width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["TSB"],
                                      name="TSB", line=dict(color="#4CAF50", width=2, dash="dot")), row=1, col=1)
            fig.add_hrect(y0=-10, y1=10, fillcolor="rgba(76,175,80,0.06)", line_width=0, row=1, col=1)

            tss_bar = tss_daily.tail(90)
            colors  = ["#e94560" if v > 80 else "#FF9800" if v > 50 else "#4CAF50" for v in tss_bar.values]
            fig.add_trace(go.Bar(x=tss_bar.index, y=tss_bar.values,
                                  name="TSS/giorno", marker_color=colors, opacity=0.8), row=2, col=1)
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               height=400, margin=dict(l=0, r=0, t=10, b=0),
                               legend=dict(orientation="h", y=1.05),
                               xaxis2=dict(gridcolor="rgba(255,255,255,0.05)"),
                               yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                               yaxis2=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown("#### Zone FC — ultimi 30gg")
            df30 = df[df["start_date"] >= (df["start_date"].max() - timedelta(days=30))]
            df30 = df30[df30["zone_num"] > 0]
            if not df30.empty:
                zone_counts = df30.groupby(["zone_num", "zone_label", "zone_color"]).apply(
                    lambda x: x["moving_time"].sum() / 3600
                ).reset_index(name="ore")
                zone_counts = zone_counts.sort_values("zone_num")
                fig_z = go.Figure(go.Bar(
                    x=zone_counts["ore"],
                    y=zone_counts["zone_label"],
                    orientation="h",
                    marker_color=zone_counts["zone_color"],
                    text=[f"{v:.1f}h" for v in zone_counts["ore"]],
                    textposition="outside",
                ))
                fig_z.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                     height=220, margin=dict(l=0, r=60, t=0, b=0),
                                     xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                     showlegend=False)
                st.plotly_chart(fig_z, use_container_width=True)
                total_z = zone_counts["ore"].sum()
                z12 = zone_counts[zone_counts["zone_num"] <= 2]["ore"].sum()
                z45 = zone_counts[zone_counts["zone_num"] >= 4]["ore"].sum()
                pol = z12 / total_z * 100 if total_z > 0 else 0
                st.metric("Allenamento bassa intensità", f"{pol:.0f}%",
                           help="Ideale >75% (allenamento polarizzato)")
            else:
                st.info("Dati FC non disponibili")

            st.markdown("#### Trend Volume (km/settimana)")
            df_weekly = df.copy()
            df_weekly["week"] = df_weekly["start_date"].dt.to_period("W").dt.start_time
            weekly_km = df_weekly.groupby("week")["distance"].sum() / 1000
            weekly_km = weekly_km.tail(12)
            fig_w = go.Figure(go.Bar(
                x=weekly_km.index, y=weekly_km.values,
                marker_color="#2196F3", opacity=0.8,
            ))
            fig_w.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  height=180, margin=dict(l=0, r=0, t=0, b=0),
                                  xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%d/%m"),
                                  yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig_w, use_container_width=True)

        st.divider()

        # --- AI Analisi stato fisico + Piano 7 giorni ---
        col_ai1, col_ai2 = st.columns(2)

        with col_ai1:
            st.markdown("#### 🤖 Analisi Stato Fisico")
            with st.spinner("Analisi in corso..."):
                try:
                    # Trend CTL ultimi 30gg
                    ctl_30ago = ctl_daily.iloc[-30] if len(ctl_daily) >= 30 else ctl_daily.iloc[0]
                    trend = "crescente" if current_ctl > ctl_30ago else "decrescente"
                    df_sport = df.tail(20)["type"].value_counts().to_dict()

                    ctx_fitness = (
                        f"CTL (fitness): {current_ctl:.1f} (trend {trend} rispetto a 30gg fa: {ctl_30ago:.1f}). "
                        f"ATL (fatica acuta): {current_atl:.1f}. TSB (forma): {current_tsb:.1f}. "
                        f"Monotonia allenamento: {monotonia:.2f}. "
                        f"Sport più praticati (ultimi 20): {df_sport}. "
                        f"Ore in Z1-Z2 ultimi 30gg: {z12 if 'z12' in dir() else 'N/A'}h. "
                        f"% allenamento bassa intensità: {pol:.0f}% {'N/A' if 'pol' not in dir() else ''}."
                    )
                    prompt_fitness = (
                        "Sei un coach sportivo con competenze in fisiologia dell'esercizio. "
                        "Analizza in dettaglio lo stato fisico dell'atleta: "
                        "interpreta CTL/ATL/TSB, commenta la distribuzione delle intensità, "
                        "identifica se c'è rischio di overtraining o undertraining, "
                        "e descrivi il trend di allenamento degli ultimi 30 giorni. "
                        "Sii preciso e usa termini tecnici. Max 4 paragrafi."
                    )
                    result_fit = genai.GenerativeModel(sel_model).generate_content(
                        f"{ctx_fitness}\n\n{prompt_fitness}"
                    ).text
                    st.info(result_fit)
                except Exception as e:
                    st.error(f"Errore AI: {e}")

        with col_ai2:
            st.markdown("#### 🗓️ Piano Allenamento AI — Prossimi 7 giorni")

            goal = st.selectbox("Obiettivo:", [
                "Mantenimento forma", "Aumentare il fitness (CTL)", "Recupero / scarico",
                "Preparazione gara (entro 2 settimane)", "Base aerobica"
            ], key="goal_select")

            if st.button("🔄 Genera Piano", use_container_width=True):
                with st.spinner("Il coach sta pianificando..."):
                    try:
                        ctx_plan = (
                            f"CTL: {current_ctl:.1f}, ATL: {current_atl:.1f}, TSB: {current_tsb:.1f}. "
                            f"FC max atleta: {u['fc_max']}, FTP: {u['ftp']}W. "
                            f"Sport principale: {df['type'].value_counts().index[0] if not df.empty else 'Running'}. "
                            f"Obiettivo atleta: {goal}."
                        )
                        prompt_plan = (
                            "Crea un piano di allenamento per i prossimi 7 giorni. "
                            "Per ogni giorno indica: tipo di sessione, durata, intensità (zona FC o % FTP), "
                            "obiettivo fisiologico. Se è un giorno di riposo, indica il perché. "
                            "Formatta come lista numerata, un giorno per riga, con tutti i dettagli pratici. "
                            "Considera lo stato di forma attuale per calibrare il carico."
                        )
                        result_plan = genai.GenerativeModel(sel_model).generate_content(
                            f"{ctx_plan}\n\n{prompt_plan}"
                        ).text
                        st.session_state["piano_7gg"] = result_plan
                    except Exception as e:
                        st.error(f"Errore AI: {e}")

            if "piano_7gg" in st.session_state:
                st.success(st.session_state["piano_7gg"])

    # ============================================================
    # CALENDARIO
    # ============================================================
    elif menu == "📅 Calendario":
        st.markdown("## 📅 Calendario Allenamenti")

        # Filtri sport a pulsanti
        all_sports = sorted(df["type"].unique().tolist())
        if st.session_state.sport_filter is None:
            st.session_state.sport_filter = set(all_sports)

        st.markdown("**Filtra per sport:**")
        btn_cols = st.columns(min(len(all_sports), 8))
        for i, sport in enumerate(all_sports):
            si = get_sport_info(sport)
            is_active = sport in st.session_state.sport_filter
            label = f"{si['icon']} {si['label']}"
            with btn_cols[i % len(btn_cols)]:
                if st.button(
                    label,
                    key=f"sport_btn_{sport}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    sf = st.session_state.sport_filter
                    if sport in sf:
                        sf.discard(sport)
                    else:
                        sf.add(sport)
                    st.rerun()

        col_all, col_none = st.columns([1, 6])
        with col_all:
            if st.button("✅ Tutti", use_container_width=True):
                st.session_state.sport_filter = set(all_sports)
                st.rerun()
        with col_none:
            pass

        df_filtered = df[df["type"].isin(st.session_state.sport_filter)]

        st.divider()

        # Calendario + statistiche mensili
        col_cal, col_stats = st.columns([3, 1])

        with col_cal:
            events = []
            for _, row in df_filtered.iterrows():
                si = get_sport_info(row["type"])
                events.append({
                    "title":           f"{si['icon']} {row['distance']/1000:.1f}km",
                    "start":           row["start_date"].isoformat(),
                    "backgroundColor": si["color"],
                    "borderColor":     si["color"],
                    "textColor":       "#ffffff",
                })
            calendar(events=events, options={
                "initialView": "dayGridMonth",
                "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,listWeek"},
                "height": 550,
            })

        with col_stats:
            st.markdown("#### 📊 Questo mese")
            now      = datetime.now()
            df_month = df_filtered[
                (df_filtered["start_date"].dt.month == now.month) &
                (df_filtered["start_date"].dt.year  == now.year)
            ]
            st.metric("Sessioni",    len(df_month))
            st.metric("Km totali",   f"{df_month['distance'].sum()/1000:.1f}")
            st.metric("Ore totali",  f"{df_month['moving_time'].sum()/3600:.1f}")
            st.metric("TSS mese",    f"{df_month['tss'].sum():.0f}")
            st.metric("Dislivello",  f"{(df_month['total_elevation_gain'].sum() or 0):.0f} m")

            st.markdown("#### Sport praticati")
            sport_m = df_month["type"].value_counts()
            for sp, cnt in sport_m.items():
                si = get_sport_info(sp)
                st.markdown(f"{si['icon']} **{si['label']}**: {cnt}")

            st.divider()
            st.markdown("#### 📅 Mese precedente")
            prev_month = now.month - 1 if now.month > 1 else 12
            prev_year  = now.year if now.month > 1 else now.year - 1
            df_prev = df_filtered[
                (df_filtered["start_date"].dt.month == prev_month) &
                (df_filtered["start_date"].dt.year  == prev_year)
            ]
            st.metric("Sessioni",   len(df_prev))
            st.metric("Km totali",  f"{df_prev['distance'].sum()/1000:.1f}")
            st.metric("Ore totali", f"{df_prev['moving_time'].sum()/3600:.1f}")

        st.divider()
        st.markdown("#### 📋 Lista Attività")

        # Heatmap consistenza annuale
        st.markdown("#### 🟩 Consistenza Annuale")
        df_heat = df.copy()
        df_heat["date"] = df_heat["start_date"].dt.date
        days_with_activity = set(df_heat["date"].astype(str).tolist())
        today = datetime.now().date()
        year_start = today.replace(month=1, day=1)
        heat_html = '<div style="display:flex; flex-wrap:wrap; gap:2px; margin:8px 0">'
        d = year_start
        week_cols = []
        current_week = []
        while d <= today:
            ds = str(d)
            has = ds in days_with_activity
            color = "#4CAF50" if has else "#1e1e2e"
            border = "#4CAF5055" if has else "#333"
            current_week.append(f'<div title="{ds}" style="width:14px;height:14px;border-radius:3px;background:{color};border:1px solid {border}"></div>')
            if d.weekday() == 6:
                week_cols.append("".join(current_week))
                current_week = []
            d += timedelta(days=1)
        if current_week:
            week_cols.append("".join(current_week))

        heat_html = '<div style="display:flex; gap:3px">'
        for w in week_cols:
            heat_html += f'<div style="display:flex; flex-direction:column; gap:2px">{w}</div>'
        heat_html += "</div>"

        streak = 0
        d = today
        while str(d) in days_with_activity:
            streak += 1
            d -= timedelta(days=1)

        total_days = (today - year_start).days + 1
        active_days = sum(1 for dd in days_with_activity if str(year_start) <= dd <= str(today))

        col_h1, col_h2, col_h3 = st.columns(3)
        col_h1.metric("🔥 Streak attuale", f"{streak} giorni")
        col_h2.metric("📅 Giorni attivi (anno)", active_days)
        col_h3.metric("📊 % Consistenza", f"{active_days/total_days*100:.0f}%")
        st.markdown(heat_html, unsafe_allow_html=True)

    # ============================================================
    # COACH CHAT
    # ============================================================
    elif menu == "💬 Coach Chat":
        st.markdown("## 💬 Parla con il tuo Coach")

        col_btn, _ = st.columns([1, 5])
        with col_btn:
            if st.button("🗑️ Pulisci", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        if prompt := st.chat_input("Chiedi al tuo coach..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            system_ctx = (
                f"Sei un coach sportivo esperto, preciso e motivante. "
                f"Dati atleta: peso {u['peso']}kg, FC riposo {u['fc_min']}, "
                f"FC max {u['fc_max']}, FTP {u['ftp']}W. "
                f"Stato attuale: CTL {current_ctl:.1f}, ATL {current_atl:.1f}, TSB {current_tsb:.1f}. "
                f"Forma: {status_label}. "
                f"Attività totali: {len(df)}. Sport più praticato: {df['type'].value_counts().index[0]}. "
                f"Ultima sessione: {df.iloc[-1]['type']} — {df.iloc[-1]['distance']/1000:.1f}km."
            )
            try:
                res = genai.GenerativeModel(sel_model).generate_content(
                    system_ctx + "\n\nDomanda dell'atleta: " + prompt
                ).text
            except Exception as e:
                res = f"⚠️ Errore: {e}"

            with st.chat_message("assistant"):
                st.markdown(res)
            st.session_state.messages.append({"role": "assistant", "content": res})

    # ============================================================
    # RECORD PERSONALI
    # ============================================================
    elif menu == "🏅 Record Personali":
        st.markdown("## 🏅 Record Personali")

        sports_available = df["type"].value_counts().index.tolist()
        selected_pr_sport = st.selectbox(
            "Sport:", sports_available,
            format_func=lambda x: f"{get_sport_info(x)['icon']} {get_sport_info(x)['label']}"
        )
        df_s = df[df["type"] == selected_pr_sport].copy()

        if df_s.empty:
            st.info("Nessuna attività per questo sport.")
        else:
            st.divider()
            col1, col2, col3, col4 = st.columns(4)

            # Distanza massima
            best_dist = df_s.loc[df_s["distance"].idxmax()]
            col1.metric("📏 Distanza Massima",
                         f"{best_dist['distance']/1000:.2f} km",
                         help=f"{best_dist['name']} — {best_dist['start_date'].strftime('%d/%m/%Y')}")

            # Dislivello massimo
            best_elev = df_s.loc[df_s["total_elevation_gain"].fillna(0).idxmax()]
            col2.metric("⛰️ Dislivello Max",
                         f"{best_elev['total_elevation_gain']:.0f} m",
                         help=f"{best_elev['name']} — {best_elev['start_date'].strftime('%d/%m/%Y')}")

            # TSS massimo (sessione più dura)
            best_tss = df_s.loc[df_s["tss"].idxmax()]
            col3.metric("🔥 TSS Massimo",
                         f"{best_tss['tss']:.1f}",
                         help=f"{best_tss['name']} — {best_tss['start_date'].strftime('%d/%m/%Y')}")

            # Sessione più lunga (tempo)
            best_time = df_s.loc[df_s["moving_time"].idxmax()]
            hrs = int(best_time["moving_time"] // 3600)
            mins = int((best_time["moving_time"] % 3600) // 60)
            col4.metric("⏱️ Sessione più lunga",
                         f"{hrs}h {mins:02d}m",
                         help=f"{best_time['name']} — {best_time['start_date'].strftime('%d/%m/%Y')}")

            st.divider()

            # Passo/Velocità best per distanza
            if selected_pr_sport in ("Run", "TrailRun", "Hike", "Walk"):
                st.markdown("#### 🏆 Miglior Passo per Distanza")
                pace_cols = st.columns(4)
                for i, (dist_thr, label) in enumerate([(5, "5 km"), (10, "10 km"), (21.097, "Mezza"), (42.195, "Maratona")]):
                    filtered = df_s[df_s["distance"] >= dist_thr * 1000]
                    if not filtered.empty:
                        # Passo migliore = più veloce = min moving_time/distance
                        filtered = filtered.copy()
                        filtered["pace_sec_km"] = filtered["moving_time"] / (filtered["distance"] / 1000)
                        best = filtered.loc[filtered["pace_sec_km"].idxmin()]
                        pace_val = best["pace_sec_km"]
                        pace_cols[i].metric(
                            f"🏃 {label}",
                            f"{int(pace_val // 60)}:{int(pace_val % 60):02d} /km",
                            help=f"{best['name']} — {best['start_date'].strftime('%d/%m/%Y')}"
                        )
                    else:
                        pace_cols[i].metric(f"🏃 {label}", "N/A")

            elif selected_pr_sport in ("Ride", "VirtualRide", "MountainBikeRide"):
                st.markdown("#### 🏆 Velocità Massima Media")
                speed_cols = st.columns(3)
                for i, (dist_thr, label) in enumerate([(20, "20 km"), (50, "50 km"), (100, "100 km")]):
                    filtered = df_s[df_s["distance"] >= dist_thr * 1000].copy()
                    if not filtered.empty:
                        filtered["speed"] = filtered["distance"] / filtered["moving_time"] * 3.6
                        best = filtered.loc[filtered["speed"].idxmax()]
                        speed_cols[i].metric(f"🚴 {label}", f"{best['speed']:.1f} km/h",
                                              help=f"{best['name']} — {best['start_date'].strftime('%d/%m/%Y')}")
                    else:
                        speed_cols[i].metric(f"🚴 {label}", "N/A")

            st.divider()

            # Andamento nel tempo
            st.markdown("#### 📈 Evoluzione Distanza nel Tempo")
            fig_pr = go.Figure()
            fig_pr.add_trace(go.Scatter(
                x=df_s["start_date"],
                y=df_s["distance"] / 1000,
                mode="markers+lines",
                marker=dict(color=get_sport_info(selected_pr_sport)["color"], size=7),
                line=dict(color=get_sport_info(selected_pr_sport)["color"], width=1.5, dash="dot"),
                name="Distanza (km)",
            ))
            # Running max
            df_s_cummax = df_s.set_index("start_date")["distance"].cummax() / 1000
            fig_pr.add_trace(go.Scatter(
                x=df_s_cummax.index, y=df_s_cummax.values,
                mode="lines", line=dict(color="#FFD700", width=2),
                name="Record storico", fill="tonexty", fillcolor="rgba(255,215,0,0.05)"
            ))
            fig_pr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                   height=300, margin=dict(l=0, r=0, t=10, b=0),
                                   xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                   yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig_pr, use_container_width=True)

            # Tabella top 10
            st.markdown("#### 📋 Top 10 Sessioni per Distanza")
            top10 = df_s.nlargest(10, "distance")[
                ["start_date", "name", "distance", "moving_time", "total_elevation_gain", "tss"]
            ].copy()
            top10["Km"]       = (top10["distance"] / 1000).round(2)
            top10["Durata"]   = top10["moving_time"].apply(
                lambda x: f"{int(x//3600)}h {int((x%3600)//60):02d}m")
            top10["Dislivello"] = top10["total_elevation_gain"].fillna(0).round(0).astype(int)
            top10["Data"]     = top10["start_date"].dt.strftime("%d/%m/%Y")
            st.dataframe(
                top10[["Data", "name", "Km", "Durata", "Dislivello", "tss"]].rename(
                    columns={"name": "Nome", "tss": "TSS"}
                ),
                use_container_width=True, hide_index=True
            )

    # ============================================================
    # PROFILO FISICO
    # ============================================================
    elif menu == "👤 Profilo Fisico":
        st.markdown("## 👤 Parametri Atleta")

        if athlete:
            col_a, col_b = st.columns([1, 4])
            with col_a:
                if athlete.get("profile_medium"):
                    st.image(athlete["profile_medium"], width=80)
            with col_b:
                st.markdown(f"**{athlete.get('firstname','')} {athlete.get('lastname','')}**")
                st.markdown(f"📍 {athlete.get('city','')}, {athlete.get('country','')}")
                st.markdown(f"🏆 Follower: {athlete.get('follower_count', 'N/A')}")

        st.divider()
        st.info("Questi parametri influenzano il calcolo del TSS e tutti i valori di fitness.")

        with st.form("settings"):
            col1, col2 = st.columns(2)
            with col1:
                peso   = st.number_input("⚖️ Peso (kg)",     value=float(u["peso"]),       min_value=30.0,  max_value=200.0)
                fc_min = st.number_input("💚 FC a Riposo",   value=int(u["fc_min"]),        min_value=30,    max_value=100)
            with col2:
                fc_max = st.number_input("❤️ FC Massima",    value=int(u["fc_max"]),        min_value=100,   max_value=250)
                ftp    = st.number_input("⚡ FTP (Watt)",    value=int(u.get("ftp", 200)), min_value=50,    max_value=600,
                                          help="Functional Threshold Power — per TSS in bici")
            if st.form_submit_button("💾 Aggiorna Parametri", use_container_width=True):
                st.session_state.user_data = {"peso": peso, "fc_min": fc_min, "fc_max": fc_max, "ftp": ftp}
                st.cache_data.clear()
                st.success("✅ Salvato! Il fitness verrà ricalcolato.")
                st.rerun()

        st.divider()
        st.markdown("### 📈 Riepilogo Stagione")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Attività",     len(df))
        c2.metric("Km Totali",    f"{df['distance'].sum()/1000:.0f}")
        c3.metric("Ore Totali",   f"{df['moving_time'].sum()/3600:.0f}")
        c4.metric("Dislivello",   f"{df['total_elevation_gain'].sum()/1000:.0f} k m")
        c5.metric("TSS Totale",   f"{df['tss'].sum():.0f}")

        sport_df = df["type"].value_counts().reset_index()
        sport_df.columns = ["Sport", "Conteggio"]
        sport_df["Label"] = sport_df["Sport"].apply(
            lambda x: f"{get_sport_info(x)['icon']} {get_sport_info(x)['label']}")
        fig_sport = px.pie(sport_df, names="Label", values="Conteggio",
                            color_discrete_sequence=px.colors.qualitative.Set3, hole=0.4)
        fig_sport.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  height=300, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_sport, use_container_width=True)

# ============================================================
# LOGIN
# ============================================================
else:
    st.markdown("""
    <div style="text-align:center; padding: 80px 20px">
        <div style="font-size:64px">🏆</div>
        <h1 style="font-size:42px; font-weight:900; margin:16px 0">Elite AI Coach Pro</h1>
        <p style="color:#888; font-size:18px; max-width:500px; margin:0 auto 32px">
            Analisi avanzata delle performance, coaching AI personalizzato<br>
            e monitoraggio del fitness basato sui tuoi dati Strava.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([2, 1, 2])
    with col_c:
        url = (
            f"https://www.strava.com/oauth/authorize"
            f"?client_id={CLIENT_ID}&response_type=code"
            f"&redirect_uri={REDIRECT_URI}"
            f"&scope=read,activity:read_all&approval_prompt=force"
        )
        st.link_button("🔗 Connetti Strava", url, use_container_width=True)
