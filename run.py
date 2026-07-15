"""
GOLD News Calendar Assistant with Desktop Notifications
==========================================================
วิธีรัน:
    pip install -r requirements.txt
    streamlit run app.py

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
# (ใช้เป็น fallback เท่านั้น — ถ้า Streamlit รองรับ st.fragment จะใช้แบบนั้นแทน เพราะลื่นกว่า
#  ไม่ล้าง scroll / dropdown / expander ที่เปิดอยู่ตอนรีเฟรช)
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
        "tz": MT4_MT5_TZ,
        "tz_std": MT4_MT5_TZ,
        "color": "#4D96FF",  # Blue
        "session": "Reference",
        "status_badge": "⚪",
        "priority": 1,
        "importance": "⭐⭐⭐⭐"
    },
    "tokyo": {
        "name": "Tokyo 🇯🇵",
        "tz": timezone(timedelta(hours=9)),  # JST (UTC+9)
        "tz_std": timezone(timedelta(hours=9)),  # No DST
        "color": "#9D4EDD",  # Purple
        "session": "08:00-15:00 JST",
        "status_badge": "🟣",
        "priority": 2,
        "importance": "⭐⭐⭐"
    },
    "singapore": {
        "name": "Singapore 🇸🇬",
        "tz": timezone(timedelta(hours=8)),  # SGT (UTC+8)
        "tz_std": timezone(timedelta(hours=8)),  # No DST
        "color": "#FF6B6B",  # Red-Orange
        "session": "08:00-17:00 SGT",
        "status_badge": "🟠",
        "priority": 3,
        "importance": "⭐⭐⭐"
    },
    "london": {
        "name": "London 🇬🇧",
        "tz": timezone(timedelta(hours=1)),  # BST (UTC+1) - ช่วง DST
        "tz_std": timezone.utc,  # GMT (UTC+0)
        "color": "#FF9500",  # Orange
        "session": "08:00-17:00 GMT",
        "status_badge": "🟠",
        "priority": 4,
        "importance": "⭐⭐⭐⭐"
    },
    "newyork": {
        "name": "New York 🇺🇸",
        "tz": timezone(timedelta(hours=-4)),  # EDT (UTC-4) - ช่วง DST
        "tz_std": timezone(timedelta(hours=-5)),  # EST (UTC-5)
        "color": "#FF3B30",  # Red
        "session": "13:30-20:00 GMT",
        "status_badge": "🔴",
        "priority": 5,
        "importance": "⭐⭐⭐⭐⭐"
    },
    "sydney": {
        "name": "Sydney 🇦🇺",
        "tz": timezone(timedelta(hours=11)),  # AEDT (UTC+11) - ช่วง DST
        "tz_std": timezone(timedelta(hours=10)),  # AEST (UTC+10)
        "color": "#17C784",  # Green
        "session": "22:00-06:00 GMT",
        "status_badge": "🟢",
        "priority": 6,
        "importance": "⭐⭐"
    },
    "bangkok": {
        "name": "Bangkok 🇹🇭 (Home)",
        "tz": THAI_TZ,
        "tz_std": THAI_TZ,
        "color": "#FFD700",  # Gold
        "session": "24H (Reference)",
        "status_badge": "⭐",
        "priority": 0,
        "importance": "Personal"
    },
}

# Default timezone ที่จะแสดง (International Standard)
DEFAULT_TIMEZONES = ["gmt", "tokyo", "london", "newyork"]
# ==========================================
# ตั้งค่าสกุลเงินที่ต้องการติดตาม (Major Currencies)
# ==========================================
TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "CHF"]

CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", 
    "JPY": "🇯🇵", "CNY": "🇨🇳", "AUD": "🇦🇺", 
    "CAD": "🇨🇦", "CHF": "🇨🇭", "NZD": "🇳🇿"
}

def get_currency_badge(currency: str) -> str:
    """คืนค่าธงชาติและชื่อสกุลเงิน"""
    flag = CURRENCY_FLAGS.get(currency, "🏳️")
    return f"{flag} {currency}"

# ==========================================
# ระบบจำการตั้งค่า (persist ข้าม browser refresh / เปิดแอปใหม่)
# ==========================================
# หมายเหตุ: st.session_state จำค่าได้แค่ตอนสคริปต์ rerun (เช่นจาก st.fragment,
# หรือกด widget อื่น) แต่พอ "รีเฟรชเบราว์เซอร์" (F5) มันคือ session ใหม่ทั้งหมด
# session_state ถูกล้าง ต้องเก็บค่าไว้ "นอก" Streamlit คือไฟล์บนดิสก์แทน
SETTINGS_FILE = Path(__file__).resolve().parent / "user_settings.json"

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
}


def load_settings() -> dict:
    """โหลดการตั้งค่าที่เคยบันทึกไว้จากไฟล์ user_settings.json
    ถ้าไม่มีไฟล์ / ไฟล์เสีย / ค่าที่เก็บไว้ใช้ไม่ได้แล้ว (เช่น timezone ที่เคยเลือกถูกลบออกจากระบบ)
    จะ fallback กลับไปใช้ค่า default แทน ไม่ทำให้แอปพัง"""
    settings = DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for key in DEFAULT_SETTINGS:
            if key in saved:
                settings[key] = saved[key]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass  # ยังไม่เคยบันทึก หรือไฟล์เสีย ใช้ default ไปก่อน

    # กรองค่าที่ไม่ valid แล้วออก (กัน error ตอนส่งเป็น default ให้ widget)
    settings["selected_timezones"] = [
        tz for tz in settings.get("selected_timezones", []) if tz in TIMEZONE_CONFIG
    ] or DEFAULT_TIMEZONES
    settings["selected_currencies"] = [
        c for c in settings.get("selected_currencies", []) if c in TARGET_CURRENCIES
    ] or TARGET_CURRENCIES
    refresh_val = settings.get("refresh_seconds", 30)
    if not isinstance(refresh_val, int) or not (10 <= refresh_val <= 120):
        settings["refresh_seconds"] = 30

    return settings


def save_settings(settings: dict):
    """บันทึกการตั้งค่าปัจจุบันลงไฟล์ — เขียนทับทุกครั้งที่ sidebar rerun
    (ราคาถูก เพราะ sidebar อยู่นอก st.fragment จะรันแค่ตอนมีคนแก้ค่าจริงๆ)"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass  # เขียนไฟล์ไม่ได้ (เช่น permission) ก็แค่ข้าม ไม่ทำให้แอปพัง

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
    div[data-testid="stMetricValue"] { font-size: 2rem; }
    
    /* แอนิเมชัน pulse สำหรับ notification badge */
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    .notification-pulse {
        animation: pulse 1s infinite;
    }
    
    /* Notification container */
    .notification-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 5px solid #ffd700;
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
// ขออนุญาต Notification ถ้ายังไม่ได้ขอ
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// ฟังก์ชันแสดง Desktop Notification
window.showDesktopNotification = function(title, options = {}) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            icon: '🥇',
            badge: '🔔',
            ...options
        });
    }
};

