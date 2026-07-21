"""
Gold News Calendar Assistant with Desktop Notifications
==========================================================
วิธีรัน:
    pip install -r requirements.txt
    python -m streamlit run runtest.py

ข้อมูลข่าวเศรษฐกิจ: ForexFactory (ผ่าน JSON export feed, ไม่ต้องใช้ API key)
"""

import re
import time
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# พยายามใช้ streamlit-autorefresh ถ้าไม่มีให้ทำงานต่อได้แบบไม่ auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# st.fragment มีตั้งแต่ Streamlit >= 1.33
HAS_FRAGMENT = hasattr(st, "fragment")

THAI_TZ = timezone(timedelta(hours=7))
# MT4/MT5 Server ตั้งเป็น GMT+0 (UTC) ตามมาตรฐาน
MT4_MT5_TZ = timezone.utc

# ==========================================
# Timezone Configuration (International Standard)
# ==========================================
TIMEZONE_CONFIG = {
    "gmt": {
        "name": "GMT/Server 💻",
        "short": "GMT",
        "flag": "💻",
        "abbr": "gmt",
        "tz": MT4_MT5_TZ,
        "color": "#4D96FF",  # Blue
        "session": "Reference",
        "status_badge": "⚪",
        "priority": 1,
    },
    "tokyo": {
        "name": "Tokyo 🇯🇵",
        "short": "Tokyo",
        "flag": "🇯🇵",
        "abbr": "jp",
        "tz": timezone(timedelta(hours=9)),  
        "color": "#9D4EDD",  # Purple
        "session": "08:00-15:00 JST",
        "status_badge": "🟣",
        "priority": 2,
    },
    "singapore": {
        "name": "Singapore 🇸🇬",
        "short": "Singapore",
        "flag": "🇸🇬",
        "abbr": "sg",
        "tz": timezone(timedelta(hours=8)),
        "color": "#FF6B6B",  # Red-Orange
        "session": "08:00-17:00 SGT",
        "status_badge": "🟠",
        "priority": 3,
    },
    "london": {
        "name": "London 🇬🇧",
        "short": "London",
        "flag": "🇬🇧",
        "abbr": "uk",
        "tz": timezone(timedelta(hours=1)),
        "color": "#FF9500",  # Orange
        "session": "08:00-17:00 GMT",
        "status_badge": "🟢",  
        "priority": 4,
    },
    "newyork": {
        "name": "New York 🇺🇸",
        "short": "New York",
        "flag": "🇺🇸",
        "abbr": "ny",
        "tz": timezone(timedelta(hours=-4)),
        "color": "#FF3B30",  # Red
        "session": "13:30-20:00 GMT",
        "status_badge": "🔴",
        "priority": 5,
    },
    "sydney": {
        "name": "Sydney 🇦🇺",
        "short": "Sydney",
        "flag": "🇦🇺",
        "abbr": "syd",
        "tz": timezone(timedelta(hours=11)),
        "color": "#17C784",  # Green
        "session": "22:00-06:00 GMT",
        "status_badge": "🔵",
        "priority": 6,
    },
    "bangkok": {
        "name": "Bangkok 🇹🇭 (Home)",
        "short": "Bangkok",
        "flag": "🇹🇭",
        "abbr": "bkk",
        "tz": THAI_TZ,
        "color": "#FFD700",  # Gold
        "session": "24H (Reference)",
        "status_badge": "⭐",
        "priority": 0,
    },
}

DEFAULT_TIMEZONES = ["gmt", "tokyo", "london", "newyork"]
TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "CHF"]

CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", 
    "JPY": "🇯🇵", "CNY": "🇨🇳", "AUD": "🇦🇺", 
    "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿"
}

def get_currency_badge(currency: str) -> str:
    flag = CURRENCY_FLAGS.get(currency, "🏳️")
    return f"{flag} {clean_or_dash(currency)}"

CURRENCY_TIMEZONE_MAP = {
    "USD": {"zone": ZoneInfo("America/New_York"), "label": "New York"},
    "EUR": {"zone": ZoneInfo("Europe/Berlin"), "label": "Frankfurt"},
    "GBP": {"zone": ZoneInfo("Europe/London"), "label": "London"},
    "JPY": {"zone": ZoneInfo("Asia/Tokyo"), "label": "Tokyo"},
    "CNY": {"zone": ZoneInfo("Asia/Shanghai"), "label": "Shanghai"},
    "AUD": {"zone": ZoneInfo("Australia/Sydney"), "label": "Sydney"},
    "CAD": {"zone": ZoneInfo("America/Toronto"), "label": "Toronto"},
    "CHF": {"zone": ZoneInfo("Europe/Zurich"), "label": "Zurich"},
    "NZD": {"zone": ZoneInfo("Pacific/Auckland"), "label": "Auckland"},
}

SETTINGS_FILE = Path(__file__).resolve().parent / "user_settings.json"

SOUND_TONE_MAP = {
    "ทุ้ม (Low)": {"freq": 500, "double": False},
    "กลาง (Mid)": {"freq": 800, "double": False},
    "แหลม (High)": {"freq": 1200, "double": False},
    "สองจังหวะ (Double Beep)": {"freq": 800, "double": True},
}

DEFAULT_SETTINGS = {
    "selected_timezones": DEFAULT_TIMEZONES,
    "selected_currencies": TARGET_CURRENCIES,
    "enable_notifications": True,
    "enable_desktop_notif": True,
    "enable_sound_notif": True,
    "notify_upcoming": True,
    "notify_released": True,
    "auto_refresh_on": True,
    "refresh_seconds": 30,
    "sound_tone": "กลาง (Mid)",
    "sound_volume": 30,
}

def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for key in DEFAULT_SETTINGS:
            if key in saved:
                settings[key] = saved[key]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    settings["selected_timezones"] = [tz for tz in settings.get("selected_timezones", []) if tz in TIMEZONE_CONFIG] or DEFAULT_TIMEZONES
    settings["selected_currencies"] = [c for c in settings.get("selected_currencies", []) if c in TARGET_CURRENCIES] or TARGET_CURRENCIES
    
    refresh_val = settings.get("refresh_seconds", 30)
    if not isinstance(refresh_val, int) or not (10 <= refresh_val <= 120):
        settings["refresh_seconds"] = 30
        
    if settings.get("sound_tone") not in SOUND_TONE_MAP:
        settings["sound_tone"] = "กลาง (Mid)"
        
    vol_val = settings.get("sound_volume", DEFAULT_SETTINGS["sound_volume"])
    if isinstance(vol_val, float) and 0.0 <= vol_val <= 1.0:
        # ไฟล์ settings เก่าที่เก็บระดับเสียงเป็นสเกล 0.0-1.0 -> แปลงเป็นสเกล 0-100 อัตโนมัติ
        vol_val = round(vol_val * 100)
    if not isinstance(vol_val, (int, float)) or not (0 <= vol_val <= 100):
        vol_val = DEFAULT_SETTINGS["sound_volume"]
    settings["sound_volume"] = int(vol_val)

    return settings

