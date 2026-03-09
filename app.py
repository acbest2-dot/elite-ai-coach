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
# 6b. METRICHE AVANZATE — TIER 1 + TIER 3
# ============================================================

def calc_trimp(row, u):
    """
    TRIMP (Training Impulse) — Banister 1991.
    Formula: durata(min) × ΔHR × 0.64×e^(1.92×ΔHR_ratio)
    dove ΔHR = (HR_media - HR_riposo) / (HR_max - HR_riposo)
    """
    hr    = row.get("average_heartrate")
    dur   = row["moving_time"] / 60
    fc_r  = u["fc_min"]
    fc_m  = u["fc_max"]
    if pd.notna(hr) and fc_m > fc_r and hr > fc_r:
        delta_hr = (hr - fc_r) / (fc_m - fc_r)
        delta_hr = max(0.0, min(delta_hr, 1.0))
        return dur * delta_hr * 0.64 * np.exp(1.92 * delta_hr)
    return dur * 0.3  # fallback conservativo

def calc_acwr(df_sorted):
    """
    ACWR = TSS_7gg / TSS_28gg_media_rolling
    Restituisce il valore corrente (ultimo).
    Safe zone: 0.8–1.3. Danger zone: >1.5
    """
    daily = df_sorted.groupby(df_sorted["start_date"].dt.date)["tss"].sum()
    daily.index = pd.to_datetime(daily.index)
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)

    atl_7  = daily.rolling(7,  min_periods=1).mean()
    ctl_28 = daily.rolling(28, min_periods=1).mean()
    acwr   = atl_7 / ctl_28.replace(0, np.nan)
    return float(acwr.iloc[-1]) if not acwr.empty else 0.0, acwr

def calc_ramp_rate(ctl_daily):
    """
    Ramp Rate = variazione CTL negli ultimi 7 giorni.
    Ideale: +3/+7 per settimana. >+8 = rischio infortuni.
    """
    if len(ctl_daily) < 8:
        return 0.0
    return float(ctl_daily.iloc[-1] - ctl_daily.iloc[-8])

def calc_monotony(df_sorted, days=7):
    """
    Monotonia = media_TSS / std_TSS (ultimi N giorni).
    <1.5 = ottimo. 1.5–2 = attenzione. >2 = rischio overtraining.
    """
    daily = df_sorted.groupby(df_sorted["start_date"].dt.date)["tss"].sum()
    daily.index = pd.to_datetime(daily.index)
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)
    recent = daily.tail(days)
    std = recent.std()
    return float(recent.mean() / std) if std > 0 else 0.0

def calc_training_strain(df_sorted, days=7):
    """
    Training Strain = Monotonia × TSS_totale_7gg.
    Indice di stress cumulativo (Banister). >2000 = zona critica.
    """
    daily = df_sorted.groupby(df_sorted["start_date"].dt.date)["tss"].sum()
    daily.index = pd.to_datetime(daily.index)
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0)
    recent = daily.tail(days)
    mono = calc_monotony(df_sorted, days)
    return float(recent.sum() * mono)

def calc_ef_series(df_sorted):
    """
    Efficiency Factor per attività aerobiche.
    EF = velocità_m_s / FC_media  (running) oppure watt / FC_media (bici).
    Trend crescente = miglioramento aerobico.
    """
    ef_list = []
    for _, row in df_sorted.iterrows():
        hr = row.get("average_heartrate")
        if not pd.notna(hr) or hr == 0:
            ef_list.append(np.nan)
            continue
        if row["type"] in ("Ride", "VirtualRide", "MountainBikeRide"):
            w = row.get("average_watts")
            ef_list.append(float(w) / float(hr) if pd.notna(w) and w > 0 else np.nan)
        else:
            dist = row["distance"]
            t    = row["moving_time"]
            speed_ms = dist / t if t > 0 else 0
            ef_list.append(speed_ms / hr if hr > 0 else np.nan)
    return ef_list

def calc_vo2max_estimate(df_sorted):
    """
    Stima VO2max con formula di Jack Daniels (VDOT approach) sulle ultime corse.
    VO2max ≈ (-4.60 + 0.182258*(dist_m/time_min) + 0.000104*(dist_m/time_min)^2) /
              (0.8 + 0.1894393*e^(-0.012778*time_min) + 0.2989558*e^(-0.1932605*time_min))
    Usa le attività Run con distanza ≥ 5 km e FC media disponibile.
    """
    runs = df_sorted[
        (df_sorted["type"].isin(["Run", "TrailRun"])) &
        (df_sorted["distance"] >= 5000)
    ].copy()
    if runs.empty:
        return None, None

    best_vo2 = 0
    best_row = None
    for _, row in runs.iterrows():
        dist_m   = row["distance"]
        time_min = row["moving_time"] / 60
        if time_min <= 0:
            continue
        vel = dist_m / time_min  # m/min
        pct_vo2 = 0.8 + 0.1894393 * np.exp(-0.012778 * time_min) + \
                  0.2989558 * np.exp(-0.1932605 * time_min)
        vo2  = (-4.60 + 0.182258 * vel + 0.000104 * vel**2)
        vo2max = vo2 / pct_vo2 if pct_vo2 > 0 else 0
        if vo2max > best_vo2:
            best_vo2 = vo2max
            best_row = row
    return round(best_vo2, 1) if best_vo2 > 0 else None, best_row