// ฟังก์ชันเล่นเสียงเตือน
window.playNotificationSound = function() {
    // สร้างเสียง beep โดยใช้ Web Audio API
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 800; // ความถี่ (Hz)
        oscillator.type = 'sine';
        
        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
    } catch (e) {
        console.log('Web Audio API ไม่สามารถใช้ได้:', e);
    }
};
</script>
"""

# เพิ่ม JavaScript ให้กับหน้า
st.components.v1.html(NOTIFICATION_JS, height=0)

# ==========================================
# 3. Session State สำหรับติดตาม Notifications ที่เคยเตือนแล้ว
# ==========================================
if "notified_upcoming" not in st.session_state:
    st.session_state.notified_upcoming = set()  # เก็บ ID ของข่าวที่เตือน "กำลังจะออก" แล้ว

if "notified_released" not in st.session_state:
    st.session_state.notified_released = set()  # เก็บ ID ของข่าวที่เตือน "เพิ่งออก" แล้ว

if "last_check_time" not in st.session_state:
    st.session_state.last_check_time = None

if "breaking_news_log" not in st.session_state:
    st.session_state.breaking_news_log = []  # เก็บประวัติ Breaking News ที่โพสต์ไว้ (คงอยู่ตลอด session)

# ==========================================
# 4. พจนานุกรมข่าวและผลกระทบต่อทองคำ (Knowledge Base)
# ==========================================
NEWS_DB = [
    {
        "patterns": [r"non[-\s]?farm", r"\bnfp\b"],
        "th": "การจ้างงานนอกภาคเกษตร (NFP)",
        "impact": "จ้างงานเยอะกว่าคาด = ดอลลาร์แข็ง (ทองร่วงหนัก) 📉 | จ้างงานน้อยกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"\bclaims\b"],
        "th": "ผู้ขอรับสวัสดิการว่างงาน (Jobless Claims)",
        "impact": "ยื่นขอเยอะกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀 | ยื่นขอน้อยกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉",
    },
    {
        "patterns": [r"unemployment"],
        "th": "อัตราการว่างงาน",
        "impact": "ว่างงานเยอะกว่าคาด = เศรษฐกิจแย่ ดอลลาร์อ่อน (ทองพุ่ง) 🚀 | ว่างงานน้อยกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉",
    },
    {
        "patterns": [r"\bemployment\b", r"\badp\b"],
        "th": "ตัวเลขการจ้างงาน (Employment)",
        "impact": "สูงกว่าคาด = ดอลลาร์แข็ง (ทองลง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองขึ้น) 🚀",
    },
    {
        "patterns": [r"\bcpi\b", r"consumer price index"],
        "th": "ดัชนีราคาผู้บริโภค (เงินเฟ้อ CPI)",
        "impact": "เงินเฟ้อสูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | เงินเฟ้อต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"\bppi\b", r"producer price index"],
        "th": "ดัชนีราคาผู้ผลิต (PPI)",
        "impact": "PPI สูงกว่าคาด = ต้นทุนแพง ดอลลาร์แข็ง (ทองร่วง) 📉 | PPI ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"retail sales"],
        "th": "ยอดค้าปลีก (Retail Sales)",
        "impact": "ยอดขายดีกว่าคาด = เศรษฐกิจโต ดอลลาร์แข็ง (ทองร่วง) 📉 | แย่กว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"\bgdp\b"],
        "th": "ตัวเลข GDP",
        "impact": "GDP สูงกว่าคาด = เศรษฐกิจดี ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"\bpmi\b", r"purchasing managers"],
        "th": "ดัชนีผู้จัดการฝ่ายจัดซื้อ (PMI)",
        "impact": "PMI สูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"\bism\b"],
        "th": "ดัชนี ISM (ภาคการผลิต/บริการ)",
        "impact": "สูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"consumer confidence", r"consumer sentiment", r"michigan"],
        "th": "ดัชนีความเชื่อมั่นผู้บริโภค",
        "impact": "เชื่อมั่นสูงกว่าคาด = ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"durable goods"],
        "th": "ยอดสั่งซื้อสินค้าคงทน (Durable Goods)",
        "impact": "สูงกว่าคาด = เศรษฐกิจแข็งแรง ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"housing starts", r"building permits", r"home sales"],
        "th": "ตัวเลขภาคอสังหาริมทรัพย์",
        "impact": "สูงกว่าคาด = เศรษฐกิจแข็งแรง ดอลลาร์แข็ง (ทองร่วง) 📉 | ต่ำกว่าคาด = ดอลลาร์อ่อน (ทองพุ่ง) 🚀",
    },
    {
        "patterns": [r"trade balance"],
        "th": "ดุลการค้า (Trade Balance)",
        "impact": "ขาดดุลมากกว่าคาด = กดดันดอลลาร์เล็กน้อย (ทองขึ้นเล็กน้อย) 🚀",
    },
    {
        "patterns": [r"\bfomc\b", r"\bfed\b", r"federal reserve", r"interest rate decision", r"powell"],
        "th": "แถลงการณ์/ดอกเบี้ย FED",
        "impact": "ขึ้นดอกเบี้ย/ส่งสัญญาณคุมเข้ม = ดอลลาร์แข็ง (ทองร่วงหนัก) 📉 | ลดดอกเบี้ย/ส่งสัญญาณผ่อนคลาย = ดอลลาร์อ่อน (ทองพุ่งทะยาน) 🚀",
    },
]
DEFAULT_NEWS_INFO = {
    "th": None,  # ใช้ title ต้นฉบับแทน
    "impact": "ข่าวสำคัญที่อาจทำให้กราฟผันผวนรุนแรง (รอดูตัวเลขจริง)",
}


def translate_news(title: str) -> dict:
    """แปลหัวข้อข่าวเป็นภาษาไทยพร้อมคำอธิบายผลกระทบ โดยจับคำแบบ word-boundary"""
    title_lower = title.lower()
    for entry in NEWS_DB:
        for pattern in entry["patterns"]:
            if re.search(pattern, title_lower):
                return {"th": entry["th"], "impact": entry["impact"]}
    return {"th": title, "impact": DEFAULT_NEWS_INFO["impact"]}


# ป้ายสีบอกระดับผลกระทบข่าว: แดง = High, ส้ม = Medium, เหลือง = Low
IMPACT_COLORS = {
    "High": {"emoji": "🔴", "bg": "#e03131", "label": "High", "text": "white"},
    "Medium": {"emoji": "🟠", "bg": "#f08c00", "label": "Medium", "text": "white"},
    "Low": {"emoji": "🟡", "bg": "#f5c518", "label": "Low", "text": "#3a2e00"},
}


def impact_emoji(impact: str) -> str:
    """คืนค่าอิโมจิวงกลมสีบอกระดับผลกระทบ"""
    return IMPACT_COLORS.get(impact, {}).get("emoji", "⚪")


def impact_badge_html(impact: str) -> str:
    """คืนค่าป้าย (badge) สีบอกระดับผลกระทบแบบ HTML pill"""
    info = IMPACT_COLORS.get(impact)
    if not info:
        return (
            f'<span style="background-color:#868e96;color:white;padding:2px 10px;'
            f'border-radius:12px;font-size:0.8em;font-weight:600;">{impact or "N/A"}</span>'
        )
    return (
        f'<span style="background-color:{info["bg"]};color:{info["text"]};padding:2px 10px;'
        f'border-radius:12px;font-size:0.8em;font-weight:600;">{info["emoji"]} {info["label"]}</span>'
    )


def display_timezone_clocks(selected_zones: list):
    """แสดงนาฬิกาเวลาหลาย timezone พร้อมสี (อัปเดตแบบ Real-time ด้วย JavaScript)"""
    
    # ฐานข้อมูล IANA Timezone สำหรับให้ JavaScript นำไปประมวลผล (รองรับ DST อัตโนมัติ)
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
    
    # สร้างโครงสร้าง HTML สำหรับแต่ละโซนเวลาที่ผู้ใช้เลือก
    for zone_key in selected_zones:
        if zone_key not in TIMEZONE_CONFIG:
            continue
            
        config = TIMEZONE_CONFIG[zone_key]
        js_tz = JS_TIMEZONES.get(zone_key, "UTC")
        clock_id = f"clock-{zone_key}"
        
        cards_html += f"""
        <div style="
            flex: 1;
            min-width: 150px;
            background-color: {config['color']};
            color: white;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            font-family: sans-serif;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        ">
            <div style="font-size: 0.9em; margin-bottom: 8px; font-weight: bold;">
                {config['status_badge']} {config['name']}
            </div>
            <!-- ช่องว่างสำหรับใส่เวลาจาก JavaScript -->
            <div id="{clock_id}" style="font-size: 1.8em; font-family: 'Courier New', monospace; font-weight: bold;">
                --:--:--
            </div>
            <div style="font-size: 0.8em; margin-top: 8px; opacity: 0.9;">
                {config['session']}
            </div>
        </div>
        """
        
        # เก็บข้อมูลเพื่อส่งให้ JS
        js_clock_data.append(f"{{ id: '{clock_id}', tz: '{js_tz}' }}")

    js_arrays_str = ",\n".join(js_clock_data)

    # ประกอบ HTML และ JavaScript (ทำงานทุกๆ 1 วินาที)
    html_content = f"""
    <div style="display: flex; gap: 15px; flex-wrap: wrap; width: 100%;">
        {cards_html}
    </div>
    
    <script>
        const clocks = [
            {js_arrays_str}
        ];

        function updateClocks() {{
            const now = new Date();
            clocks.forEach(clock => {{
                const el = document.getElementById(clock.id);
                if (el) {{
                    // ใช้ toLocaleTimeString เพื่อแปลงเวลาตาม Timezone ที่กำหนด
                    el.innerText = now.toLocaleTimeString('en-GB', {{ 
                        timeZone: clock.tz,
                        hour12: false,
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    }});
                }}
            }});
        }}
        
        // รันครั้งแรกทันที และตั้งเวลาให้รันซ้ำทุก 1000ms (1 วินาที)
        updateClocks();
        setInterval(updateClocks, 1000);
    </script>
    """

    # แสดงผลผ่าน st.components.v1 (กำหนดความสูงให้พอดีกับกล่อง)
    import streamlit.components.v1 as components
    components.html(html_content, height=130)


# นิยามเวลาเปิด-ปิดตลาดเป็น "เวลาท้องถิ่นจริง" ของแต่ละเมือง (ไม่ hardcode เป็น GMT offset ตายตัว)
# ให้ ZoneInfo จัดการเรื่อง DST (เวลาออมแสง) ให้อัตโนมัติ ถูกต้องตลอดทั้งปี
# ปัญหาเดิม: hardcode "New York = 13:30-20:00 GMT" ถูกแค่ตอน EDT (ฤดูร้อน)
#            พอเข้า EST (ฤดูหนาว) เวลาจริงเลื่อนเป็น 14:30-21:00 GMT ทำให้ status ผิดไป 1 ชม.
SESSION_LOCAL_HOURS = {
    "tokyo": {"zone": ZoneInfo("Asia/Tokyo"), "open": (8, 0), "close": (15, 0)},
    "singapore": {"zone": ZoneInfo("Asia/Singapore"), "open": (8, 0), "close": (17, 0)},
    "london": {"zone": ZoneInfo("Europe/London"), "open": (8, 0), "close": (17, 0)},
    "newyork": {"zone": ZoneInfo("America/New_York"), "open": (9, 30), "close": (16, 0)},
    "sydney": {"zone": ZoneInfo("Australia/Sydney"), "open": (8, 0), "close": (16, 0)},
}


def get_active_sessions(now_time: datetime) -> dict:
    """ตรวจสอบว่า session ไหนกำลังเปิดตอนนี้ โดยใช้ ZoneInfo (รองรับ DST อัตโนมัติ)

    วิธีคิด: แปลง now_time เป็นเวลาท้องถิ่น "จริง" ของแต่ละตลาด แล้วเทียบกับเวลา
    เปิด-ปิดท้องถิ่นตรงๆ (ไม่ต้องคำนวณ offset เอง ปล่อยให้ ZoneInfo จัดการ DST ให้)
    ข้อดีอีกอย่าง: ไม่ต้องจัดการ "วันข้ามคืน" แบบ Sydney แบบเดิม เพราะเวลาเปิด-ปิด
    ท้องถิ่นของ Sydney เอง (08:00-16:00) ไม่ได้ข้ามเที่ยงคืน

    Returns:
        {
            "tokyo": {"active": True, "closes_in": 120, "opens_in": 0},
            "london": {"active": False, "closes_in": 0, "opens_in": 180},
            ...
        }
        (closes_in / opens_in มีหน่วยเป็นนาที)
    """
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
            active_sessions[session_name] = {
                "active": True,
                "closes_in": closes_in,
                "opens_in": 0,
            }
        else:
            next_open = open_dt if local_now < open_dt else open_dt + timedelta(days=1)
            opens_in = max(0, int((next_open - local_now).total_seconds() // 60))
            active_sessions[session_name] = {
                "active": False,
                "closes_in": 0,
                "opens_in": opens_in,
            }

    return active_sessions


def display_session_status(selected_zones: list):
    """แสดง Live Session Status ว่า session ไหนเปิด/ปิด/กำลังจะเปิด"""
    now = datetime.now(THAI_TZ)
    active_sessions = get_active_sessions(now)
    
    st.subheader("📊 Trading Session Status")
    
    # สร้าง status cards
    cols = st.columns(min(3, len(selected_zones)))
    
    col_idx = 0
    for zone_key in selected_zones:
        if zone_key not in TIMEZONE_CONFIG or zone_key == "gmt":
            continue
        
        if zone_key not in active_sessions:
            continue
        
        config = TIMEZONE_CONFIG[zone_key]
        session = active_sessions[zone_key]
        
        with cols[col_idx % 3]:
            if session["active"]:
                # Session Active
                closes_hours = session["closes_in"] // 60
                closes_mins = session["closes_in"] % 60
                
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, {config['color']} 0%, rgba(255,255,255,0.1) 100%);
                        border: 2px solid {config['color']};
                        border-radius: 10px;
                        padding: 15px;
                        margin-bottom: 10px;
                    ">
                        <div style="color: white; font-weight: bold; margin-bottom: 5px;">
                            {config['status_badge']} {config['name']}
                        </div>
                        <div style="color: #00FF00; font-size: 1.2em; font-weight: bold;">
                            🟢 ACTIVE!
                        </div>
                        <div style="color: white; font-size: 0.9em; margin-top: 5px;">
                            Closes in {closes_hours}h {closes_mins}m
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            else:
                # Session Closed
                opens_hours = session["opens_in"] // 60
                opens_mins = session["opens_in"] % 60
                
                status_color = "#FF9500" if opens_hours < 1 else "#868E96"
                status_text = "🟡 OPENING SOON!" if opens_hours < 1 else "🔴 CLOSED"
                
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, {status_color} 0%, rgba(255,255,255,0.1) 100%);
                        border: 2px solid {status_color};
                        border-radius: 10px;
                        padding: 15px;
                        margin-bottom: 10px;
                    ">
                        <div style="color: white; font-weight: bold; margin-bottom: 5px;">
                            {config['status_badge']} {config['name']}
                        </div>
                        <div style="color: white; font-size: 1.2em; font-weight: bold;">
                            {status_text}
                        </div>
                        <div style="color: white; font-size: 0.9em; margin-top: 5px;">
                            Opens in {opens_hours}h {opens_mins}m
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        
        col_idx += 1
    
    # Check for Golden Hours (London-NY Overlap)
    now_gmt = now.astimezone(timezone.utc)
    current_hour = now_gmt.hour + (now_gmt.minute / 60)
    
    if 13 <= current_hour < 17:  # 13:00-17:00 GMT
        st.warning("⭐ **GOLDEN HOUR!** London-NY Overlap (13:00-17:00 GMT = 20:00-00:00 Bangkok) - BEST TRADING TIME! High volume & volatility!")



# 5. ตัวช่วยแปลงค่าตัวเลข (K/M/B, %, วงเล็บติดลบ)
# ==========================================
def parse_numeric_value(raw: str):
    """แปลงสตริงอย่าง '1.2M', '-0.3%', '(2.1K)' ให้เป็น float จริง"""
    if raw is None:
        return None
    s = raw.strip()
    if s == "" or s.upper() in ("N/A", "NA", "-"):
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


def parse_iso_datetime(date_str: str) -> datetime:
    """แปลงสตริงวันที่ ISO8601"""
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    return datetime.fromisoformat(date_str)


def format_dual_time(dt_thai: datetime) -> str:
    """แสดงเวลาคู่: เวลาไทย (หลัก) พร้อมเวลา MT4/MT5 Server ในวงเล็บ"""
    server_time = dt_thai.astimezone(MT4_MT5_TZ)
    return f"{dt_thai.strftime('%H:%M')} น. (MT4/MT5 {server_time.strftime('%H:%M')})"


# ==========================================
# 6. ระบบดึงข้อมูลหลังบ้าน
# ==========================================
@st.cache_data(ttl=300)
def fetch_today_news():
    """คืนค่า (news_list, error_message)
    ลอง fetch ใหม่อัตโนมัติสูงสุด 3 ครั้ง (รอ 1 วิ แล้ว 2 วิ ก่อนลองใหม่) กันปัญหาเน็ตสะดุดชั่วคราว
    (ตัว cache ttl=300 ช่วยให้ retry loop นี้ทำงานจริงแค่ตอน cache หมดอายุเท่านั้น ไม่ยิงถี่)"""
    data = None
    last_error = None

    for attempt in range(3):
        if attempt > 0:
            time.sleep(attempt)  # backoff แบบง่าย: รอ 1 วิ ก่อนครั้งที่ 2, รอ 2 วิ ก่อนครั้งที่ 3
        try:
            res = requests.get(NEWS_URL, headers=HTTP_HEADERS, timeout=10)
            res.raise_for_status()
            data = res.json()
            last_error = None
            break
        except requests.exceptions.RequestException as e:
            last_error = f"เชื่อมต่อ Calendar API ไม่สำเร็จ ({type(e).__name__})"
            continue
        except ValueError:
            last_error = "รูปแบบข้อมูลข่าวที่ได้รับไม่ถูกต้อง (JSON parse error)"
            break  # ข้อมูลผิดรูปแบบ ลองใหม่ก็ไม่ช่วย ไม่ต้อง retry

    if data is None:
        return [], last_error or "ไม่ทราบสาเหตุ"

    today_date = datetime.now(THAI_TZ).strftime("%Y-%m-%d")
    today_news = []
    seen_news = set()  # ใช้สำหรับ deduplicate

    for n in data:
        try:
            # เช็คจาก TARGET_CURRENCIES (ไม่ใช่แค่ USD)
            # แสดงทุกระดับ impact: High (แดง) / Medium (ส้ม) / Low (เหลือง)
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


# ==========================================
# 7. ฟังก์ชันสำหรับส่ง Notification
# ==========================================
def send_notification(title: str, body: str, enable_desktop: bool, enable_sound: bool):
    """ส่ง Desktop Notification และ Sound Alert"""
    if enable_desktop:
        st.components.v1.html(
            f"""
            <script>
            window.showDesktopNotification('{title}', {{
                body: '{body}',
                tag: 'GOLD-alert'
            }});
            </script>
            """,
            height=0
        )
    
    if enable_sound:
        st.components.v1.html(
            """
            <script>
            window.playNotificationSound();
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

    if enable_notifications:
        enable_desktop_notif = st.checkbox("💻 Desktop Popup", value=saved_settings["enable_desktop_notif"], help="แสดง Notification ที่มุมจอ")
        enable_sound_notif = st.checkbox("🔊 Sound Alert", value=saved_settings["enable_sound_notif"], help="เล่นเสียงเตือน")
        notify_upcoming = st.checkbox("⏰ เตือนก่อน 5-10 นาที", value=saved_settings["notify_upcoming"], help="เตือนข่าวที่กำลังจะออก")
        notify_released = st.checkbox("✅ เตือนเมื่อข่าวออก", value=saved_settings["notify_released"], help="เตือนทันทีเมื่อข่าวเพิ่งออก")
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
            # st.fragment รีเฟรชเฉพาะส่วนข่าว ไม่ล้าง scroll/expander ที่เปิดอยู่
            st.caption("✅ รีเฟรชเฉพาะส่วนข่าว (st.fragment) — ไม่ล้าง dropdown ที่เปิดอยู่")
        elif HAS_AUTOREFRESH:
            st_autorefresh(interval=refresh_seconds * 1000, key="dashboard_autorefresh")
            st.caption("⚠️ รีเฟรชทั้งหน้า — อัปเดต Streamlit เป็น ≥1.33 เพื่อใช้ st.fragment จะลื่นกว่านี้")
        else:
            st.info(
                "ยังไม่ได้ติดตั้ง `streamlit-autorefresh` และ Streamlit เวอร์ชันนี้ไม่รองรับ st.fragment\n\n"
                "แนะนำอัปเดต Streamlit เป็นเวอร์ชันล่าสุด หรือติดตั้ง:\n```\npip install streamlit-autorefresh\n```"
            )

    # บันทึกการตั้งค่าปัจจุบันลงไฟล์ทุกครั้งที่ sidebar rerun (แก้ปัญหาค่าหายตอนรีเฟรชเบราว์เซอร์)
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
    })

    st.caption(f"เวลาปัจจุบัน: {datetime.now(THAI_TZ).strftime('%H:%M:%S น.')}")
    st.caption("💾 การตั้งค่าถูกจำไว้อัตโนมัติ แม้รีเฟรชเบราว์เซอร์")
    st.divider()

    if st.button("🔄 ล้างแคชและโหลดใหม่ทั้งหมด", use_container_width=True):
        st.cache_data.clear()
        st.session_state.notified_upcoming.clear()
        st.session_state.notified_released.clear()
        st.rerun()

    if st.button("♻️ รีเซ็ตการตั้งค่าเป็นค่าเริ่มต้น", use_container_width=True,
                 help="ล้างการตั้งค่าที่จำไว้ในไฟล์ user_settings.json กลับไปใช้ค่า default ทั้งหมด"):
        try:
            SETTINGS_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        st.rerun()

    st.divider()
    st.caption(
        "แหล่งข้อมูล: ForexFactory (ผ่าน JSON export feed, จำกัด 2 ครั้ง/5 นาที — "
        "แอปนี้ cache ไว้แล้วให้ปลอดภัย)\n\n"
        "⚠️ ใช้เพื่อประกอบการตัดสินใจเท่านั้น ไม่ใช่คำแนะนำการลงทุน"
    )