def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

NEWS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ==========================================
# 1. การตั้งค่าหน้าเว็บ + CSS สำหรับ Notification
# ==========================================
st.set_page_config(page_title="Gold News", page_icon="🥇", layout="wide")

st.markdown(
    """
    <style>
    /* ฟอนต์ Prompt: เส้นกลม โมเดิร์น อ่านง่ายทั้งไทย+อังกฤษ นิยมใช้ในแดชบอร์ด/แอปการเงินยุคใหม่ */
    @import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"], .stApp, .stMarkdown, .stMetric,
    div[data-testid="stAppViewContainer"], section[data-testid="stSidebar"] {
        font-family: 'Prompt', 'Segoe UI', sans-serif;
        line-height: 1.65;               /* เว้นบรรทัดให้อ่านสบายตาขึ้น โดยเฉพาะข้อความไทย */
        letter-spacing: 0.01em;
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Prompt', sans-serif;
        font-weight: 600;
        letter-spacing: 0;                /* หัวข้อให้ตัวชิดกว่าปกติเล็กน้อย ดูคมและทันสมัยขึ้น */
        line-height: 1.3;
    }
    p, li, span, div { line-height: 1.6; }

    div[data-testid="stMetricValue"] {
        font-size: 1.6rem;
        font-weight: 600;
        font-variant-numeric: tabular-nums;  /* ตัวเลขความกว้างเท่ากัน อ่านง่ายเวลาตัวเลขเปลี่ยน */
        white-space: normal;      /* ไม่ตัดข้อความด้วย ... อีกต่อไป */
        overflow: visible;
        text-overflow: unset;
        line-height: 1.25;
        word-break: break-word;
    }
    div[data-testid="stMetricLabel"] { white-space: normal; font-weight: 500; }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .notification-pulse {
        animation: pulse 1s infinite;
    }
    
    .notification-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 5px solid #ffd700;
    }

    @media (max-width: 480px) {
        div[data-testid="stMetricValue"] { font-size: 1.15rem; }
        div[data-testid="stMetricLabel"] { font-size: 0.75rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ==========================================
# 2. JavaScript สำหรับ Browser Notification + เสียง
# ==========================================
NOTIFICATION_JS = """
<script>
// ขออนุญาต Notification
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// สำคัญ: ผูกทุกอย่างไว้กับ window.parent (หน้าเว็บจริงของ Streamlit) ไม่ใช่ window ของ
// iframe เล็ก ๆ นี้เอง เพราะทุกครั้งที่ Python เรียก st.components.v1.html(...) ใหม่
// (ตอนกดปุ่มทดสอบเสียง หรือตอน send_notification ทำงาน) จะได้ iframe ใหม่ที่มี window
// เป็นคนละตัวกันเสมอ ถ้าผูกฟังก์ชัน/audioCtx ไว้กับ window ของ iframe นี้ ฟังก์ชันจะถูก
// เรียกจาก iframe อื่นไม่ได้เลย -> เป็นสาเหตุหลักที่กดทดสอบเสียงแล้วไม่มีเสียงออกมา
const hostWindow = window.parent || window;

let audioCtx;
function initAudio() {
    if (!audioCtx) {
        audioCtx = new (hostWindow.AudioContext || hostWindow.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}
// ดักจับ click/keydown จากหน้าเว็บจริง (parent) เพื่อปลดล็อก autoplay policy ของเบราว์เซอร์
// เดิมดักจับจาก document ของ iframe ที่มองไม่เห็นนี้เอง ซึ่งไม่มี click เกิดขึ้นจริงเลย
// เพราะผู้ใช้คลิกปุ่มต่าง ๆ บนหน้า Streamlit จริง (window.parent.document) ไม่ใช่ในนี้
hostWindow.document.addEventListener('click', initAudio, { once: true });
hostWindow.document.addEventListener('keydown', initAudio, { once: true });

hostWindow.showDesktopNotification = function(title, options = {}) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            icon: '🥇',
            badge: '🔔',
            ...options
        });
    }
};

