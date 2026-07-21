readme_content = """# 🥇 Gold News Calendar Assistant

![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

โปรแกรมสำหรับติดตามข่าวสารเศรษฐกิจโลกที่มีผลกระทบต่อราคาทองคำ (Gold) และตลาด Forex พัฒนาด้วย Python และ Streamlit โดยดึงข้อมูลแบบ Real-time จาก ForexFactory (ผ่าน JSON Feed โดยไม่ต้องใช้ API Key) มาพร้อมกับระบบแจ้งเตือนผ่าน Desktop, เสียงเตือน, และการคำนวณช่วงเวลา Trading Session แบบอัตโนมัติ

---

## ✨ ฟีเจอร์เด่น (Key Features)

- **🔄 Real-time Data Sync:** ดึงข้อมูลข่าวเศรษฐกิจแบบอัปเดตอัตโนมัติตามเวลาที่ตั้งไว้ (Auto-Refresh) 
- **🌍 Multi-Timezone Tracking:** เทียบเวลาท้องถิ่นกับเวลาเซิร์ฟเวอร์ (GMT) และตลาดหลัก (Tokyo, London, New York, Sydney) ให้โดยอัตโนมัติ
- **📊 Trading Session Status:** ตรวจสอบสถานะตลาดว่าเปิดหรือปิด รวมถึงแจ้งเตือน **Golden Hour** (ช่วงที่ตลาด London และ New York เปิดซ้อนทับกัน ซึ่งเป็นช่วงที่กราฟผันผวนสูง)
- **🔔 Notification System:** 
  - รองรับการแจ้งเตือนแบบ **Desktop Popup** เมื่อข่าวใกล้จะประกาศ (ล่วงหน้า 5-10 นาที) หรือเมื่อข่าวประกาศแล้ว
  - รองรับระบบ **Sound Alert** (เสียงเตือน) พร้อมปรับแต่งโทนเสียงและระดับความดังได้
- **🧠 Impact Analysis (Knowledge Base):** วิเคราะห์ผลกระทบของข่าวที่มีต่อราคาทองคำเบื้องต้น (เช่น NFP, CPI, FED) พร้อมอธิบายกลไกที่ส่งผลต่อตลาดแบบเข้าใจง่าย
- **💱 Currency Filtering:** เลือกกรองเฉพาะสกุลเงินที่ต้องการติดตามได้ (เช่น USD, EUR, GBP, JPY)
- **💾 Auto-Save Settings:** ระบบบันทึกการตั้งค่าผู้ใช้อัตโนมัติในไฟล์ `.json` ไม่ต้องตั้งค่าใหม่ทุกครั้งที่เปิดโปรแกรม

---

## 🛠 ความต้องการของระบบ (Prerequisites)

- Python 3.9 หรือใหม่กว่า
- Web Browser ที่รองรับ Web Notifications API (เช่น Google Chrome, Microsoft Edge, Safari)

**Dependencies ที่สำคัญ:**
- `streamlit`
- `requests`
- `streamlit-autorefresh` (แนะนำสำหรับการรีเฟรชหน้าจออัตโนมัติ)

---

## 🚀 การติดตั้งและเปิดใช้งาน (Installation & Usage)

1. **โคลนโปรเจกต์ลงมาที่เครื่อง (Clone the repository)**
   ```bash
   git clone [https://github.com/sarawutms/gold-news-calendar.git](https://github.com/sarawutms/gold-news-calendar.git)
   cd gold-news-calendar