# ==========================================
# 9. ส่วนแสดงผล: หัวข้อ + นาฬิกาเวลาสด
# ==========================================
st.title("🥇 Gold News")
st.markdown("ติดตามข่าวเศรษฐกิจและเหตุการณ์สำคัญทั่วโลกที่มีผลต่อราคาทองคำ (GOLD) อัปเดตอัตโนมัติ")

# ==========================================
# Breaking News Section (ย้ายขึ้นบนสุด + เก็บลง session_state
# แก้ปัญหาเดิม: โพสต์แล้วพอมีการโต้ตอบอื่นในหน้า การ์ดก็หายไปเพราะไม่เคยถูกเก็บไว้เลย)
# ==========================================
st.subheader("🚨 Breaking News Alert")

col_bn1, col_bn2 = st.columns([3, 1])

with col_bn1:
    breaking_news_type = st.selectbox(
        "📰 ประเภทข่าว",
        ["(ไม่มี)",
         "🏛️ ผู้นำประเทศ/นักการเมือง",      # เช่น Trump, ผู้นำประเทศอื่นๆ (ไม่จำกัดแค่สหรัฐฯ)
         "🌍 ภูมิรัฐศาสตร์/สงคราม",
         "🏦 ธนาคารกลาง (Fed/ECB/BOJ/BOE/PBOC)",
         "📉 ตลาดการเงินปั่นป่วน (Crash/Rally)",
         "🏦 วิกฤตธนาคาร/สภาพคล่อง",
         "💱 ข่าวเฉพาะสกุลเงิน",              # เลือกสกุลเงินเพิ่มด้านล่าง
         "🛢️ Commodity/น้ำมัน/Supply Shock",
         "🏛️ กฎหมาย/นโยบายรัฐ"],
        key="bn_type",
        help="เลือกประเภทที่ใกล้เคียงที่สุด ไม่จำกัดแค่ข่าว USD เพราะทองคำถูกกระทบจากหลายสกุลเงิน/เหตุการณ์ทั่วโลก"
    )

    breaking_news_currency = None
    if breaking_news_type == "💱 ข่าวเฉพาะสกุลเงิน":
        breaking_news_currency = st.selectbox(
            "เกี่ยวกับสกุลเงินไหน",
            options=TARGET_CURRENCIES,
            format_func=get_currency_badge,
            key="bn_currency"
        )