hostWindow.playNotificationSound = function(frequency = 800, volume = 0.3, doubleBeep = false) {
    try {
        initAudio();
        audioCtx.resume(); // เผื่อกรณี resume() รอบแรกยังทำงานไม่เสร็จ (เป็น async)
        const playTone = (startTime) => {
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            oscillator.frequency.value = frequency; 
            oscillator.type = 'sine';

            gainNode.gain.setValueAtTime(volume, startTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + 0.5);

            oscillator.start(startTime);
            oscillator.stop(startTime + 0.5);
        };

        const now = audioCtx.currentTime;
        playTone(now);
        if (doubleBeep) {
            playTone(now + 0.3);
        }
    } catch (e) {
        console.log('Web Audio API Playback Error:', e);
    }
};
</script>
"""
st.components.v1.html(NOTIFICATION_JS, height=0)

# ==========================================
# 3. Session State สำหรับติดตาม Notifications 
# ==========================================
if "notified_upcoming" not in st.session_state:
    st.session_state.notified_upcoming = set()

if "notified_released" not in st.session_state:
    st.session_state.notified_released = set()

# วันที่ (Bangkok) ล่าสุดที่ set สองอันข้างบนถูกล้าง ใช้เช็คเพื่อล้างอัตโนมัติทุกวันใหม่
# กัน set โตไม่มีที่สิ้นสุดถ้าเปิดแอปทิ้งไว้ข้ามวันหลาย ๆ วันโดยไม่กดล้างแคชเอง
if "notified_reset_date" not in st.session_state:
    st.session_state.notified_reset_date = datetime.now(THAI_TZ).strftime("%Y-%m-%d")

def reset_notified_sets_if_new_day():
    today_str = datetime.now(THAI_TZ).strftime("%Y-%m-%d")
    if st.session_state.notified_reset_date != today_str:
        st.session_state.notified_upcoming.clear()
        st.session_state.notified_released.clear()
        st.session_state.notified_reset_date = today_str

# ==========================================
# 4. พจนานุกรมข่าวและผลกระทบต่อทองคำ (Knowledge Base)
# ==========================================
NEWS_DB = [
    {"patterns": [r"non[-\s]?farm", r"\bnfp\b"], "th": "การจ้างงานนอกภาคเกษตร (NFP)", "impact": "จ้างงานเยอะกว่าคาด = ดอลลาร์แข็ง (ทองร่วงหนัก) 📉 | จ้างงานน้อยกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"\bclaims\b"], "th": "ผู้ขอรับสวัสดิการว่างงาน (Jobless Claims)", "impact": "ยื่นขอเยอะกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀 | ยื่นขอน้อยกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉"},
    {"patterns": [r"unemployment"], "th": "อัตราการว่างงาน", "impact": "ว่างงานเยอะกว่าคาด = เศรษฐกิจแย่ ดอลลาร์อ่อน (ทองพุ่ง) 🚀 | ว่างงานน้อยกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉"},
    {"patterns": [r"\bemployment\b", r"\badp\b"], "th": "ตัวเลขการจ้างงาน (Employment)", "impact": "สูงกว่าคาด = ดอลลาร์แข็ง (ทองลง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองขึ้น) 🚀"},
    {"patterns": [r"\bcpi\b", r"consumer price index"], "th": "ดัชนีราคาผู้บริโภค (เงินเฟ้อ CPI)", "impact": "เงินเฟ้อสูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | เงินเฟ้อต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"\bppi\b", r"producer price index"], "th": "ดัชนีราคาผู้ผลิต (PPI)", "impact": "PPI สูงกว่าคาด = ต้นทุนแพง ดอลลาร์แข็ง (ทองร่วง) 📉 | PPI ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"retail sales"], "th": "ยอดค้าปลีก (Retail Sales)", "impact": "ยอดขายดีกว่าคาด = เศรษฐกิจโต ดอลลาร์แข็ง (ทองร่วง) 📉 | แย่กว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"\bgdp\b"], "th": "ตัวเลข GDP", "impact": "GDP สูงกว่าคาด = เศรษฐกิจดี ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"\bpmi\b", r"purchasing managers"], "th": "ดัชนีผู้จัดการฝ่ายจัดซื้อ (PMI)", "impact": "PMI สูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"\bism\b"], "th": "ดัชนี ISM (ภาคการผลิต/บริการ)", "impact": "สูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"consumer confidence", r"consumer sentiment", r"michigan"], "th": "ดัชนีความเชื่อมั่นผู้บริโภค", "impact": "เชื่อมั่นสูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"durable goods"], "th": "ยอดสั่งซื้อสินค้าคงทน (Durable Goods)", "impact": "สูงกว่าคาด = เศรษฐกิจแข็งแรง ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"housing starts", r"building permits", r"home sales"], "th": "ตัวเลขภาคอสังหาริมทรัพย์", "impact": "สูงกว่าคาด = เศรษฐกิจแข็งแรง ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀"},
    {"patterns": [r"trade balance"], "th": "ดุลการค้า (Trade Balance)", "impact": "ขาดดุลมากกว่าคาด = กดดันดอลลาร์เล็กน้อย (ทองขึ้นเล็กน้อย) 🚀"},
    {"patterns": [r"\bspeaks\b", r"testifies", r"testimony"], "th": "สุนทรพจน์/แถลงความเห็นผู้บริหารธนาคารกลาง", "impact": "เป็นความเห็นส่วนบุคคล ไม่ใช่การประกาศดอกเบี้ยอย่างเป็นทางการ แต่ตลาดอาจตีความเป็นสัญญาณทิศทางดอกเบี้ยในอนาคต — โดยทั่วไปผลกระทบเบากว่าการประกาศดอกเบี้ยจริงมาก"},
    {"patterns": [r"\bfomc\b", r"\bfed\b", r"federal reserve", r"interest rate decision", r"powell"], "th": "แถลงการณ์/ดอกเบี้ย FED", "impact": "ขึ้นดอกเบี้ย/ส่งสัญญาณคุมเข้ม = ดอลลาร์แข็ง (ทองร่วงหนัก) 📉 | ลดดอกเบี้ย/ส่งสัญญาณผ่อนคลาย = ดอลลาร์อ่อน (ทองพุ่งทะยาน) 🚀"},
]

DEFAULT_NEWS_INFO = {
    "th": None,
    "impact": "ข่าวสำคัญที่อาจทำให้กราฟผันผวนรุนแรง (รอดูตัวเลขจริง)",
}

def translate_news(title: str) -> dict:
    title_lower = title.lower()
    for entry in NEWS_DB:
        for pattern in entry["patterns"]:
            if re.search(pattern, title_lower):
                return {"th": entry["th"], "impact": entry["impact"]}
    return {"th": title, "impact": DEFAULT_NEWS_INFO["impact"]}

IMPACT_COLORS = {
    "High": {"emoji": "🔴", "bg": "#e03131", "label": "High", "text": "white"},
    "Medium": {"emoji": "🟠", "bg": "#f08c00", "label": "Medium", "text": "white"},
    "Low": {"emoji": "🟡", "bg": "#f5c518", "label": "Low", "text": "#3a2e00"},
}

def impact_emoji(impact: str) -> str:
    return IMPACT_COLORS.get(impact, {}).get("emoji", "⚪")

def impact_badge_html(impact: str) -> str:
    info = IMPACT_COLORS.get(impact)
    if not info:
        return (
            f'<span style="background-color:#868e96;color:white;padding:2px 10px;'
            f'border-radius:12px;font-size:0.8em;font-weight:600;">{clean_or_dash(impact)}</span>'
        )
    return (
        f'<span style="background-color:{info["bg"]};color:{info["text"]};padding:2px 10px;'
        f'border-radius:12px;font-size:0.8em;font-weight:600;">{info["emoji"]} {info["label"]}</span>'
    )

def primary_zone(group: list) -> str:
    """
    คืน zone key ที่ 'หลัก' ที่สุดในกลุ่ม (priority ตัวเลขน้อยสุด = สำคัญสุด)
    ใช้ร่วมกันทุกที่ที่ต้องเลือกตัวแทนของกลุ่ม zone ที่เวลาตรงกัน กันโค้ดซ้ำ
    """
    return min(group, key=lambda zk: TIMEZONE_CONFIG[zk]["priority"])

def group_zones_by_offset(zone_keys: list) -> list:
    """
    จัดกลุ่ม zone ที่เวลาปัจจุบันตรงกันพอดี (UTC offset เท่ากัน) เอาไว้ด้วยกัน
    เพื่อไม่ต้องมีการ์ด/ป้ายชื่อซ้ำซ้อนสำหรับ zone ที่บอกเวลาเดียวกัน
    คืนค่าเป็น list ของ list เช่น [["tokyo"], ["london","gmt"], ...]
    """
    groups: list = []
    offset_to_group_idx: dict = {}
    for zk in zone_keys:
        if zk not in TIMEZONE_CONFIG:
            continue
        offset = TIMEZONE_CONFIG[zk]["tz"].utcoffset(None)
        if offset in offset_to_group_idx:
            groups[offset_to_group_idx[offset]].append(zk)
        else:
            offset_to_group_idx[offset] = len(groups)
            groups.append([zk])
    return groups

def merged_zone_label(group: list) -> str:
    """
    สร้างชื่อแสดงผลของกลุ่ม zone ที่เวลาตรงกัน
    - zone เดี่ยว: 'Tokyo 🇯🇵'
    - หลาย zone เวลาตรงกัน: 'Tokyo (🇯🇵, sg)'  <- flag ของตัวหลัก + ตัวย่อของ zone อื่นที่ตรงกัน
    """
    primary = primary_zone(group)
    primary_cfg = TIMEZONE_CONFIG[primary]
    if len(group) == 1:
        return f"{primary_cfg['short']} {primary_cfg['flag']}"
    others = [zk for zk in group if zk != primary]
    others_sorted = sorted(others, key=lambda zk: TIMEZONE_CONFIG[zk]["priority"])
    tail = ", ".join([primary_cfg["flag"]] + [TIMEZONE_CONFIG[zk]["abbr"] for zk in others_sorted])
    return f"{primary_cfg['short']} ({tail})"

def display_timezone_clocks(selected_zones: list):
    """
    แก้ปัญหาช่องว่าง (White space) ใต้นาฬิกา:
    ฝังโครงสร้าง HTML แบบ Native ไม่ผ่าน iframe ทำให้การ์ดต่อตัวแบบ Responsive เป๊ะๆ
    """
    JS_TIMEZONES = {
        "gmt": "UTC",
        "tokyo": "Asia/Tokyo",
        "singapore": "Asia/Singapore",
        "london": "Europe/London",
        "newyork": "America/New_York",
        "sydney": "Australia/Sydney",
        "bangkok": "Asia/Bangkok"
    }

    cards_html = ""
    js_clock_data = []

    for group in group_zones_by_offset(selected_zones):
        primary_key = primary_zone(group)
        config = TIMEZONE_CONFIG[primary_key]
        label = merged_zone_label(group)
        js_tz = JS_TIMEZONES.get(primary_key, "UTC")
        clock_id = f"clock-target-{primary_key}"
        # ถ้ามีหลาย zone เวลาตรงกัน รวม session ของแต่ละ zone ไว้ในบรรทัดเดียว
        session_text = " / ".join(dict.fromkeys(TIMEZONE_CONFIG[zk]["session"] for zk in group))

        # ห้ามมีย่อหน้าช่องว่าง (Indentation) นำหน้าเด็ดขาด ไม่งั้นจะกลายเป็น Code Block ใน Markdown
        cards_html += f"""<div style="flex: 1; min-width: 140px; background-color: {config['color']}; color: white; padding: 15px; border-radius: 10px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