def predict_race_times(vo2max):
    """
    Stima tempi di gara da VO2max usando le tabelle VDOT di Daniels.
    Formula inversa approssimata per ogni distanza.
    """
    if not vo2max or vo2max <= 0:
        return {}
    # Formula approssimata: pace_min_km = a + b/vo2max
    races = {
        "5 km":     {"dist": 5.0,    "a": 1.60, "b": 220},
        "10 km":    {"dist": 10.0,   "a": 1.65, "b": 280},
        "Mezza":    {"dist": 21.097, "a": 1.70, "b": 310},
        "Maratona": {"dist": 42.195, "a": 1.80, "b": 380},
    }
    results = {}
    for label, p in races.items():
        pace_sec_km = (p["a"] + p["b"] / vo2max) * 60
        total_sec   = pace_sec_km * p["dist"]
        h = int(total_sec // 3600)
        m = int((total_sec % 3600) // 60)
        s = int(total_sec % 60)
        time_str  = f"{h}h {m:02d}m {s:02d}s" if h > 0 else f"{m}:{s:02d}"
        pace_str  = f"{int(pace_sec_km // 60)}:{int(pace_sec_km % 60):02d} /km"
        results[label] = {"time": time_str, "pace": pace_str}
    return results

def calc_variability_index(row):
    """
    Variability Index = NP / AP (Normalized Power / Average Power).
    Disponibile solo per bici con watt.
    <1.05 = costante; >1.15 = variabile/nervoso.
    """
    np_val  = row.get("normalized_power")
    ap_val  = row.get("average_watts")
    if pd.notna(np_val) and pd.notna(ap_val) and ap_val > 0:
        return round(float(np_val) / float(ap_val), 3)
    return None

# ============================================================
# 6c. DIZIONARIO TOOLTIP METRICHE
# ============================================================
METRIC_INFO = {
    "TSS": {
        "nome": "Training Stress Score",
        "desc": "Misura lo stress fisiologico di una singola sessione integrando durata e intensità. Sviluppato da Andrew Coggan.",
        "range": "0–50: recupero facile | 50–100: medio | 100–150: difficile | >150: molto duro (giorni di recupero necessari)",
        "fonte": "Coggan & Allen — Training and Racing with a Power Meter",
    },
    "CTL": {
        "nome": "Chronic Training Load (Fitness)",
        "desc": "Media esponenziale a 42 giorni del TSS giornaliero. Rappresenta il tuo livello di fitness cronico e capacità di lavoro.",
        "range": "<40: principiante/recupero | 40–60: buona base | 60–80: atleta allenato | 80–100: atleta avanzato | >100: elite",
        "fonte": "Modello PMC (Performance Management Chart) — Banister 1991",
    },
    "ATL": {
        "nome": "Acute Training Load (Fatica)",
        "desc": "Media esponenziale a 7 giorni del TSS. Rappresenta la fatica accumulata nell'ultima settimana. Valore alto = sei stanco.",
        "range": "Confronta con CTL: ATL > CTL = accumulo fatica. La differenza determina il TSB.",
        "fonte": "Modello PMC — Banister 1991",
    },
    "TSB": {
        "nome": "Training Stress Balance (Forma)",
        "desc": "TSB = CTL - ATL. Indica il bilanciamento tra fitness e fatica. Positivo = riposato. Negativo = affaticato.",
        "range": "> +25: detrain/troppo riposo | +10/+25: fresco per gara | -10/+10: zona ottimale allenamento | -20/-10: accumulo | < -20: rischio overtraining",
        "fonte": "Coggan — TrainingPeaks Performance Management",
    },
    "TRIMP": {
        "nome": "Training Impulse",
        "desc": "Metrica di carico allenamento basata su FC, durata e intensità relativa. Precede il TSS ed è indipendente da potenza o GPS.",
        "range": "Dipende dalla durata. 100 TRIMP ≈ sessione di 1h a Z3. Usa il trend storico come riferimento personale.",
        "fonte": "Banister et al. — A systems model of training, physical performance and retention (1975)",
    },
    "ACWR": {
        "nome": "Acute:Chronic Workload Ratio",
        "desc": "Rapporto tra carico degli ultimi 7 giorni e media degli ultimi 28. Indicatore di rischio infortuni (studi su atleti elite).",
        "range": "< 0.8: undertraining | 0.8–1.3: zona sicura ✅ | 1.3–1.5: attenzione ⚠️ | > 1.5: danger zone 🔴 rischio infortuni elevato",
        "fonte": "Gabbett TJ — British Journal of Sports Medicine 2016 | Malone et al. IJSPP 2017",
    },
    "RAMP_RATE": {
        "nome": "Ramp Rate (CTL settimanale)",
        "desc": "Variazione del CTL negli ultimi 7 giorni. Indica quanto velocemente sta crescendo il tuo fitness.",
        "range": "< 3: crescita lenta/riposo | 3–7: progressione ideale ✅ | > 8: rischio overtraining ⚠️ | > 10: pericolo 🔴",
        "fonte": "TrainingPeaks — Performance Management Chart guidelines",
    },
    "MONOTONIA": {
        "nome": "Monotonia dell'Allenamento",
        "desc": "Media TSS / Deviazione standard TSS degli ultimi 7 giorni. Misura quanto è vario il tuo allenamento. Troppa uniformità = rischio.",
        "range": "< 1.5: variazione sana ✅ | 1.5–2.0: attenzione ⚠️ | > 2.0: rischio overtraining anche con carichi moderati 🔴",
        "fonte": "Foster C. — Journal of Strength and Conditioning Research 1998",
    },
    "STRAIN": {
        "nome": "Training Strain",
        "desc": "Monotonia × TSS_totale_settimanale. Indice di stress cumulativo che combina volume e uniformità dell'allenamento.",
        "range": "< 1000: basso | 1000–2000: moderato | > 2000: elevato/critico 🔴",
        "fonte": "Foster C. — JSCR 1998 | Banister training model",
    },
    "EF": {
        "nome": "Efficiency Factor (Indice di Efficienza Aerobica)",
        "desc": "Velocità (m/s) diviso FC media (corsa) oppure Watt / FC (bici). Trend crescente = migliori adattamenti aerobici.",
        "range": "Corsa: EF ~0.010–0.017 m/s per bpm. Bici: EF ~1.5–2.5 W/bpm. Il valore assoluto dipende dall'atleta — conta il miglioramento nel tempo.",
        "fonte": "Joe Friel — Training Bible | Coggan normalized metrics",
    },
    "VO2MAX": {
        "nome": "VO2max Stimato",
        "desc": "Massimo consumo di ossigeno, indicatore fondamentale del fitness cardiovascolare. Stimato da pace e durata delle tue corse migliori (formula Daniels/VDOT).",
        "range": "< 35: sedentario | 35–45: nella media | 45–55: buono | 55–65: molto buono | > 65: atleta d'élite",
        "fonte": "Daniels J. — Daniels' Running Formula (VDOT tables) | Nes et al. 2011",
    },
    "VI": {
        "nome": "Variability Index (solo bici con potenza)",
        "desc": "Normalized Power / Average Power. Misura quanto è stato uniforme lo sforzo. Valore basso = corsa costante ed efficiente.",
        "range": "1.00–1.05: costante/pianura ✅ | 1.05–1.10: leggermente variabile | 1.10–1.15: misto | > 1.15: molto variabile/nervoso",
        "fonte": "Coggan & Allen — Training and Racing with a Power Meter",
    },
    "POL": {
        "nome": "Distribuzione Polarizzata",
        "desc": "% del tempo trascorso in bassa intensità (Z1-Z2). La ricerca mostra che gli atleti endurance d'élite trascorrono ~80% in Z1-Z2 e ~20% in Z4-Z5.",
        "range": "< 60%: troppo sforzo a media intensità (zona grigia) | 60–75%: accettabile | > 75%: distribuzione polarizzata ottimale ✅",
        "fonte": "Seiler S. — International Journal of Sports Physiology and Performance 2010",
    },
}

def metric_tooltip(key):
    """Renderizza un expander piccolo con le info sulla metrica."""
    info = METRIC_INFO.get(key)
    if not info:
        return
    with st.expander(f"ℹ️ Cos'è?", expanded=False):
        st.markdown(f"**{info['nome']}**")
        st.markdown(info["desc"])
        st.markdown(f"📊 **Range tipici:** {info['range']}")
        st.markdown(f"📚 *Fonte: {info['fonte']}*")

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
# 9. FETCH — Paginazione completa (tutte le attività)
# ============================================================
@st.cache_data(ttl=1800, show_spinner=False)   # cache 30 min — storico cambia poco
def fetch_all_activities(access_token: str) -> list:
    """
    Scarica TUTTE le attività con paginazione.
    Strava restituisce max 200 per pagina.
    Si ferma quando arriva una pagina vuota.
    """
    all_acts = []
    page     = 1
    headers  = {"Authorization": f"Bearer {access_token}"}
    while True:
        r = requests.get(
            f"https://www.strava.com/api/v3/athlete/activities"
            f"?per_page=200&page={page}",
            headers=headers,
        )
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:          # pagina vuota → abbiamo tutto
            break
        all_acts.extend(batch)
        if len(batch) < 200:   # ultima pagina parziale
            break
        page += 1
    return all_acts

@st.cache_data(ttl=300, show_spinner=False)
def fetch_activities(access_token: str) -> list:
    """Manteniamo questo alias per compatibilità — chiama la versione paginata."""
    return fetch_all_activities(access_token)

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
    athlete      = fetch_athlete(access_token)

    # Primo caricamento: mostra indicatore di avanzamento
    if "activities_loaded" not in st.session_state:
        with st.spinner("⏳ Scaricamento storico completo da Strava (potrebbe richiedere 20-40 secondi al primo accesso)..."):
            raw = fetch_all_activities(access_token)
        st.session_state.activities_loaded = True
    else:
        raw = fetch_all_activities(access_token)

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

    # ---- METRICHE AVANZATE ----
    df["trimp"]      = df.apply(lambda row: calc_trimp(row, u), axis=1)
    acwr_val, acwr_series = calc_acwr(df)
    ramp_rate        = calc_ramp_rate(ctl_daily)
    monotonia        = calc_monotony(df)
    strain_val       = calc_training_strain(df)
    df["ef"]         = calc_ef_series(df)
    vo2max_val, _    = calc_vo2max_estimate(df)
    race_preds       = predict_race_times(vo2max_val)
    df["vi"]         = df.apply(calc_variability_index, axis=1)

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
            "📈 Recap",
            "📅 Calendario",
            "💬 Coach Chat",
            "🏅 Record Personali",
            "👤 Profilo Fisico",
        ], label_visibility="collapsed")

        st.divider()
        # Modelli disponibili — lista curata con fallback all'auto-discovery
        AVAILABLE_MODELS = [
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ]
        try:
            discovered_raw = [m.name for m in genai.list_models()
                               if "generateContent" in m.supported_generation_methods
                               and "gemini" in m.name]
            # Normalizza: rimuovi prefisso "models/" che alcune versioni API restituiscono
            discovered = [m.replace("models/", "") for m in discovered_raw]
            # Unisci lista curata + scoperta, rimuovi duplicati mantenendo ordine
            all_models = AVAILABLE_MODELS + [m for m in discovered if m not in AVAILABLE_MODELS]
        except Exception:
            all_models = AVAILABLE_MODELS

        # Prova a recuperare l'ultimo modello usato
        default_idx = 0
        if "sel_model" in st.session_state and st.session_state.sel_model in all_models:
            default_idx = all_models.index(st.session_state.sel_model)

        sel_model = st.selectbox("🧠 Modello AI:", all_models, index=default_idx,
                                  help="gemini-1.5-flash/pro: stabile. gemini-2.0: più recente ma con quote più basse.")
        st.session_state.sel_model = sel_model

        # Wrapper chiamata AI — gestisce automaticamente il prefisso corretto
        def ai_generate(prompt: str) -> str:
            try:
                return ai_generate(prompt)
            except Exception:
                # Fallback: prova con prefisso models/
                try:
                    return genai.GenerativeModel(f"models/{sel_model}").generate_content(prompt).text
                except Exception as e2:
                    raise e2

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

        # --- Recap ultimi 7 giorni ---
        st.markdown("### 📅 Recap Ultimi 7 Giorni")
        df7 = df[df["start_date"] >= (df["start_date"].max() - timedelta(days=7))]

        r7c1, r7c2, r7c3, r7c4, r7c5, r7c6 = st.columns(6)
        r7c1.metric("Sessioni",    len(df7))
        r7c2.metric("Km totali",   f"{df7['distance'].sum()/1000:.1f}")
        r7c3.metric("Ore totali",  f"{df7['moving_time'].sum()/3600:.1f}")
        r7c4.metric("TSS totale",  f"{df7['tss'].sum():.0f}")
        r7c5.metric("Dislivello",  f"{(df7['total_elevation_gain'].sum() or 0):.0f} m")
        avg_hr_7 = df7["average_heartrate"].dropna()
        r7c6.metric("FC media",    f"{avg_hr_7.mean():.0f} bpm" if not avg_hr_7.empty else "N/A")

        # Barra sport della settimana
        if not df7.empty:
            sport_7 = df7["type"].value_counts()
            sport_labels = [f"{get_sport_info(s)['icon']} {get_sport_info(s)['label']}" for s in sport_7.index]
            fig_7d = go.Figure()
            for i, (sp, cnt) in enumerate(sport_7.items()):
                si = get_sport_info(sp)
                df7_sp = df7[df7["type"] == sp]
                km = df7_sp["distance"].sum() / 1000
                tss_sp = df7_sp["tss"].sum()
                fig_7d.add_trace(go.Bar(
                    name=f"{si['icon']} {si['label']}",
                    x=[f"{si['icon']} {si['label']}"],
                    y=[df7_sp["moving_time"].sum() / 3600],
                    marker_color=si["color"],
                    text=[f"{km:.1f}km<br>TSS {tss_sp:.0f}"],
                    textposition="inside",
                    insidetextanchor="middle",
                ))
            fig_7d.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                height=160, margin=dict(l=0, r=0, t=10, b=0),
                showlegend=False, barmode="group",
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="ore"),
            )
            col_bar7, col_days7 = st.columns([2, 1])
            with col_bar7:
                st.plotly_chart(fig_7d, use_container_width=True)
            with col_days7:
                # Mini calendario settimanale
                st.markdown("<div style='font-size:13px;color:#888;margin-bottom:6px'>Giorni attivi</div>", unsafe_allow_html=True)
                today = datetime.now().date()
                week_html = "<div style='display:flex;gap:6px;margin-top:4px'>"
                giorni = ["L","M","M","G","V","S","D"]
                for i in range(6, -1, -1):
                    d = today - timedelta(days=i)
                    active = not df7[df7["start_date"].dt.date == d].empty
                    bg = "#4CAF50" if active else "rgba(255,255,255,0.07)"
                    border = "#4CAF50" if active else "rgba(255,255,255,0.1)"
                    week_html += (
                        f"<div style='width:32px;height:32px;border-radius:8px;"
                        f"background:{bg};border:1px solid {border};"
                        f"display:flex;align-items:center;justify-content:center;"
                        f"font-size:11px;color:{'#fff' if active else '#555'}'>"
                        f"{giorni[d.weekday()]}</div>"
                    )
                week_html += "</div>"
                st.markdown(week_html, unsafe_allow_html=True)

                # Confronto con settimana precedente
                df_prev7 = df[
                    (df["start_date"] >= (df["start_date"].max() - timedelta(days=14))) &
                    (df["start_date"] <  (df["start_date"].max() - timedelta(days=7)))
                ]
                delta_km  = df7["distance"].sum()/1000 - df_prev7["distance"].sum()/1000
                delta_tss = df7["tss"].sum() - df_prev7["tss"].sum()
                st.markdown(f"<div style='font-size:12px;color:#888;margin-top:10px'>vs settimana prec.</div>", unsafe_allow_html=True)
                km_color  = "#4CAF50" if delta_km  >= 0 else "#F44336"
                tss_color = "#4CAF50" if delta_tss >= 0 else "#F44336"
                st.markdown(
                    f"<span style='color:{km_color};font-size:13px'>{delta_km:+.1f} km</span> &nbsp; "
                    f"<span style='color:{tss_color};font-size:13px'>{delta_tss:+.0f} TSS</span>",
                    unsafe_allow_html=True
                )

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
                result = ai_generate(f"{ctx}\n\n{prompt}")
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

        # ── Stato forma banner ──
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,{status_color}22,{status_color}08);
                    border:1px solid {status_color}55; border-radius:16px;
                    padding:18px 24px; margin-bottom:20px; display:flex; align-items:center; gap:16px">
            <div style="font-size:36px">{status_label.split()[0]}</div>
            <div>
                <div style="font-size:22px; font-weight:800; color:{status_color}">{' '.join(status_label.split()[1:])}</div>
                <div style="color:#aaa; font-size:14px; margin-top:2px">
                    CTL {current_ctl:.1f} &nbsp;·&nbsp; ATL {current_atl:.1f} &nbsp;·&nbsp; TSB {current_tsb:.1f}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── BLOCCO 1: Metriche PMC classiche ──
        # ── Commento AI automatico ──
        with st.spinner("🤖 Il coach sta valutando il tuo stato..."):
            try:
                ctl_30ago  = ctl_daily.iloc[-30] if len(ctl_daily) >= 30 else ctl_daily.iloc[0]
                trend_ctl  = "in crescita" if current_ctl > ctl_30ago else "in calo"
                df_sport_r = df.tail(14)["type"].value_counts().to_dict()
                ctx_quick  = (
                    f"CTL={current_ctl:.1f} ({trend_ctl} rispetto a 30gg fa: {ctl_30ago:.1f}), "
                    f"ATL={current_atl:.1f}, TSB={current_tsb:.1f}, ACWR={acwr_val:.2f}, "
                    f"Ramp Rate={ramp_rate:+.1f}, Monotonia={monotonia:.2f}, Strain={strain_val:.0f}. "
                    f"VO2max stimato: {vo2max_val if vo2max_val else 'N/D'} ml/kg/min. "
                    f"Sport ultimi 14gg: {df_sport_r}."
                )
                prompt_quick = (
                    "Sei un coach sportivo d'élite. In 3-4 frasi dirette e concrete, "
                    "dammi un giudizio immediato sullo stato fisico attuale di questo atleta: "
                    "cosa sta andando bene, cosa richiede attenzione, e il consiglio più importante per questa settimana. "
                    "Tono professionale ma diretto. No elenchi puntati, solo testo fluido."
                )
                quick_summary = ai_generate(f"{ctx_quick}\n\n{prompt_quick}")
                st.markdown(f"""
                <div style="background:rgba(33,150,243,0.08); border-left:3px solid #2196F3;
                             border-radius:0 12px 12px 0; padding:14px 18px; margin-bottom:16px;">
                    <div style="font-size:12px;color:#2196F3;font-weight:700;margin-bottom:6px">🤖 VALUTAZIONE COACH</div>
                    <div style="color:#ddd;font-size:14px;line-height:1.6">{quick_summary}</div>
                </div>
                """, unsafe_allow_html=True)
            except Exception:
                pass  # Se fallisce non blocchiamo la pagina

        st.markdown("### 📊 Metriche PMC — Performance Management Chart")
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)

        with r1c1:
            st.metric("CTL — Fitness", f"{current_ctl:.1f}")
            metric_tooltip("CTL")
        with r1c2:
            st.metric("ATL — Fatica", f"{current_atl:.1f}")
            metric_tooltip("ATL")
        with r1c3:
            st.metric("TSB — Forma", f"{current_tsb:.1f}")
            metric_tooltip("TSB")
        with r1c4:
            trimp_7 = df["trimp"].tail(7).sum()
            st.metric("TRIMP (7gg)", f"{trimp_7:.0f}")
            metric_tooltip("TRIMP")

        st.divider()

        # ── BLOCCO 2: Metriche carico avanzate ──
        st.markdown("### ⚡ Carico & Rischio Infortuni")
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)

        # Colori ACWR
        if acwr_val < 0.8:    acwr_color, acwr_emoji = "#2196F3", "🔵"
        elif acwr_val <= 1.3: acwr_color, acwr_emoji = "#4CAF50", "🟢"
        elif acwr_val <= 1.5: acwr_color, acwr_emoji = "#FF9800", "🟡"
        else:                  acwr_color, acwr_emoji = "#F44336", "🔴"

        # Colori Ramp Rate
        if abs(ramp_rate) <= 3:   rr_color = "#2196F3"
        elif abs(ramp_rate) <= 7: rr_color = "#4CAF50"
        elif abs(ramp_rate) <= 10: rr_color = "#FF9800"
        else:                      rr_color = "#F44336"

        # Colori Monotonia
        if monotonia < 1.5:   mono_color = "#4CAF50"
        elif monotonia < 2.0: mono_color = "#FF9800"
        else:                  mono_color = "#F44336"

        # Colori Strain
        if strain_val < 1000:   strain_color = "#4CAF50"
        elif strain_val < 2000: strain_color = "#FF9800"
        else:                    strain_color = "#F44336"

        with r2c1:
            st.markdown(f"<div style='font-size:13px;color:#888'>ACWR</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{acwr_color}'>{acwr_emoji} {acwr_val:.2f}</div>",
                        unsafe_allow_html=True)
            metric_tooltip("ACWR")
        with r2c2:
            arrow = "↑" if ramp_rate > 0 else "↓"
            st.markdown(f"<div style='font-size:13px;color:#888'>Ramp Rate (7gg)</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{rr_color}'>{arrow} {ramp_rate:+.1f} CTL</div>",
                        unsafe_allow_html=True)
            metric_tooltip("RAMP_RATE")
        with r2c3:
            st.markdown(f"<div style='font-size:13px;color:#888'>Monotonia</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{mono_color}'>{monotonia:.2f}</div>",
                        unsafe_allow_html=True)
            metric_tooltip("MONOTONIA")
        with r2c4:
            st.markdown(f"<div style='font-size:13px;color:#888'>Training Strain</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{strain_color}'>{strain_val:.0f}</div>",
                        unsafe_allow_html=True)
            metric_tooltip("STRAIN")

        # Gauge ACWR
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=acwr_val,
            title={"text": "ACWR — Rischio Infortuni", "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, 2.0], "tickwidth": 1},
                "bar":  {"color": acwr_color, "thickness": 0.25},
                "steps": [
                    {"range": [0,   0.8], "color": "rgba(33,150,243,0.15)"},
                    {"range": [0.8, 1.3], "color": "rgba(76,175,80,0.15)"},
                    {"range": [1.3, 1.5], "color": "rgba(255,152,0,0.15)"},
                    {"range": [1.5, 2.0], "color": "rgba(244,67,54,0.15)"},
                ],
                "threshold": {"line": {"color": "#fff", "width": 2}, "thickness": 0.75, "value": acwr_val},
            },
            number={"font": {"size": 32}, "suffix": ""},
        ))
        fig_gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=220,
                                 margin=dict(l=20, r=20, t=40, b=10),
                                 font={"color": "#ccc"})

        g_col, acwr_hist_col = st.columns([1, 2])
        with g_col:
            st.plotly_chart(fig_gauge, use_container_width=True)
        with acwr_hist_col:
            acwr_plot = acwr_series.tail(90).dropna()
            fig_acwr = go.Figure()
            fig_acwr.add_hrect(y0=0.8, y1=1.3, fillcolor="rgba(76,175,80,0.08)", line_width=0)
            fig_acwr.add_hrect(y0=1.3, y1=1.5, fillcolor="rgba(255,152,0,0.08)", line_width=0)
            fig_acwr.add_hrect(y0=1.5, y1=3.0, fillcolor="rgba(244,67,54,0.08)", line_width=0)
            acwr_fill = {"#4CAF50": "rgba(76,175,80,0.12)", "#FF9800": "rgba(255,152,0,0.12)",
                         "#F44336": "rgba(244,67,54,0.12)", "#2196F3": "rgba(33,150,243,0.12)"}.get(acwr_color, "rgba(150,150,150,0.12)")
            fig_acwr.add_trace(go.Scatter(x=acwr_plot.index, y=acwr_plot.values,
                                           line=dict(color=acwr_color, width=2),
                                           fill="tozeroy", fillcolor=acwr_fill,
                                           name="ACWR"))
            fig_acwr.add_hline(y=0.8, line_dash="dot", line_color="rgba(76,175,80,0.5)",  line_width=1)
            fig_acwr.add_hline(y=1.3, line_dash="dot", line_color="rgba(255,152,0,0.5)",  line_width=1)
            fig_acwr.add_hline(y=1.5, line_dash="dot", line_color="rgba(244,67,54,0.5)",  line_width=1)
            fig_acwr.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                    height=220, margin=dict(l=0, r=0, t=10, b=0),
                                    showlegend=False,
                                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0, max(2.0, acwr_plot.max()+0.2)]))
            st.markdown("<div style='font-size:13px;color:#888;margin-top:8px'>Storico ACWR — 90 giorni</div>", unsafe_allow_html=True)
            st.plotly_chart(fig_acwr, use_container_width=True)

        st.divider()

        # ── BLOCCO 3: CTL/ATL/TSB + TSS giornaliero ──
        st.markdown("### 📈 Andamento PMC — 90 giorni")
        chart_df = pd.DataFrame({
            "CTL": ctl_daily, "ATL": atl_daily, "TSB": tsb_daily
        }).dropna().tail(90)

        fig_pmc = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            row_heights=[0.65, 0.35], vertical_spacing=0.04,
                            subplot_titles=["CTL / ATL / TSB", "TSS giornaliero"])
        fig_pmc.add_trace(go.Scatter(x=chart_df.index, y=chart_df["CTL"],
                                  name="CTL", line=dict(color="#2196F3", width=2.5),
                                  fill="tozeroy", fillcolor="rgba(33,150,243,0.07)"), row=1, col=1)
        fig_pmc.add_trace(go.Scatter(x=chart_df.index, y=chart_df["ATL"],
                                  name="ATL", line=dict(color="#FF9800", width=2)), row=1, col=1)
        fig_pmc.add_trace(go.Scatter(x=chart_df.index, y=chart_df["TSB"],
                                  name="TSB", line=dict(color="#4CAF50", width=2, dash="dot")), row=1, col=1)
        fig_pmc.add_hrect(y0=-10, y1=10, fillcolor="rgba(76,175,80,0.05)", line_width=0, row=1, col=1)
        tss_bar = tss_daily.tail(90)
        bar_colors = ["#e94560" if v > 80 else "#FF9800" if v > 50 else "#4CAF50" for v in tss_bar.values]
        fig_pmc.add_trace(go.Bar(x=tss_bar.index, y=tss_bar.values,
                              name="TSS/giorno", marker_color=bar_colors, opacity=0.85), row=2, col=1)
        fig_pmc.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           height=420, margin=dict(l=0, r=0, t=30, b=0),
                           legend=dict(orientation="h", y=1.04),
                           xaxis2=dict(gridcolor="rgba(255,255,255,0.05)"),
                           yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                           yaxis2=dict(gridcolor="rgba(255,255,255,0.05)"))
        st.plotly_chart(fig_pmc, use_container_width=True)

        st.divider()

        # ── BLOCCO 4: Zone FC + Volume + EF ──
        st.markdown("### ❤️ Intensità, Volume & Efficienza Aerobica")
        col_z, col_vol, col_ef = st.columns(3)

        with col_z:
            st.markdown("**Zone FC — ultimi 30gg**")
            metric_tooltip("POL")
            df30 = df[df["start_date"] >= (df["start_date"].max() - timedelta(days=30))]
            df30 = df30[df30["zone_num"] > 0]
            z12, z45, pol = 0, 0, 0
            if not df30.empty:
                zone_counts = df30.groupby(["zone_num", "zone_label", "zone_color"]).apply(
                    lambda x: x["moving_time"].sum() / 3600
                ).reset_index(name="ore")
                zone_counts = zone_counts.sort_values("zone_num")
                fig_z = go.Figure(go.Bar(
                    x=zone_counts["ore"], y=zone_counts["zone_label"],
                    orientation="h", marker_color=zone_counts["zone_color"],
                    text=[f"{v:.1f}h" for v in zone_counts["ore"]], textposition="outside",
                ))
                fig_z.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                     height=200, margin=dict(l=0, r=60, t=0, b=0),
                                     xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                     showlegend=False)
                st.plotly_chart(fig_z, use_container_width=True)
                total_z = zone_counts["ore"].sum()
                z12 = zone_counts[zone_counts["zone_num"] <= 2]["ore"].sum()
                z45 = zone_counts[zone_counts["zone_num"] >= 4]["ore"].sum()
                pol = z12 / total_z * 100 if total_z > 0 else 0
                pol_color = "#4CAF50" if pol >= 75 else "#FF9800" if pol >= 60 else "#F44336"
                st.markdown(f"<span style='color:{pol_color};font-weight:700'>Bassa intensità: {pol:.0f}%</span> (target >75%)", unsafe_allow_html=True)
            else:
                st.info("Nessun dato FC disponibile")

        with col_vol:
            st.markdown("**Volume settimanale (km)**")
            df_weekly = df.copy()
            df_weekly["week"] = df_weekly["start_date"].dt.to_period("W").dt.start_time
            weekly_km = df_weekly.groupby("week")["distance"].sum() / 1000
            weekly_km = weekly_km.tail(12)
            avg_vol = weekly_km.mean()
            w_colors = ["#e94560" if v > avg_vol * 1.3 else "#2196F3" for v in weekly_km.values]
            fig_w = go.Figure(go.Bar(x=weekly_km.index, y=weekly_km.values,
                                      marker_color=w_colors, opacity=0.85))
            fig_w.add_hline(y=avg_vol, line_dash="dot", line_color="rgba(255,255,255,0.27)", line_width=1,
                             annotation_text=f"media {avg_vol:.0f}km", annotation_font_color="#aaa")
            fig_w.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  height=200, margin=dict(l=0, r=0, t=0, b=0),
                                  xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%d/%m"),
                                  yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig_w, use_container_width=True)

        with col_ef:
            st.markdown("**Efficiency Factor — trend**")
            metric_tooltip("EF")
            ef_data = df[df["ef"].notna()][["start_date", "ef", "type"]].tail(30)
            if not ef_data.empty:
                fig_ef = go.Figure()
                for sport_type in ef_data["type"].unique():
                    sub = ef_data[ef_data["type"] == sport_type]
                    fig_ef.add_trace(go.Scatter(
                        x=sub["start_date"], y=sub["ef"],
                        mode="markers+lines",
                        name=f"{get_sport_info(sport_type)['icon']} {get_sport_info(sport_type)['label']}",
                        line=dict(color=get_sport_info(sport_type)["color"], width=1.5),
                        marker=dict(size=6),
                    ))
                fig_ef.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      height=200, margin=dict(l=0, r=0, t=0, b=0),
                                      legend=dict(font=dict(size=10), orientation="h", y=1.15),
                                      xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                      yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
                st.plotly_chart(fig_ef, use_container_width=True)
                ef_trend = ef_data["ef"].iloc[-1] - ef_data["ef"].iloc[0] if len(ef_data) > 1 else 0
                ef_emoji = "📈" if ef_trend > 0 else "📉"
                st.markdown(f"{ef_emoji} Trend EF: **{ef_trend:+.4f}** negli ultimi {len(ef_data)} allenamenti")
            else:
                st.info("Dati FC non sufficienti per EF")

        st.divider()

        # ── BLOCCO 5: VO2max + Race Predictor + VI ──
        st.markdown("### 🔬 Capacità Aerobica & Performance")
        col_vo2, col_race, col_vi = st.columns(3)

        with col_vo2:
            st.markdown("**VO2max Stimato**")
            metric_tooltip("VO2MAX")
            if vo2max_val:
                # Colore in base al range
                if vo2max_val >= 65:   vo2_color, vo2_label = "#9C27B0", "🏆 Élite"
                elif vo2max_val >= 55: vo2_color, vo2_label = "#4CAF50", "🥇 Molto Buono"
                elif vo2max_val >= 45: vo2_color, vo2_label = "#2196F3", "🥈 Buono"
                elif vo2max_val >= 35: vo2_color, vo2_label = "#FF9800", "🥉 Nella Media"
                else:                   vo2_color, vo2_label = "#F44336", "📈 Da Migliorare"
                st.markdown(f"""
                <div style="background:{vo2_color}15; border:1px solid {vo2_color}44;
                             border-radius:12px; padding:16px; text-align:center;">
                    <div style="font-size:42px; font-weight:900; color:{vo2_color}">{vo2max_val}</div>
                    <div style="color:#aaa; font-size:12px">ml/kg/min</div>
                    <div style="color:{vo2_color}; font-size:14px; font-weight:700; margin-top:4px">{vo2_label}</div>
                </div>
                """, unsafe_allow_html=True)
                # Mini gauge VO2max — mostra solo il semicerchio, il numero è già nel card sopra
                fig_vo2 = go.Figure(go.Indicator(
                    mode="gauge",
                    value=vo2max_val,
                    gauge={
                        "axis": {"range": [20, 85]},
                        "bar":  {"color": vo2_color, "thickness": 0.3},
                        "steps": [
                            {"range": [20, 35], "color": "rgba(244,67,54,0.15)"},
                            {"range": [35, 45], "color": "rgba(255,152,0,0.15)"},
                            {"range": [45, 55], "color": "rgba(33,150,243,0.15)"},
                            {"range": [55, 65], "color": "rgba(76,175,80,0.15)"},
                            {"range": [65, 85], "color": "rgba(156,39,176,0.15)"},
                        ],
                    },
                ))
                fig_vo2.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=120,
                                       margin=dict(l=10, r=10, t=10, b=0),
                                       font={"color": "#ccc"})
                st.plotly_chart(fig_vo2, use_container_width=True)
            else:
                st.info("Servono almeno 1 corsa ≥5km con dati tempo per stimare il VO2max.")

        with col_race:
            st.markdown("**🏁 Race Time Predictor**")
            if race_preds:
                for dist_label, pred in race_preds.items():
                    st.markdown(f"""
                    <div style="display:flex; justify-content:space-between; align-items:center;
                                 background:rgba(255,255,255,0.03); border-radius:8px;
                                 padding:8px 12px; margin-bottom:6px;">
                        <span style="color:#aaa; font-size:14px">🏃 {dist_label}</span>
                        <span style="color:#e94560; font-weight:700; font-size:15px">{pred['time']}</span>
                        <span style="color:#666; font-size:12px">{pred['pace']}</span>
                    </div>
                    """, unsafe_allow_html=True)
                st.caption("⚠️ Stime basate su VO2max stimato (formula Daniels VDOT). Usa come riferimento indicativo.")
            else:
                st.info("Calcola il VO2max per ottenere le stime.")

        with col_vi:
            st.markdown("**Variability Index (bici)**")
            metric_tooltip("VI")
            vi_data = df[df["vi"].notna()][["start_date", "vi", "name"]].tail(20)
            if not vi_data.empty:
                vi_colors = ["#4CAF50" if v <= 1.05 else "#FF9800" if v <= 1.10 else "#F44336"
                              for v in vi_data["vi"]]
                fig_vi = go.Figure(go.Bar(
                    x=vi_data["start_date"], y=vi_data["vi"],
                    marker_color=vi_colors, opacity=0.85,
                    text=[f"{v:.3f}" for v in vi_data["vi"]], textposition="outside",
                ))
                fig_vi.add_hline(y=1.05, line_dash="dot", line_color="rgba(76,175,80,0.33)")
                fig_vi.add_hline(y=1.10, line_dash="dot", line_color="rgba(255,152,0,0.33)")
                fig_vi.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                      height=200, margin=dict(l=0, r=0, t=20, b=0),
                                      xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%d/%m"),
                                      yaxis=dict(gridcolor="rgba(255,255,255,0.05)", range=[0.95, max(1.25, vi_data["vi"].max()+0.05)]))
                st.plotly_chart(fig_vi, use_container_width=True)
                avg_vi = vi_data["vi"].mean()
                vi_label = "Costante ✅" if avg_vi <= 1.05 else "Variabile ⚠️" if avg_vi <= 1.10 else "Molto variabile 🔴"
                st.markdown(f"Media VI: **{avg_vi:.3f}** — {vi_label}")
            else:
                st.info("Nessuna attività in bici con dati di potenza normalizzata.")

        st.divider()

        # ── BLOCCO 6: AI Analisi completa + Piano 7gg ──
        st.markdown("### 🤖 Coaching AI Avanzato")
        col_ai1, col_ai2 = st.columns(2)

        with col_ai1:
            st.markdown("#### Analisi Fisiolologica Completa")
            if st.button("🔍 Genera Analisi", key="btn_analisi", use_container_width=True):
                with st.spinner("Analisi in corso..."):
                    try:
                        ctl_30ago = ctl_daily.iloc[-30] if len(ctl_daily) >= 30 else ctl_daily.iloc[0]
                        trend_ctl = "crescente" if current_ctl > ctl_30ago else "decrescente"
                        df_sport  = df.tail(20)["type"].value_counts().to_dict()
                        ctx_fitness = (
                            f"DATI ATLETA: CTL={current_ctl:.1f} (trend {trend_ctl}), "
                            f"ATL={current_atl:.1f}, TSB={current_tsb:.1f}. "
                            f"ACWR={acwr_val:.2f}, Ramp Rate={ramp_rate:+.1f}/settimana. "
                            f"Monotonia={monotonia:.2f}, Training Strain={strain_val:.0f}. "
                            f"VO2max stimato={vo2max_val if vo2max_val else 'N/D'} ml/kg/min. "
                            f"% allenamento bassa intensità (Z1-Z2)={pol:.0f}%. "
                            f"TRIMP ultimi 7gg={trimp_7:.0f}. "
                            f"Sport praticati={df_sport}."
                        )
                        prompt_fitness = (
                            "Sei un fisiolo dello sport e coach d'élite. "
                            "Fornisci un'analisi DETTAGLIATA e PROFESSIONALE dello stato fisico di questo atleta. "
                            "Struttura la risposta così: "
                            "1) Stato di forma attuale (interpreta CTL/ATL/TSB/ACWR), "
                            "2) Rischio overtraining/undertraining (monotonia, strain, ramp rate), "
                            "3) Qualità dell'allenamento (distribuzione intensità, EF), "
                            "4) Capacità aerobica (VO2max, implicazioni), "
                            "5) Raccomandazioni concrete per le prossime 2 settimane. "
                            "Usa terminologia tecnica. Sii diretto e specifico."
                        )
                        result_fit = ai_generate(f"{ctx_fitness}\n\n{prompt_fitness}")
                        st.session_state["analisi_fisica"] = result_fit
                    except Exception as e:
                        st.error(f"Errore AI: {e}")
            if "analisi_fisica" in st.session_state:
                st.info(st.session_state["analisi_fisica"])

        with col_ai2:
            st.markdown("#### 🗓️ Piano Allenamento — Prossimi 7 giorni")
            goal = st.selectbox("Obiettivo:", [
                "Mantenimento forma", "Aumentare il fitness (CTL)",
                "Recupero / scarico", "Preparazione gara (entro 2 settimane)", "Base aerobica"
            ], key="goal_select")
            if st.button("🔄 Genera Piano", use_container_width=True, key="btn_piano"):
                with st.spinner("Il coach sta pianificando..."):
                    try:
                        ctx_plan = (
                            f"CTL={current_ctl:.1f}, ATL={current_atl:.1f}, TSB={current_tsb:.1f}. "
                            f"ACWR={acwr_val:.2f}, Ramp Rate={ramp_rate:+.1f}. "
                            f"Monotonia={monotonia:.2f}, Strain={strain_val:.0f}. "
                            f"FC max={u['fc_max']}, FTP={u['ftp']}W. "
                            f"Sport principale: {df['type'].value_counts().index[0]}. "
                            f"% bassa intensità attuale: {pol:.0f}%. "
                            f"Obiettivo: {goal}."
                        )
                        prompt_plan = (
                            "Crea un piano di allenamento dettagliato per i prossimi 7 giorni. "
                            "Per ogni giorno: tipo sessione, durata precisa, intensità (zona FC o %FTP), "
                            "obiettivo fisiologico, note pratiche. "
                            "Calibra il carico considerando ACWR e TSB attuali. "
                            "Se ACWR > 1.3 riduci il volume. Se TSB < -20 inserisci più recupero. "
                            "Formato: Giorno N — [tipo]: descrizione dettagliata."
                        )
                        result_plan = ai_generate(f"{ctx_plan}\n\n{prompt_plan}")
                        st.session_state["piano_7gg"] = result_plan
                    except Exception as e:
                        st.error(f"Errore AI: {e}")
            if "piano_7gg" in st.session_state:
                st.success(st.session_state["piano_7gg"])

    # ============================================================
    # RECAP
    # ============================================================
    elif menu == "📈 Recap":
        st.markdown("## 📈 Recap Allenamenti")

        # ── Filtro sport ──
        all_sports_recap = sorted(df["type"].unique().tolist())
        st.markdown("**Filtra sport:**")
        if "recap_sport_filter" not in st.session_state:
            st.session_state.recap_sport_filter = set(all_sports_recap)

        btn_cols_r = st.columns(min(len(all_sports_recap), 9))
        for i, sport in enumerate(all_sports_recap):
            si = get_sport_info(sport)
            is_active = sport in st.session_state.recap_sport_filter
            with btn_cols_r[i % len(btn_cols_r)]:
                if st.button(
                    f"{si['icon']} {si['label']}", key=f"recap_btn_{sport}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    sf = st.session_state.recap_sport_filter
                    sf.discard(sport) if sport in sf else sf.add(sport)
                    st.rerun()

        col_all_r, _ = st.columns([1, 8])
        with col_all_r:
            if st.button("✅ Tutti", key="recap_all", use_container_width=True):
                st.session_state.recap_sport_filter = set(all_sports_recap)
                st.rerun()

        df_r = df[df["type"].isin(st.session_state.recap_sport_filter)].copy()

        st.divider()

        # ── Selezione periodo ──
        tab_week, tab_month, tab_year, tab_yoy = st.tabs([
            "📅 Settimana", "🗓️ Mese", "📆 Anno", "↔️ Anno su Anno"
        ])

        # ──────────────────────────────────────────────
        # HELPER: genera KPI cards + grafici per un df
        # ──────────────────────────────────────────────
        def recap_kpi_row(df_sub, label_periodo):
            """Mostra 6 KPI + delta vs periodo precedente."""
            n_sess  = len(df_sub)
            km      = df_sub["distance"].sum() / 1000
            ore     = df_sub["moving_time"].sum() / 3600
            tss_tot = df_sub["tss"].sum()
            elev    = df_sub["total_elevation_gain"].sum() or 0
            hr_vals = df_sub["average_heartrate"].dropna()
            fc_med  = hr_vals.mean() if not hr_vals.empty else None
            calorie = df_sub["kilojoules"].sum() or 0

            c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
            c1.metric("Sessioni",   n_sess)
            c2.metric("Km totali",  f"{km:.1f}")
            c3.metric("Ore",        f"{ore:.1f}")
            c4.metric("TSS",        f"{tss_tot:.0f}")
            c5.metric("Dislivello", f"{elev:.0f} m")
            c6.metric("FC media",   f"{fc_med:.0f} bpm" if fc_med else "N/A")
            c7.metric("Calorie",    f"{calorie:.0f} kcal" if calorie else "N/A")

        def sport_breakdown_chart(df_sub, height=200):
            """Grafico a torta + barre per sport."""
            if df_sub.empty:
                st.info("Nessuna attività nel periodo selezionato.")
                return
            grp = df_sub.groupby("type").agg(
                sessioni=("distance", "count"),
                km=("distance", lambda x: x.sum()/1000),
                ore=("moving_time", lambda x: x.sum()/3600),
                tss=("tss", "sum"),
            ).reset_index()
            grp["label"] = grp["type"].apply(lambda x: f"{get_sport_info(x)['icon']} {get_sport_info(x)['label']}")
            grp["color"] = grp["type"].apply(lambda x: get_sport_info(x)["color"])

            col_pie, col_bar = st.columns(2)
            with col_pie:
                fig_p = go.Figure(go.Pie(
                    labels=grp["label"], values=grp["ore"],
                    marker_colors=grp["color"].tolist(),
                    hole=0.5, textinfo="label+percent",
                    textfont_size=12,
                ))
                fig_p.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=height,
                                     margin=dict(l=0,r=0,t=10,b=0), showlegend=False,
                                     annotations=[dict(text="Ore", x=0.5, y=0.5,
                                                        font_size=14, showarrow=False, font_color="#aaa")])
                st.plotly_chart(fig_p, use_container_width=True)
            with col_bar:
                fig_b = go.Figure()
                fig_b.add_trace(go.Bar(name="Km", x=grp["label"], y=grp["km"],
                                        marker_color=grp["color"].tolist(), opacity=0.85,
                                        text=grp["km"].round(1), textposition="outside"))
                fig_b.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                     height=height, margin=dict(l=0,r=0,t=20,b=0),
                                     xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                     yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="km"),
                                     showlegend=False)
                st.plotly_chart(fig_b, use_container_width=True)

        def weekly_bars_chart(df_sub, n_weeks=12, height=220):
            """Barre volume settimanale con colori per sport."""
            if df_sub.empty: return
            df_w = df_sub.copy()
            df_w["week"] = df_w["start_date"].dt.to_period("W").dt.start_time
            sports_in_sub = df_w["type"].unique()
            fig = go.Figure()
            for sport in sports_in_sub:
                si  = get_sport_info(sport)
                sub = df_w[df_w["type"] == sport].groupby("week")["distance"].sum() / 1000
                sub = sub.reindex(
                    pd.date_range(df_w["week"].min(), df_w["week"].max(), freq="W-MON"),
                    fill_value=0
                ).tail(n_weeks)
                fig.add_trace(go.Bar(
                    name=f"{si['icon']} {si['label']}",
                    x=sub.index, y=sub.values,
                    marker_color=si["color"], opacity=0.85,
                ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                barmode="stack", height=height, margin=dict(l=0,r=0,t=10,b=0),
                legend=dict(orientation="h", y=1.1, font=dict(size=11)),
                xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%d/%m"),
                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="km"),
            )
            st.plotly_chart(fig, use_container_width=True)

        def activity_list_table(df_sub, n=10):
            """Tabella top N attività per distanza."""
            if df_sub.empty: return
            top = df_sub.nlargest(n, "distance")[
                ["start_date","type","name","distance","moving_time","total_elevation_gain","tss","average_heartrate"]
            ].copy()
            top["Sport"]      = top["type"].apply(lambda x: f"{get_sport_info(x)['icon']} {get_sport_info(x)['label']}")
            top["Data"]       = top["start_date"].dt.strftime("%d/%m/%Y")
            top["Km"]         = (top["distance"]/1000).round(2)
            top["Durata"]     = top["moving_time"].apply(lambda x: f"{int(x//3600)}h {int((x%3600)//60):02d}m")
            top["Dislivello"] = top["total_elevation_gain"].fillna(0).astype(int)
            top["FC"]         = top["average_heartrate"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "N/A")
            top["TSS"]        = top["tss"].round(1)
            st.dataframe(
                top[["Data","Sport","name","Km","Durata","Dislivello","FC","TSS"]].rename(columns={"name":"Nome"}),
                use_container_width=True, hide_index=True,
            )

        # ────────────────────────────────────
        # TAB 1 — SETTIMANA CORRENTE
        # ────────────────────────────────────
        with tab_week:
            now = datetime.now()
            # Lunedì della settimana corrente
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            df_week = df_r[df_r["start_date"] >= week_start]

            # Settimana precedente per delta
            prev_week_start = week_start - timedelta(weeks=1)
            df_prev_week    = df_r[(df_r["start_date"] >= prev_week_start) & (df_r["start_date"] < week_start)]

            st.markdown(f"#### Settimana {week_start.strftime('%d %b')} — {now.strftime('%d %b %Y')}")

            # KPI con delta
            n1,n2,n3,n4,n5,n6 = st.columns(6)
            def delta_str(curr, prev):
                d = curr - prev
                return f"{d:+.1f}" if abs(d) > 0.05 else None

            n1.metric("Sessioni",   len(df_week),
                      delta=str(len(df_week)-len(df_prev_week)) if len(df_prev_week) else None)
            n2.metric("Km",         f"{df_week['distance'].sum()/1000:.1f}",
                      delta=delta_str(df_week['distance'].sum()/1000, df_prev_week['distance'].sum()/1000))
            n3.metric("Ore",        f"{df_week['moving_time'].sum()/3600:.1f}",
                      delta=delta_str(df_week['moving_time'].sum()/3600, df_prev_week['moving_time'].sum()/3600))
            n4.metric("TSS",        f"{df_week['tss'].sum():.0f}",
                      delta=delta_str(df_week['tss'].sum(), df_prev_week['tss'].sum()))
            n5.metric("Dislivello", f"{(df_week['total_elevation_gain'].sum() or 0):.0f} m")
            hr_w = df_week["average_heartrate"].dropna()
            n6.metric("FC media",   f"{hr_w.mean():.0f} bpm" if not hr_w.empty else "N/A")

            if not df_week.empty:
                st.markdown("##### Distribuzione sport")
                sport_breakdown_chart(df_week, height=220)

                # Progress bar verso obiettivo settimanale (km)
                target_km = st.number_input("🎯 Obiettivo km settimana", value=50, min_value=0, step=5, key="target_km_w")
                curr_km   = df_week["distance"].sum() / 1000
                prog      = min(curr_km / target_km, 1.0) if target_km > 0 else 0
                prog_color = "#4CAF50" if prog >= 1 else "#FF9800" if prog >= 0.6 else "#2196F3"
                st.markdown(f"""
                <div style='margin:8px 0 4px'>
                    <div style='font-size:13px;color:#888'>Progressione km: {curr_km:.1f} / {target_km} km</div>
                    <div style='background:rgba(255,255,255,0.08);border-radius:8px;height:12px;margin-top:6px'>
                        <div style='background:{prog_color};width:{prog*100:.1f}%;height:12px;border-radius:8px;transition:width 0.4s'></div>
                    </div>
                </div>""", unsafe_allow_html=True)

                st.markdown("##### Attività della settimana")
                activity_list_table(df_week, n=20)
            else:
                st.info("Nessuna attività questa settimana.")

        # ────────────────────────────────────
        # TAB 2 — MESE CORRENTE
        # ────────────────────────────────────
        with tab_month:
            # Selezione mese
            available_months = df_r["start_date"].dt.to_period("M").unique()
            available_months_str = [str(m) for m in sorted(available_months, reverse=True)]
            sel_month = st.selectbox("Mese:", available_months_str, index=0, key="sel_month")
            sel_period = pd.Period(sel_month, "M")

            df_month_r = df_r[df_r["start_date"].dt.to_period("M") == sel_period]

            # Stesso mese anno precedente per confronto
            prev_year_period = pd.Period(f"{sel_period.year - 1}-{sel_period.month:02d}", "M")
            df_month_py      = df_r[df_r["start_date"].dt.to_period("M") == prev_year_period]

            st.markdown(f"#### {sel_period.strftime('%B %Y')}")

            m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
            km_m   = df_month_r["distance"].sum()/1000
            km_mpy = df_month_py["distance"].sum()/1000
            ore_m  = df_month_r["moving_time"].sum()/3600
            ore_mpy= df_month_py["moving_time"].sum()/3600
            tss_m  = df_month_r["tss"].sum()
            tss_mpy= df_month_py["tss"].sum()

            m1.metric("Sessioni",   len(df_month_r), delta=str(len(df_month_r)-len(df_month_py)) if not df_month_py.empty else None)
            m2.metric("Km",         f"{km_m:.1f}",   delta=f"{km_m-km_mpy:+.1f}" if not df_month_py.empty else None)
            m3.metric("Ore",        f"{ore_m:.1f}",  delta=f"{ore_m-ore_mpy:+.1f}" if not df_month_py.empty else None)
            m4.metric("TSS",        f"{tss_m:.0f}",  delta=f"{tss_m-tss_mpy:+.0f}" if not df_month_py.empty else None)
            m5.metric("Dislivello", f"{(df_month_r['total_elevation_gain'].sum() or 0):.0f} m")
            hr_mo = df_month_r["average_heartrate"].dropna()
            m6.metric("FC media",   f"{hr_mo.mean():.0f}" if not hr_mo.empty else "N/A")
            cal_mo = df_month_r["kilojoules"].sum() or 0
            m7.metric("Calorie",    f"{cal_mo:.0f}" if cal_mo else "N/A")

            if not df_month_r.empty:
                st.markdown("##### Distribuzione sport")
                sport_breakdown_chart(df_month_r, height=240)

                # Grafico giornaliero del mese
                st.markdown("##### Volume giornaliero (km)")
                df_daily_m = df_month_r.copy()
                df_daily_m["day"] = df_daily_m["start_date"].dt.date
                daily_km = df_daily_m.groupby(["day","type"])["distance"].sum().reset_index()
                daily_km["km"] = daily_km["distance"] / 1000
                fig_dm = go.Figure()
                for sport in daily_km["type"].unique():
                    si  = get_sport_info(sport)
                    sub = daily_km[daily_km["type"] == sport]
                    fig_dm.add_trace(go.Bar(
                        x=sub["day"], y=sub["km"],
                        name=f"{si['icon']} {si['label']}",
                        marker_color=si["color"], opacity=0.85,
                    ))
                fig_dm.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    barmode="stack", height=220, margin=dict(l=0,r=0,t=10,b=0),
                    legend=dict(orientation="h", y=1.1, font=dict(size=11)),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%d"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="km"),
                )
                st.plotly_chart(fig_dm, use_container_width=True)

                # Heatmap attività del mese
                st.markdown("##### Giorni di allenamento")
                import calendar as _cal
                first_wd, n_days = _cal.monthrange(sel_period.year, sel_period.month)
                active_days_m = set(df_month_r["start_date"].dt.day.tolist())
                cal_html = "<div style='display:flex;gap:3px;flex-wrap:wrap;margin:8px 0'>"
                # Offset lunedì
                for _ in range(first_wd):
                    cal_html += "<div style='width:32px;height:32px'></div>"
                for day in range(1, n_days + 1):
                    active = day in active_days_m
                    bg     = "#4CAF50" if active else "rgba(255,255,255,0.05)"
                    cal_html += (
                        f"<div style='width:32px;height:32px;border-radius:6px;"
                        f"background:{bg};display:flex;align-items:center;"
                        f"justify-content:center;font-size:11px;"
                        f"color:{'#fff' if active else '#555'}'>{day}</div>"
                    )
                cal_html += "</div>"
                c_cal, c_stat = st.columns([2,1])
                with c_cal:
                    st.markdown(cal_html, unsafe_allow_html=True)
                with c_stat:
                    st.metric("Giorni attivi", f"{len(active_days_m)} / {n_days}")
                    st.metric("% mese", f"{len(active_days_m)/n_days*100:.0f}%")
                    if not df_month_py.empty:
                        st.metric("vs stesso mese anno prec.", f"{len(active_days_m) - len(set(df_month_py['start_date'].dt.day.tolist())):+d} giorni")

                st.markdown("##### Top attività del mese")
                activity_list_table(df_month_r, n=10)
            else:
                st.info("Nessuna attività in questo mese.")

        # ────────────────────────────────────
        # TAB 3 — ANNO CORRENTE
        # ────────────────────────────────────
        with tab_year:
            available_years = sorted(df_r["start_date"].dt.year.unique(), reverse=True)
            sel_year = st.selectbox("Anno:", available_years, index=0, key="sel_year")
            df_year_r = df_r[df_r["start_date"].dt.year == sel_year]

            st.markdown(f"#### Anno {sel_year}")

            y1,y2,y3,y4,y5,y6,y7 = st.columns(7)
            km_y  = df_year_r["distance"].sum()/1000
            ore_y = df_year_r["moving_time"].sum()/3600
            tss_y = df_year_r["tss"].sum()
            elev_y= df_year_r["total_elevation_gain"].sum() or 0
            hr_y  = df_year_r["average_heartrate"].dropna()
            cal_y = df_year_r["kilojoules"].sum() or 0

            y1.metric("Sessioni",    len(df_year_r))
            y2.metric("Km totali",   f"{km_y:.0f}")
            y3.metric("Ore totali",  f"{ore_y:.0f}")
            y4.metric("TSS totale",  f"{tss_y:.0f}")
            y5.metric("Dislivello",  f"{elev_y/1000:.1f} km")
            y6.metric("FC media",    f"{hr_y.mean():.0f}" if not hr_y.empty else "N/A")
            y7.metric("Calorie",     f"{cal_y:.0f}" if cal_y else "N/A")

            if not df_year_r.empty:
                st.markdown("##### Distribuzione sport")
                sport_breakdown_chart(df_year_r, height=260)

                # Volume mensile per sport (barre stacked)
                st.markdown("##### Volume mensile (km)")
                df_year_r2 = df_year_r.copy()
                df_year_r2["month"] = df_year_r2["start_date"].dt.to_period("M").dt.start_time
                monthly = df_year_r2.groupby(["month","type"])["distance"].sum().reset_index()
                monthly["km"] = monthly["distance"] / 1000
                fig_my = go.Figure()
                for sport in monthly["type"].unique():
                    si  = get_sport_info(sport)
                    sub = monthly[monthly["type"] == sport]
                    fig_my.add_trace(go.Bar(
                        x=sub["month"], y=sub["km"],
                        name=f"{si['icon']} {si['label']}",
                        marker_color=si["color"], opacity=0.85,
                    ))
                fig_my.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    barmode="stack", height=280, margin=dict(l=0,r=0,t=10,b=0),
                    legend=dict(orientation="h", y=1.08, font=dict(size=11)),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat="%b"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="km"),
                )
                st.plotly_chart(fig_my, use_container_width=True)

                # Sessioni per settimana (heatmap stile GitHub)
                st.markdown("##### Heatmap attività annuale")
                year_start_d = datetime(sel_year, 1, 1).date()
                year_end_d   = datetime(sel_year, 12, 31).date()
                active_dates_y = set(df_year_r["start_date"].dt.date.astype(str).tolist())
                tss_by_date    = df_year_r.groupby(df_year_r["start_date"].dt.date.astype(str))["tss"].sum().to_dict()

                # Costruzione griglia ISO settimane
                d = year_start_d
                weeks_data: list = []
                current_wk: list = []
                wd_offset = d.weekday()
                for _ in range(wd_offset):
                    current_wk.append(None)
                while d <= year_end_d:
                    current_wk.append(d)
                    if d.weekday() == 6:
                        weeks_data.append(current_wk)
                        current_wk = []
                    d += timedelta(days=1)
                if current_wk:
                    weeks_data.append(current_wk)

                heat_html = "<div style='display:flex;gap:2px;overflow-x:auto'>"
                for week in weeks_data:
                    heat_html += "<div style='display:flex;flex-direction:column;gap:2px'>"
                    for day_d in week:
                        if day_d is None:
                            heat_html += "<div style='width:12px;height:12px'></div>"
                        else:
                            ds    = str(day_d)
                            tss_d = tss_by_date.get(ds, 0)
                            if tss_d == 0:      bg = "rgba(255,255,255,0.05)"
                            elif tss_d < 50:    bg = "#1b5e20"
                            elif tss_d < 100:   bg = "#388e3c"
                            elif tss_d < 150:   bg = "#66bb6a"
                            else:               bg = "#a5d6a7"
                            heat_html += (
                                f"<div title='{ds} — TSS {tss_d:.0f}' "
                                f"style='width:12px;height:12px;border-radius:2px;"
                                f"background:{bg}'></div>"
                            )
                    heat_html += "</div>"
                heat_html += "</div>"
                heat_html += """
                <div style='display:flex;gap:8px;align-items:center;margin-top:6px;font-size:11px;color:#666'>
                    <span>Meno</span>
                    <div style='width:12px;height:12px;border-radius:2px;background:rgba(255,255,255,0.05)'></div>
                    <div style='width:12px;height:12px;border-radius:2px;background:#1b5e20'></div>
                    <div style='width:12px;height:12px;border-radius:2px;background:#388e3c'></div>
                    <div style='width:12px;height:12px;border-radius:2px;background:#66bb6a'></div>
                    <div style='width:12px;height:12px;border-radius:2px;background:#a5d6a7'></div>
                    <span>Più TSS</span>
                </div>"""
                st.markdown(heat_html, unsafe_allow_html=True)

                # Medie mensili
                st.divider()
                st.markdown("##### Medie mensili")
                avg_sess = len(df_year_r) / 12
                avg_km   = km_y / 12
                avg_ore  = ore_y / 12
                avg_tss  = tss_y / 12
                a1,a2,a3,a4 = st.columns(4)
                a1.metric("Sessioni/mese", f"{avg_sess:.1f}")
                a2.metric("Km/mese",       f"{avg_km:.0f}")
                a3.metric("Ore/mese",      f"{avg_ore:.0f}")
                a4.metric("TSS/mese",      f"{avg_tss:.0f}")
            else:
                st.info(f"Nessuna attività nel {sel_year}.")

        # ────────────────────────────────────
        # TAB 4 — CONFRONTO ANNO SU ANNO
        # ────────────────────────────────────
        with tab_yoy:
            st.markdown("#### ↔️ Confronto Anno su Anno")
            available_years_yoy = sorted(df_r["start_date"].dt.year.unique(), reverse=True)

            if len(available_years_yoy) < 2:
                st.info("Servono almeno 2 anni di dati per il confronto.")
            else:
                col_y1, col_y2 = st.columns(2)
                with col_y1:
                    year_a = st.selectbox("Anno A:", available_years_yoy, index=0, key="yoy_a")
                with col_y2:
                    year_b = st.selectbox("Anno B:", available_years_yoy,
                                           index=min(1, len(available_years_yoy)-1), key="yoy_b")

                df_ya = df_r[df_r["start_date"].dt.year == year_a]
                df_yb = df_r[df_r["start_date"].dt.year == year_b]

                # KPI confronto
                def yoy_metric(label, val_a, val_b, fmt=".0f"):
                    delta = val_a - val_b
                    pct   = (delta / val_b * 100) if val_b else 0
                    color = "#4CAF50" if delta >= 0 else "#F44336"
                    return f"""
                    <div style='background:rgba(255,255,255,0.03);border-radius:10px;padding:12px;text-align:center'>
                        <div style='color:#888;font-size:12px'>{label}</div>
                        <div style='font-size:20px;font-weight:700;color:#fff'>{val_a:{fmt}}</div>
                        <div style='font-size:11px;color:#666'>{year_b}: {val_b:{fmt}}</div>
                        <div style='font-size:13px;font-weight:700;color:{color}'>{delta:+{fmt}} ({pct:+.1f}%)</div>
                    </div>"""

                st.markdown(f"### {year_a} vs {year_b}")
                cols_yoy = st.columns(5)
                metrics_yoy = [
                    ("Sessioni",    len(df_ya),                      len(df_yb),                      "d"),
                    ("Km totali",   df_ya["distance"].sum()/1000,    df_yb["distance"].sum()/1000,    ".0f"),
                    ("Ore totali",  df_ya["moving_time"].sum()/3600, df_yb["moving_time"].sum()/3600, ".0f"),
                    ("TSS totale",  df_ya["tss"].sum(),              df_yb["tss"].sum(),              ".0f"),
                    ("Dislivello",  df_ya["total_elevation_gain"].sum() or 0,
                                    df_yb["total_elevation_gain"].sum() or 0, ".0f"),
                ]
                for i, (label, va, vb, fmt) in enumerate(metrics_yoy):
                    cols_yoy[i].markdown(yoy_metric(label, va, vb, fmt), unsafe_allow_html=True)

                st.divider()

                # Grafico mensile sovrapposto — km
                st.markdown("##### Confronto volume mensile (km)")
                months_range = range(1, 13)
                months_label = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"]

                km_ya_m = [df_ya[df_ya["start_date"].dt.month == m]["distance"].sum()/1000 for m in months_range]
                km_yb_m = [df_yb[df_yb["start_date"].dt.month == m]["distance"].sum()/1000 for m in months_range]

                fig_yoy = go.Figure()
                fig_yoy.add_trace(go.Scatter(
                    x=months_label, y=km_ya_m, name=str(year_a),
                    line=dict(color="#e94560", width=2.5), mode="lines+markers",
                    fill="tozeroy", fillcolor="rgba(233,69,96,0.08)",
                ))
                fig_yoy.add_trace(go.Scatter(
                    x=months_label, y=km_yb_m, name=str(year_b),
                    line=dict(color="#2196F3", width=2, dash="dot"), mode="lines+markers",
                ))
                fig_yoy.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    height=280, margin=dict(l=0,r=0,t=10,b=0),
                    legend=dict(orientation="h", y=1.08),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="km"),
                )
                st.plotly_chart(fig_yoy, use_container_width=True)

                # Confronto TSS mensile
                st.markdown("##### Confronto TSS mensile")
                tss_ya_m = [df_ya[df_ya["start_date"].dt.month == m]["tss"].sum() for m in months_range]
                tss_yb_m = [df_yb[df_yb["start_date"].dt.month == m]["tss"].sum() for m in months_range]

                fig_tss_yoy = go.Figure()
                fig_tss_yoy.add_trace(go.Bar(x=months_label, y=tss_ya_m, name=str(year_a),
                                              marker_color="#e94560", opacity=0.8))
                fig_tss_yoy.add_trace(go.Bar(x=months_label, y=tss_yb_m, name=str(year_b),
                                              marker_color="#2196F3", opacity=0.6))
                fig_tss_yoy.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    barmode="group", height=240, margin=dict(l=0,r=0,t=10,b=0),
                    legend=dict(orientation="h", y=1.08),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="TSS"),
                )
                st.plotly_chart(fig_tss_yoy, use_container_width=True)

                # Sessioni per sport confronto
                st.markdown("##### Sessioni per sport")
                sports_union = set(df_ya["type"].unique()) | set(df_yb["type"].unique())
                sport_comp = []
                for sport in sports_union:
                    si = get_sport_info(sport)
                    sport_comp.append({
                        "Sport": f"{si['icon']} {si['label']}",
                        f"Sessioni {year_a}": len(df_ya[df_ya["type"]==sport]),
                        f"Km {year_a}":       round(df_ya[df_ya["type"]==sport]["distance"].sum()/1000, 1),
                        f"Sessioni {year_b}": len(df_yb[df_yb["type"]==sport]),
                        f"Km {year_b}":       round(df_yb[df_yb["type"]==sport]["distance"].sum()/1000, 1),
                    })
                sport_comp_df = pd.DataFrame(sport_comp).sort_values(f"Km {year_a}", ascending=False)
                st.dataframe(sport_comp_df, use_container_width=True, hide_index=True)

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
            border = "rgba(76,175,80,0.33)" if has else "#333"
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
                res = ai_generate(system_ctx + "\n\nDomanda dell'atleta: " + prompt)
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