with col_bn2:
    if st.checkbox("📢 มีข่าวใหม่?", key="bn_checkbox"):
        breaking_news_text = st.text_area(
            "ข้อมูลข่าว",
            placeholder="เช่น: Trump announces 25% tariff on China...",
            height=60,
            key="bn_text"
        )

        if breaking_news_text and breaking_news_type != "(ไม่มี)":
            news_impact = st.radio(
                "ผลกระทบต่อทองคำ",
                ["Gold UP 🚀", "Gold DOWN 📉", "ยังไม่แน่ใจ"],
                key="bn_impact"
            )

            if st.button("🚨 POST BREAKING NEWS", key="bn_button"):
                # เก็บลง session_state — คงอยู่ตลอด session ไม่หายเมื่อหน้ามีการโต้ตอบอื่น
                st.session_state.breaking_news_log.insert(0, {
                    "type": breaking_news_type,
                    "currency": breaking_news_currency,  # None ถ้าไม่ใช่ประเภท "ข่าวเฉพาะสกุลเงิน"
                    "text": breaking_news_text,
                    "impact": news_impact,
                    "time": datetime.now(THAI_TZ).strftime("%H:%M:%S น."),
                })
                st.session_state.breaking_news_log = st.session_state.breaking_news_log[:20]  # เก็บ 20 รายการล่าสุดพอ

                notif_title = f"🚨 BREAKING NEWS: {breaking_news_type}"
                if breaking_news_currency:
                    notif_title += f" ({breaking_news_currency})"

                send_notification(
                    notif_title,
                    f"Gold: {news_impact}\n{breaking_news_text[:100]}...",
                    True,
                    True
                )
                st.rerun()