<div style="font-size: 0.9em; margin-bottom: 8px; font-weight: bold;">{config['status_badge']} {label}</div>
<div id="{clock_id}" style="font-size: 1.6em; font-family: 'Courier New', monospace; font-weight: bold;">--:--:--</div>
<div style="font-size: 0.8em; margin-top: 8px; opacity: 0.9;">{session_text}</div>
</div>"""
        js_clock_data.append(f"{{ id: '{clock_id}', tz: '{js_tz}' }}")

    st.markdown(f"""<div style="display: flex; gap: 15px; flex-wrap: wrap; width: 100%; margin-bottom: 5px;">
{cards_html}
</div>""", unsafe_allow_html=True)

    js_arrays_str = ",\n".join(js_clock_data)
    
    js_updater = f"""
    <script>
        const clocks = [{js_arrays_str}];
        function updateClocks() {{
            const now = new Date();
            clocks.forEach(clock => {{
                const el = window.parent.document.getElementById(clock.id);
                if (el) {{
                    el.innerText = now.toLocaleTimeString('en-GB', {{ 
                        timeZone: clock.tz, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
                    }});
                }}
            }});
        }}
        updateClocks();
        setInterval(updateClocks, 1000);
    </script>
    """
    import streamlit.components.v1 as components
    components.html(js_updater, height=0)

SESSION_LOCAL_HOURS = {
    "tokyo": {"zone": ZoneInfo("Asia/Tokyo"), "open": (8, 0), "close": (15, 0)},
    "singapore": {"zone": ZoneInfo("Asia/Singapore"), "open": (8, 0), "close": (17, 0)},
    "london": {"zone": ZoneInfo("Europe/London"), "open": (8, 0), "close": (17, 0)},
    "newyork": {"zone": ZoneInfo("America/New_York"), "open": (9, 30), "close": (16, 0)},
    "sydney": {"zone": ZoneInfo("Australia/Sydney"), "open": (8, 0), "close": (16, 0)},
}

def get_active_sessions(now_time: datetime) -> dict:
    active_sessions = {}
    for session_name, defn in SESSION_LOCAL_HOURS.items():
        local_now = now_time.astimezone(defn["zone"])
        open_h, open_m = defn["open"]
        close_h, close_m = defn["close"]

        open_dt = local_now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        close_dt = local_now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

        is_active = open_dt <= local_now < close_dt

        if is_active:
            closes_in = max(0, int((close_dt - local_now).total_seconds() // 60))
            active_sessions[session_name] = {"active": True, "closes_in": closes_in, "opens_in": 0}
        else:
            next_open = open_dt if local_now < open_dt else open_dt + timedelta(days=1)
            opens_in = max(0, int((next_open - local_now).total_seconds() // 60))
            active_sessions[session_name] = {"active": False, "closes_in": 0, "opens_in": opens_in}

    return active_sessions

def display_session_status(selected_zones: list):
    now = datetime.now(THAI_TZ)
    active_sessions = get_active_sessions(now)

    # นับเฉพาะ zone ที่จะแสดงการ์ดจริง (มี session hours และไม่ใช่ gmt) กันคอลัมน์ว่างเกิน
    renderable_zones = [
        zk for zk in selected_zones
        if zk in TIMEZONE_CONFIG and zk != "gmt" and zk in active_sessions
    ]

    st.subheader("📊 Trading Session Status")
    if not renderable_zones:
        return
    cols = st.columns(min(3, len(renderable_zones)))
    
    col_idx = 0
    for zone_key in renderable_zones:
        config = TIMEZONE_CONFIG[zone_key]
        session = active_sessions[zone_key]
        zone_label = f"{config['short']} {config['flag']}"
        
        with cols[col_idx % 3]:
            if session["active"]:
                closes_hours = session["closes_in"] // 60
                closes_mins = session["closes_in"] % 60
                
                st.markdown(f"""<div style="background: linear-gradient(135deg, {config['color']} 0%, rgba(255,255,255,0.1) 100%); border: 2px solid {config['color']}; border-radius: 10px; padding: 15px; margin-bottom: 10px;">
<div style="color: white; font-weight: bold; margin-bottom: 5px;">{config['status_badge']} {zone_label}</div>
<div style="color: #00FF00; font-size: 1.2em; font-weight: bold;">🟢 ACTIVE!</div>
<div style="color: white; font-size: 0.9em; margin-top: 5px;">Closes in {closes_hours}h {closes_mins}m</div>
</div>""", unsafe_allow_html=True)
            else:
                opens_hours = session["opens_in"] // 60
                opens_mins = session["opens_in"] % 60
                
                status_color = "#FF9500" if opens_hours < 1 else "#868E96"
                status_text = "🟡 OPENING SOON!" if opens_hours < 1 else "🔴 CLOSED"
                
                st.markdown(f"""<div style="background: linear-gradient(135deg, {status_color} 0%, rgba(255,255,255,0.1) 100%); border: 2px solid {status_color}; border-radius: 10px; padding: 15px; margin-bottom: 10px;">
<div style="color: white; font-weight: bold; margin-bottom: 5px;">{config['status_badge']} {zone_label}</div>
<div style="color: white; font-size: 1.2em; font-weight: bold;">{status_text}</div>
<div style="color: white; font-size: 0.9em; margin-top: 5px;">Opens in {opens_hours}h {opens_mins}m</div>
</div>""", unsafe_allow_html=True)
        col_idx += 1
    
    now_gmt = now.astimezone(timezone.utc)
    current_hour = now_gmt.hour + (now_gmt.minute / 60)
    
    if 13 <= current_hour < 17:
        st.warning("⭐ **GOLDEN HOUR!** London-NY Overlap (13:00-17:00 GMT = 20:00-00:00 Bangkok) - BEST TRADING TIME! High volume & volatility!")

def parse_numeric_value(raw: str):
    if raw is None:
        return None
    s = raw.strip()
    if s == "" or s in ("—", "-") or s.upper() in ("N/A", "NA"):
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    if s.startswith("-"):
        negative = True
        s = s[1:]

    s = s.replace(",", "").replace("%", "").strip()
    multiplier = 1.0
    if s and s[-1] in ("K", "k"):
        multiplier = 1_000.0
        s = s[:-1]
    elif s and s[-1] in ("M", "m"):
        multiplier = 1_000_000.0
        s = s[:-1]
    elif s and s[-1] in ("B", "b"):
        multiplier = 1_000_000_000.0
        s = s[:-1]

    try:
        value = float(s) * multiplier
    except ValueError:
        return None
    return -value if negative else value

def clean_or_dash(raw, dash: str = "—") -> str:
    """
    คืนค่าที่ปลอดภัยสำหรับแสดงผล: ถ้า raw ว่าง/None หรือเป็น N/A, NA, - (ที่ API บางทีส่งมาตรง ๆ)
    ให้ใช้ '—' แทน (อ่านง่าย ดูทันสมัยกว่าคำว่า 'N/A' ที่โผล่แทรกภาษาอังกฤษในหน้า Thai UI)
    """
    if raw is None:
        return dash
    s = str(raw).strip()
    if s == "" or s.upper() in ("N/A", "NA", "-"):
        return dash
    return s

def parse_iso_datetime(date_str: str) -> datetime:
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    return datetime.fromisoformat(date_str)

def format_dual_time(dt_thai: datetime, currency: str = None) -> str:
    tz_info = CURRENCY_TIMEZONE_MAP.get(currency)
    if tz_info:
        local_time = dt_thai.astimezone(tz_info["zone"])
        return f"{dt_thai.strftime('%H:%M')} น. ({tz_info['label']} {local_time.strftime('%H:%M')})"
    server_time = dt_thai.astimezone(MT4_MT5_TZ)
    return f"{dt_thai.strftime('%H:%M')} น. (GMT {server_time.strftime('%H:%M')})"

@st.cache_data(ttl=300)
def _fetch_raw_calendar() -> list:
    """
    ดึง JSON ดิบจาก ForexFactory endpoint
    หมายเหตุ: st.cache_data จะ cache "เฉพาะตอนที่ return สำเร็จ" เท่านั้น
    ถ้าฟังก์ชันนี้ raise exception จะไม่ถูก cache เลย ทำให้ retry รอบถัดไปยิง network จริงเสมอ
    (ก่อนหน้านี้ error ก็โดน cache ไปด้วย ทำให้ต้องรอเต็ม 5 นาทีถึงจะลองใหม่อัตโนมัติ)
    """
    res = requests.get(NEWS_URL, headers=HTTP_HEADERS, timeout=10)
    res.raise_for_status()
    return res.json()

def fetch_today_news():
    data = None
    last_error = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(attempt)
        try:
            data = _fetch_raw_calendar()
            last_error = None
            break
        except requests.exceptions.RequestException as e:
            last_error = f"เชื่อมต่อ Calendar API ไม่สำเร็จ ({type(e).__name__})"
            continue
        except ValueError:
            last_error = "รูปแบบข้อมูลข่าวที่ได้รับไม่ถูกต้อง (JSON parse error)"
            break

    if data is None:
        return [], last_error or "ไม่ทราบสาเหตุ"

    today_date = datetime.now(THAI_TZ).strftime("%Y-%m-%d")
    today_news = []
    seen_news = set()

    for n in data:
        try:
            if n.get("country") not in TARGET_CURRENCIES or n.get("impact") not in ("High", "Medium", "Low"):
                continue
            news_time = parse_iso_datetime(n.get("date")).astimezone(THAI_TZ)
            if news_time.strftime("%Y-%m-%d") == today_date:
                news_key = (n.get("date"), n.get("title"))
                if news_key not in seen_news:
                    today_news.append(n)
                    seen_news.add(news_key)
        except (KeyError, ValueError, TypeError):
            continue
    return today_news, None

def send_notification(title: str, body: str, enable_desktop: bool, enable_sound: bool, freq: int, vol: float, double_beep: bool):
    if enable_desktop:
        # ใช้ json.dumps เพื่อ escape apostrophe/quote/newline ในชื่อข่าวให้ปลอดภัยตอนฝังเป็น JS string
        # (ถ้าใช้ f-string ตรง ๆ เช่น title มีคำว่า Fed's Bostic Speaks จะทำให้ syntax พังแบบเงียบ ๆ)
        safe_title = json.dumps(title)
        safe_body = json.dumps(body)
        st.components.v1.html(
            f"""
            <script>
            window.parent.showDesktopNotification({safe_title}, {{
                body: {safe_body},
                tag: 'Gold-alert'
            }});
            </script>
            """,
            height=0
        )
    if enable_sound:
        st.components.v1.html(
            f"""
            <script>
            window.parent.playNotificationSound({freq}, {vol / 100}, {str(double_beep).lower()});
            </script>
            """,
            height=0
        )

# ==========================================
# 8. Sidebar: การตั้งค่า
# ==========================================
with st.sidebar:
    st.header("⚙️ ตั้งค่า")
    saved_settings = load_settings()

    st.subheader("🌍 เลือก Timezone ที่จะแสดง")
    selected_timezones = st.multiselect(
        "เลือก timezone",
        options=list(TIMEZONE_CONFIG.keys()),
        default=saved_settings["selected_timezones"],
        format_func=lambda x: TIMEZONE_CONFIG[x]["name"],
        help="เลือก timezone ที่อยากดูเวลา"
    )

    st.divider()
    st.subheader("💱 กรองตามสกุลเงิน")
    selected_currencies = st.multiselect(
        "แสดงเฉพาะข่าวของสกุลเงิน",
        options=TARGET_CURRENCIES,
        default=saved_settings["selected_currencies"],
        format_func=get_currency_badge,
        help="เลือกสกุลเงินที่ต้องการติดตาม (ไม่เลือกเลย = ไม่แสดงข่าว)"
    )

    st.divider()
    st.subheader("🔔 ตั้งค่าการแจ้งเตือน")
    enable_notifications = st.toggle("🔔 เปิดการแจ้งเตือน", value=saved_settings["enable_notifications"])

    sound_tone = saved_settings["sound_tone"]
    sound_volume = saved_settings["sound_volume"]
    sound_frequency = SOUND_TONE_MAP[sound_tone]["freq"]
    sound_double_beep = SOUND_TONE_MAP[sound_tone]["double"]

    if enable_notifications:
        enable_desktop_notif = st.checkbox("💻 Desktop Popup", value=saved_settings["enable_desktop_notif"])
        if enable_desktop_notif:
            if st.button("🔔 ทดสอบ Desktop Popup", use_container_width=True):
                test_title = json.dumps("🥇 ทดสอบการแจ้งเตือน")
                test_body = json.dumps("ถ้าเห็นข้อความนี้ แปลว่า Desktop Popup ทำงานปกติ")
                st.components.v1.html(
                    f"""
                    <script>
                    window.parent.showDesktopNotification({test_title}, {{
                        body: {test_body},
                        tag: 'Gold-alert-test'
                    }});
                    </script>
                    """,
                    height=0
                )
                st.caption("ถ้าไม่เห็น popup ให้เช็คสิทธิ์ Notification ของเบราว์เซอร์/ระบบปฏิบัติการสำหรับเว็บนี้")

        enable_sound_notif = st.checkbox("🔊 Sound Alert", value=saved_settings["enable_sound_notif"])

        if enable_sound_notif:
            sound_tone = st.selectbox(
                "🎵 โทนเสียง",
                options=list(SOUND_TONE_MAP.keys()),
                index=list(SOUND_TONE_MAP.keys()).index(saved_settings["sound_tone"])
            )
            sound_volume = st.slider("🔈 ระดับเสียง (%)", 0, 100, saved_settings["sound_volume"], step=5)

            sound_frequency = SOUND_TONE_MAP[sound_tone]["freq"]
            sound_double_beep = SOUND_TONE_MAP[sound_tone]["double"]

            if st.button("▶️ ทดสอบเสียง", use_container_width=True):
                st.components.v1.html(
                    f"""
                    <script>
                    window.parent.playNotificationSound({sound_frequency}, {sound_volume / 100}, {str(sound_double_beep).lower()});
                    </script>
                    """,
                    height=0
                )
        
        notify_upcoming = st.checkbox("⏰ เตือนก่อน 5-10 นาที", value=saved_settings["notify_upcoming"])
        notify_released = st.checkbox("✅ เตือนเมื่อข่าวออก", value=saved_settings["notify_released"])
    else:
        enable_desktop_notif = False
        enable_sound_notif = False
        notify_upcoming = False
        notify_released = False

    st.divider()
    auto_refresh_on = st.toggle("🔄 อัปเดตอัตโนมัติ", value=saved_settings["auto_refresh_on"])
    refresh_seconds = st.slider("ความถี่ในการอัปเดต (วินาที)", 10, 120, saved_settings["refresh_seconds"], step=10)

    if auto_refresh_on:
        if HAS_FRAGMENT:
            st.caption("✅ รีเฟรชเฉพาะส่วนข่าว (st.fragment) — ไม่ล้าง dropdown ที่เปิดอยู่")
        elif HAS_AUTOREFRESH:
            st_autorefresh(interval=refresh_seconds * 1000, key="dashboard_autorefresh")
            st.caption("⚠️ รีเฟรชทั้งหน้า — อัปเดต Streamlit เป็น ≥1.33 เพื่อใช้ st.fragment จะลื่นกว่านี้")
        else:
            st.info("แนะนำอัปเดต Streamlit เป็นเวอร์ชันล่าสุด หรือติดตั้ง: `pip install streamlit-autorefresh`")

    save_settings({
        "selected_timezones": selected_timezones,
        "selected_currencies": selected_currencies,
        "enable_notifications": enable_notifications,
        "enable_desktop_notif": enable_desktop_notif,
        "enable_sound_notif": enable_sound_notif,
        "notify_upcoming": notify_upcoming,
        "notify_released": notify_released,
        "auto_refresh_on": auto_refresh_on,
        "refresh_seconds": refresh_seconds,
        "sound_tone": sound_tone,
        "sound_volume": sound_volume,
    })

    st.caption(f"เวลาปัจจุบัน: {datetime.now(THAI_TZ).strftime('%H:%M:%S น.')}")
    st.caption("💾 การตั้งค่าถูกจำไว้อัตโนมัติ")
    st.divider()

    if st.button("🔄 ล้างแคชและโหลดใหม่ทั้งหมด", use_container_width=True):
        st.cache_data.clear()
        st.session_state.notified_upcoming.clear()
        st.session_state.notified_released.clear()
        st.rerun()

    if st.button("♻️ รีเซ็ตการตั้งค่า", use_container_width=True):
        try:
            SETTINGS_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        st.rerun()

# ==========================================
# 9. ส่วนแสดงผล: หัวข้อ + นาฬิกาเวลาสด
# ==========================================
st.title("🥇 Gold News")
st.markdown("ติดตามข่าวเศรษฐกิจและเหตุการณ์สำคัญทั่วโลกที่มีผลต่อราคาทองคำ (Gold) อัปเดตอัตโนมัติ")

if selected_timezones:
    st.subheader("🌍 เวลาปัจจุบันในแต่ละ Zone")
    display_timezone_clocks(selected_timezones)
else:
    st.warning("⚠️ กรุณาเลือก Timezone อย่างน้อย 1 อันจากแถบด้านซ้าย")

st.markdown("---")

# ==========================================
# ส่วนแสดงผลข่าว + Session Status + การแจ้งเตือน
# ==========================================
def render_live_section():
    reset_notified_sets_if_new_day()

    if selected_timezones:
        display_session_status(selected_timezones)
        st.markdown("---")

    now = datetime.now(THAI_TZ)
    news_list, news_error = fetch_today_news()

    if not selected_currencies:
        news_list = []
    elif news_list:
        news_list = [n for n in news_list if n.get("country") in selected_currencies]

    if news_error:
        st.error(f"⚠️ **ดึงข้อมูลข่าวไม่สำเร็จ:** {news_error}\n\nกรุณากดปุ่ม 'ล้างแคชและโหลดใหม่ทั้งหมด' ที่แถบด้านซ้าย")
    elif not selected_currencies:
        st.warning("⚠️ กรุณาเลือกอย่างน้อย 1 สกุลเงินที่แถบด้านซ้าย เพื่อแสดงข่าว")
    elif not news_list:
        st.success("✅ **วันนี้ไม่มีข่าวสำคัญ (แดง/ส้ม/เหลือง) ของสกุลเงินที่เลือก**")
    else:
        past_news, upcoming_news = [], []
        for n in news_list:
            try:
                n_time = parse_iso_datetime(n["date"]).astimezone(THAI_TZ)
            except (KeyError, ValueError, TypeError):
                continue
            (upcoming_news if n_time > now else past_news).append((n, n_time))

        upcoming_news.sort(key=lambda x: x[1])
        past_news.sort(key=lambda x: x[1], reverse=True)

        if enable_notifications:
            for n, n_time in upcoming_news:
                news_id = f"{n.get('date')}_{n.get('title', '').replace(' ', '_')}"
                time_until = (n_time - now).total_seconds()

                if notify_upcoming and time_until > 0 and time_until <= 600:
                    if news_id not in st.session_state.notified_upcoming:
                        info = translate_news(n.get("title", ""))
                        title_display = info["th"] or n.get("title", "")
                        impact = n.get("impact", "")
                        send_notification(
                            f"⚠️ ข่าว {title_display} กำลังจะออก!",
                            f"อีก {int(time_until // 60)} นาที (เวลา {format_dual_time(n_time, n.get('country'))})\nระดับ: {impact}",
                            enable_desktop_notif,
                            enable_sound_notif,
                            sound_frequency, sound_volume, sound_double_beep
                        )
                        st.session_state.notified_upcoming.add(news_id)

                if notify_released and time_until <= 0 and time_until > -600:
                    if news_id not in st.session_state.notified_released:
                        info = translate_news(n.get("title", ""))
                        title_display = info["th"] or n.get("title", "")
                        actual = n.get("actual") or "รอข้อมูล"
                        send_notification(
                            f"✅ ข่าว {title_display} เพิ่งออก!",
                            f"ตัวเลขจริง: {actual}",
                            enable_desktop_notif,
                            enable_sound_notif,
                            sound_frequency, sound_volume, sound_double_beep
                        )
                        st.session_state.notified_released.add(news_id)

        # Dashboard Summary
        high_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "High")
        medium_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "Medium")
        low_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "Low")

        active_sessions_summary = get_active_sessions(now)
        active_zone_keys = [
            z for z in selected_timezones
            if z != "gmt" and active_sessions_summary.get(z, {}).get("active")
        ]
        # จัดกลุ่ม zone ที่ active พร้อมกันและเวลาตรงกัน ใช้ชื่อเต็มเหมือนเดิม แต่แสดงเป็น chip แยกแต่ละอัน
        active_zone_groups = group_zones_by_offset(active_zone_keys)
        now_gmt = now.astimezone(timezone.utc)
        is_golden_hour = 13 <= (now_gmt.hour + now_gmt.minute / 60) < 17

        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        with sum_col1:
            if is_golden_hour:
                st.metric("Session ตอนนี้", "⭐ Golden Hour")
            elif active_zone_groups:
                zone_chips = "".join(
                    f'<span style="background:{TIMEZONE_CONFIG[primary_zone(g)]["color"]}; '
                    f'color:white; padding:3px 11px; border-radius:20px; font-size:0.82rem; font-weight:600; '
                    f'white-space:nowrap; display:inline-block; box-shadow:0 2px 5px rgba(0,0,0,0.15);">'
                    f'{merged_zone_label(g)}</span>'
                    for g in active_zone_groups
                )
                st.markdown(
                    f"""<div style="padding: 2px 0 4px 0;">