# แสดง Breaking News ล่าสุด (การ์ดใหญ่) + ประวัติก่อนหน้า (อ่านจาก session_state ทุกครั้ง จึงไม่หาย)
if st.session_state.breaking_news_log:
    latest = st.session_state.breaking_news_log[0]
    latest_color = "#00D084" if "UP" in latest["impact"] else ("#FF3B30" if "DOWN" in latest["impact"] else "#868E96")
    latest_icon = "🚀" if "UP" in latest["impact"] else ("📉" if "DOWN" in latest["impact"] else "❓")
    latest_type_label = latest["type"]
    if latest.get("currency"):
        latest_type_label += f" {get_currency_badge(latest['currency'])}"

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {latest_color} 0%, rgba(255,255,255,0.1) 100%);
            border: 3px solid {latest_color};
            border-radius: 15px;
            padding: 20px;
            margin: 10px 0 20px 0;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        ">
            <div style="color: white; font-size: 1.3em; font-weight: bold; margin-bottom: 8px;">
                🚨 {latest_type_label}
            </div>
            <div style="color: white; font-size: 0.95em; margin-bottom: 10px; line-height: 1.6;">
                {latest['text']}
            </div>
            <div style="color: white; font-size: 1.1em; font-weight: bold;">
                💰 Expected Impact: {latest['impact']} {latest_icon}
            </div>
            <div style="color: white; font-size: 0.8em; margin-top: 8px; opacity: 0.8;">
                ⏰ {latest['time']}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if len(st.session_state.breaking_news_log) > 1:
        with st.expander(f"📜 ประวัติ Breaking News ก่อนหน้า ({len(st.session_state.breaking_news_log) - 1} รายการ)"):
            for entry in st.session_state.breaking_news_log[1:]:
                entry_type_label = entry["type"]
                if entry.get("currency"):
                    entry_type_label += f" {get_currency_badge(entry['currency'])}"
                st.markdown(f"**[{entry['time']}] {entry_type_label}** — {entry['text']} → **{entry['impact']}**")

    if st.button("🗑️ ล้างประวัติ Breaking News", key="bn_clear"):
        st.session_state.breaking_news_log = []
        st.rerun()