<div style="font-size: 0.875rem; opacity: 0.6; margin-bottom: 6px;">🟢 Active</div>
<div style="display: flex; flex-wrap: wrap; gap: 6px;">{zone_chips}</div>
</div>""",
                    unsafe_allow_html=True,
                )
            else:
                st.metric("🔴 Session", "ปิดทั้งหมด")
        with sum_col2:
            st.metric("🔴 High Impact", f"{high_count} ข่าว")
        with sum_col3:
            st.metric("🟠 Medium Impact", f"{medium_count} ข่าว")
        with sum_col4:
            st.metric("🟡 Low Impact", f"{low_count} ข่าว")

        st.caption(f"ประกาศไปแล้ว {len(past_news)} ข่าว | รอประกาศอีก {len(upcoming_news)} ข่าว")
        st.markdown("---")

        if upcoming_news:
            next_news, next_time = upcoming_news[0]
            time_left = next_time - now
            
            total_seconds_left = max(0, int(time_left.total_seconds()))
            hours, remainder = divmod(total_seconds_left, 3600)
            minutes, _ = divmod(remainder, 60)
            
            info = translate_news(next_news.get("title", ""))
            display_th = info["th"] or next_news.get("title", "")
            next_currency = clean_or_dash(next_news.get("country"), dash="")

            st.markdown("### 🚨 ข่าวสำคัญต่อไปที่กำลังจะออก")
            impact_level = next_news.get("impact", "")
            
            card_color = IMPACT_COLORS.get(impact_level, {}).get("bg", "#868e96")
            
            # ลบช่องว่างข้างหน้าออกเพื่อไม่ให้เป็น Code Block
            card_html = f"""<div style="border: 1px solid rgba(128,128,128,0.2); border-left: 6px solid {card_color}; border-radius: 10px; padding: 20px; background: rgba(128,128,128,0.05); display: flex; flex-wrap: wrap; gap: 20px; align-items: center; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
<div style="flex: 1; min-width: 220px;">
<div style="font-size: 1.25rem; color: {card_color}; font-weight: bold; margin-bottom: 8px;">⏳ อีก {hours} ชม. {minutes} นาที</div>
<div style="font-size: 0.95rem; margin-bottom: 15px; opacity: 0.8;">เวลา: <b>{format_dual_time(next_time, next_currency)}</b></div>
<div>{impact_badge_html(impact_level)} &nbsp; {get_currency_badge(next_currency)}</div>
</div>
<div style="flex: 2; min-width: 250px;">
<div style="font-size: 1.25rem; font-weight: bold; margin-bottom: 5px;">{display_th}</div>
<div style="font-size: 0.9rem; opacity: 0.8; margin-bottom: 12px;">{clean_or_dash(next_news.get('title'))}</div>
<div style="font-size: 0.95rem; padding: 12px; background: rgba(128,128,128,0.08); border-radius: 8px; margin-bottom: 12px;">📌 <b>ผลกระทบ:</b> {info['impact']}</div>
<div style="display: flex; gap: 15px; font-size: 0.9rem; flex-wrap: wrap;">
<div style="background: rgba(128,128,128,0.08); padding: 8px 12px; border-radius: 5px; flex: 1; min-width: 120px;">📊 <b>คาดการณ์:</b> {next_news.get('forecast') or 'ไม่มีข้อมูล'}</div>
<div style="background: rgba(128,128,128,0.08); padding: 8px 12px; border-radius: 5px; flex: 1; min-width: 120px;">🔄 <b>ครั้งก่อน:</b> {next_news.get('previous') or 'ไม่มีข้อมูล'}</div>
</div>
</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

            st.markdown("---")

            if len(upcoming_news) > 1:
                st.subheader("📅 ข่าวอื่นๆ ที่รอประกาศในวันนี้")
                for n, n_time in upcoming_news[1:]:
                    info = translate_news(n.get("title", ""))
                    display_th = info["th"] or n.get("title", "")
                    badge = impact_emoji(n.get("impact", ""))
                    currency_b = get_currency_badge(n.get("country", ""))

                    with st.expander(f"{badge} {currency_b} | ⏰ {format_dual_time(n_time, n.get('country'))} - {display_th}"):
                        st.markdown(f"**สกุลเงิน:** {currency_b} | **ความรุนแรง:** {impact_badge_html(n.get('impact', ''))}", unsafe_allow_html=True)
                        st.write(f"**การวิเคราะห์:** {info['impact']}")
                        st.write(
                            f"**คาดการณ์:** {n.get('forecast') or 'ไม่มีข้อมูล'} | "
                            f"**ครั้งก่อน:** {n.get('previous') or 'ไม่มีข้อมูล'}"
                        )
        else:
            st.info("✅ ไม่มีข่าวสำคัญที่รอประกาศแล้วสำหรับวันนี้")

        # ข่าวที่ประกาศไปแล้ว
        if past_news:
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("✅ ข่าวที่ประกาศไปแล้ววันนี้ (เรียงจากล่าสุดขึ้นก่อน)")

            for n, n_time in past_news:
                info = translate_news(n.get("title", ""))
                display_th = info["th"] or n.get("title", "")
                actual_raw = clean_or_dash(n.get("actual"))
                forecast_raw = clean_or_dash(n.get("forecast"))
                previous_raw = clean_or_dash(n.get("previous"))
                badge = impact_emoji(n.get("impact", ""))
                currency_b = get_currency_badge(n.get("country", ""))

                with st.expander(f"{badge} {currency_b} ✔️ ออกแล้วเวลา {format_dual_time(n_time, n.get('country'))}: {display_th}", expanded=True):
                    st.markdown(f"{impact_badge_html(n.get('impact', ''))} &nbsp; {currency_b}", unsafe_allow_html=True)

                    if actual_raw == "—" and forecast_raw == "—" and previous_raw == "—":
                        st.write("🎙️ ข่าวประเภทแถลงการณ์/สุนทรพจน์ ไม่มีตัวเลขเปรียบเทียบ ติดตามผลกระทบจากกราฟราคาโดยตรงครับ")
                        continue

                    colA, colB, colC = st.columns(3)
                    colA.metric("ตัวเลขจริง (Actual)", actual_raw)
                    colB.metric("คาดการณ์ (Forecast)", forecast_raw)
                    colC.metric("ครั้งก่อน (Previous)", previous_raw)

                    a_val = parse_numeric_value(actual_raw)
                    f_val = parse_numeric_value(forecast_raw)

                    if a_val is not None and f_val is not None:
                        if a_val > f_val:
                            st.info("💡 **วิเคราะห์:** ตัวเลขจริง **สูงกว่า** คาดการณ์ (ทิศทางจริงต้องดูบริบทของข่าวนั้นๆ ประกอบด้วย)")
                        elif a_val < f_val:
                            st.info("💡 **วิเคราะห์:** ตัวเลขจริง **ต่ำกว่า** คาดการณ์ (ทิศทางจริงต้องดูบริบทของข่าวนั้นๆ ประกอบด้วย)")
                        else:
                            st.info("💡 **วิเคราะห์:** ตัวเลขจริงเท่ากับคาดการณ์พอดี ผลกระทบต่อตลาดมักจะจำกัด")
                    else:
                        st.write("💡 ยังไม่มีตัวเลขให้เปรียบเทียบ หรือรออีก 5-15 นาทีให้ตลาดสะท้อนราคาแล้วดูทิศทางกราฟจริงครับ")

if auto_refresh_on and HAS_FRAGMENT:
    render_live_section = st.fragment(run_every=refresh_seconds)(render_live_section)

render_live_section()

st.markdown("---")
st.caption(
    "🔔 แดชบอร์ดนี้เป็นเครื่องมือช่วยประกอบการตัดสินใจเท่านั้น ไม่ใช่คำแนะนำการลงทุน "
    "โปรดบริหารความเสี่ยงและตรวจสอบข่าวจากแหล่งทางการก่อนเทรดจริงเสมอ"
)