st.markdown("---")

# แสดง Multi-Timezone Clocks พร้อมสี (อัปเดตเองด้วย JS ทุกวินาที ไม่ต้องพึ่ง Python rerun)
if selected_timezones:
    st.subheader("🌍 เวลาปัจจุบันในแต่ละ Zone")
    display_timezone_clocks(selected_timezones)
else:
    st.warning("⚠️ กรุณาเลือก Timezone อย่างน้อย 1 อันจากแถบด้านซ้าย")

st.markdown("---")

# ==========================================
# ส่วนแสดงผลข่าว + Session Status + การแจ้งเตือน
# ห่อด้วย st.fragment เพื่อรีเฟรชเฉพาะส่วนนี้เป็นระยะ โดยไม่ล้าง scroll/expander
# ของส่วนอื่นในหน้า (เช่น Breaking News ด้านบน) — แก้ปัญหาเดิมที่ full-page
# autorefresh ทำให้ dropdown ที่เปิดอยู่ปิดหมดทุกรอบ
# ==========================================
def render_live_section():
    # --- Live Session Status ---
    if selected_timezones:
        display_session_status(selected_timezones)
        st.markdown("---")

    now = datetime.now(THAI_TZ)

    news_list, news_error = fetch_today_news()

    # กรองตามสกุลเงินที่เลือกไว้ใน sidebar
    if not selected_currencies:
        news_list = []
    elif news_list:
        news_list = [n for n in news_list if n.get("country") in selected_currencies]

    if news_error:
        st.error(
            f"⚠️ **ดึงข้อมูลข่าวไม่สำเร็จ:** {news_error}\n\n"
            "ข้อมูลด้านล่างอาจไม่ครบถ้วน กรุณากดปุ่ม 'ล้างแคชและโหลดใหม่ทั้งหมด' ที่แถบด้านซ้าย"
        )
    elif not selected_currencies:
        st.warning("⚠️ กรุณาเลือกอย่างน้อย 1 สกุลเงินที่แถบด้านซ้าย เพื่อแสดงข่าว")
    elif not news_list:
        st.success(
            "✅ **วันนี้ไม่มีข่าวสำคัญ (แดง/ส้ม/เหลือง) ของสกุลเงินที่เลือก** - "
            "กราฟทองคำมีแนวโน้มวิ่งตามเทคนิคอล (Support/Resistance) ตามปกติ"
        )
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

        # ==========================================
        # Logic การแจ้งเตือน
        # ==========================================
        if enable_notifications:
            for n, n_time in upcoming_news:
                news_id = f"{n.get('date')}_{n.get('title', '').replace(' ', '_')}"
                time_until = (n_time - now).total_seconds()

                # เตือน "กำลังจะออก" เมื่อเหลือ 5-10 นาที
                if notify_upcoming and time_until > 0 and time_until <= 600:  # 10 นาที = 600 วิ
                    if news_id not in st.session_state.notified_upcoming:
                        info = translate_news(n.get("title", ""))
                        title_display = info["th"] or n.get("title", "")
                        impact = n.get("impact", "")

                        send_notification(
                            f"⚠️ ข่าว {title_display} กำลังจะออก!",
                            f"อีก {int(time_until // 60)} นาที (เวลา {format_dual_time(n_time)})\nระดับ: {impact}",
                            enable_desktop_notif,
                            enable_sound_notif
                        )
                        st.session_state.notified_upcoming.add(news_id)

                # เตือน "เพิ่งออก" ถ้าเวลาผ่านไป
                if notify_released and time_until <= 0 and time_until > -600:  # เพิ่งออกไป 10 นาที
                    if news_id not in st.session_state.notified_released:
                        info = translate_news(n.get("title", ""))
                        title_display = info["th"] or n.get("title", "")
                        actual = n.get("actual") or "รอข้อมูล"

                        send_notification(
                            f"✅ ข่าว {title_display} เพิ่งออก!",
                            f"ตัวเลขจริง: {actual}",
                            enable_desktop_notif,
                            enable_sound_notif
                        )
                        st.session_state.notified_released.add(news_id)

        # ---------------------------------------------------------
        # Dashboard Summary — สรุปภาพรวมแบบเห็นปุ๊บรู้ปั๊บ
        # ---------------------------------------------------------
        high_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "High")
        medium_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "Medium")
        low_count = sum(1 for n, _ in past_news + upcoming_news if n.get("impact") == "Low")

        active_sessions_summary = get_active_sessions(now)
        active_zone_names = [
            TIMEZONE_CONFIG[z]["name"] for z in selected_timezones
            if z != "gmt" and active_sessions_summary.get(z, {}).get("active")
        ]
        now_gmt = now.astimezone(timezone.utc)
        is_golden_hour = 13 <= (now_gmt.hour + now_gmt.minute / 60) < 17

        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        with sum_col1:
            if is_golden_hour:
                st.metric("Session ตอนนี้", "⭐ Golden Hour")
            elif active_zone_names:
                st.metric("🟢 Active", " + ".join(active_zone_names))
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
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            info = translate_news(next_news.get("title", ""))
            display_th = info["th"] or next_news.get("title", "")

            next_currency = next_news.get("country", "N/A")

            st.markdown("### 🚨 ข่าวสำคัญต่อไปที่กำลังจะออก")
            col1, col2 = st.columns([1, 2])
            impact_level = next_news.get("impact", "")
            with col1:
                if impact_level == "High":
                    st.error(f"## ⏳ อีก {hours} ชม. {minutes} นาที")
                elif impact_level == "Medium":
                    st.warning(f"## ⏳ อีก {hours} ชม. {minutes} นาที")
                else:
                    st.info(f"## ⏳ อีก {hours} ชม. {minutes} นาที")
                st.write(f"เวลา: **{format_dual_time(next_time)}**")
                st.markdown(f"ระดับ: {impact_badge_html(impact_level)} | {get_currency_badge(next_currency)}", unsafe_allow_html=True)
            with col2:
                st.warning(f"### {display_th} ({next_news.get('title', 'N/A')})")
                st.write(f"📌 **ผลกระทบ:** {info['impact']}")
                st.write(
                    f"📊 **คาดการณ์:** {next_news.get('forecast') or 'ไม่มีข้อมูล'} | "
                    f"**ครั้งก่อน:** {next_news.get('previous') or 'ไม่มีข้อมูล'}"
                )

            st.markdown("---")

            if len(upcoming_news) > 1:
                st.subheader("📅 ข่าวอื่นๆ ที่รอประกาศในวันนี้")
                for n, n_time in upcoming_news[1:]:
                    info = translate_news(n.get("title", ""))
                    display_th = info["th"] or n.get("title", "")
                    badge = impact_emoji(n.get("impact", ""))
                    currency_b = get_currency_badge(n.get("country", ""))  # ดึงธงชาติ

                    with st.expander(f"{badge} {currency_b} | ⏰ {format_dual_time(n_time)} - {display_th}"):
                        st.markdown(f"**สกุลเงิน:** {currency_b} | **ความรุนแรง:** {impact_badge_html(n.get('impact', ''))}", unsafe_allow_html=True)
                        st.write(f"**การวิเคราะห์:** {info['impact']}")
                        st.write(
                            f"**คาดการณ์:** {n.get('forecast') or 'ไม่มีข้อมูล'} | "
                            f"**ครั้งก่อน:** {n.get('previous') or 'ไม่มีข้อมูล'}"
                        )
        else:
            st.info("✅ ไม่มีข่าวสำคัญที่รอประกาศแล้วสำหรับวันนี้")

        # ---------------------------------------------------------
        # สรุปผล: ข่าวที่ประกาศไปแล้ว
        # ---------------------------------------------------------
        if past_news:
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("✅ สรุปผลข่าวที่ประกาศไปแล้ววันนี้ (ล่าสุดก่อน)")

            for n, n_time in past_news:
                info = translate_news(n.get("title", ""))
                display_th = info["th"] or n.get("title", "")
                actual_raw = n.get("actual") or "N/A"
                forecast_raw = n.get("forecast") or "N/A"
                previous_raw = n.get("previous") or "N/A"
                badge = impact_emoji(n.get("impact", ""))

                with st.expander(f"{badge} ✔️ ข่าวออกแล้วเวลา {format_dual_time(n_time)}: {display_th}", expanded=True):
                    st.markdown(impact_badge_html(n.get("impact", "")), unsafe_allow_html=True)

                    if actual_raw == forecast_raw == previous_raw == "N/A":
                        # ข่าวประเภทแถลงการณ์/สุนทรพจน์ ไม่มีตัวเลขให้เทียบ ไม่ต้องโชว์กล่อง N/A ซ้ำ 3 อัน
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
                            st.info(
                                "💡 **วิเคราะห์:** ตัวเลขจริง **สูงกว่า** คาดการณ์ "
                                "(โดยทั่วไปดอลลาร์มักจะแข็งค่า / ทองคำมักจะโดนกดดัน 📉) "
                                "— ทิศทางจริงต้องดูบริบทของข่าวนั้นๆ ประกอบด้วย"
                            )
                        elif a_val < f_val:
                            st.info(
                                "💡 **วิเคราะห์:** ตัวเลขจริง **ต่ำกว่า** คาดการณ์ "
                                "(โดยทั่วไปดอลลาร์มักจะอ่อนค่า / ทองคำมักจะพุ่งขึ้น 🚀) "
                                "— ทิศทางจริงต้องดูบริบทของข่าวนั้นๆ ประกอบด้วย"
                            )
                        else:
                            st.info("💡 **วิเคราะห์:** ตัวเลขจริงเท่ากับคาดการณ์พอดี ผลกระทบต่อตลาดมักจะจำกัด")
                    else:
                        st.write("💡 ยังไม่มีตัวเลขให้เปรียบเทียบ หรือรออีก 5-15 นาทีให้ตลาดสะท้อนราคาแล้วดูทิศทางกราฟจริงครับ")


# เรียกใช้งาน: ถ้า Streamlit รองรับ st.fragment และเปิด auto-refresh ไว้ ให้ห่อด้วย fragment
# (รีเฟรชเฉพาะส่วนนี้ทุก refresh_seconds วิ ไม่กระทบ Breaking News/นาฬิกาด้านบน)
if auto_refresh_on and HAS_FRAGMENT:
    render_live_section = st.fragment(run_every=refresh_seconds)(render_live_section)

render_live_section()

st.markdown("---")
st.caption(
    "🔔 แดชบอร์ดนี้เป็นเครื่องมือช่วยประกอบการตัดสินใจเท่านั้น ไม่ใช่คำแนะนำการลงทุน "
    "โปรดบริหารความเสี่ยงและตรวจสอบข่าวจากแหล่งทางการก่อนเทรดจริงเสมอ"
)