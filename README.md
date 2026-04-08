# Screen Translator 🌐

نظام ترجمة شاشة متكامل — يلتقط النص من شاشتك تلقائياً ويترجمه للعربية.

## المكونات

| المكون | التقنية | الوصف |
|--------|---------|-------|
| **Client** | Python + PyQt6 | تطبيق ويندوز مع overlay شفاف |
| **Server** | FastAPI + Ollama | سيرفر الترجمة (aya-expanse:8b) |
| **Dashboard** | Jinja2 + TailwindCSS | لوحة تحكم الإدارة |

---

## 🚀 تشغيل السيرفر

### المتطلبات
- Docker + Docker Compose
- Ollama مثبت ومشغل مع نموذج `aya-expanse:8b`

### التثبيت

```bash
cd server

# نسخ ملف البيئة
cp .env.example .env
# عدّل .env وضع SECRET_KEY قوي

# تشغيل السيرفر والـ Ollama
docker-compose up -d

# تحميل النموذج (أول مرة فقط)
docker exec -it screen-translator-ollama ollama pull aya-expanse:8b
```

السيرفر يعمل على: `http://localhost:8000`
الداشبورد: `http://localhost:8000/dashboard`

**بيانات الدخول الافتراضية:** `admin` / `admin123`
> ⚠️ غيّر الباسورد فور الدخول!

### إنشاء Admin من الـ Terminal

```bash
cd server
pip install bcrypt
python setup_admin.py --username admin --password YourStrongPassword
```

---

## 💻 تشغيل الكلايت (ويندوز)

### المتطلبات
- Python 3.11+
- Windows 10/11

### التثبيت

```bash
cd client
pip install -r requirements.txt

# تشغيل البرنامج
python src/main.py
```

### الإعداد
1. شغّل البرنامج — يظهر في الـ System Tray
2. انقر يمين على الأيقونة → إعدادات
3. في تبويب الاتصال: أدخل رابط السيرفر + API Key
4. اسحب المربع الأخضر فوق النص اللي تريد ترجمته
5. الترجمة تظهر تلقائياً كل ثانيتين

---

## 🔑 إدارة مفاتيح API

من الداشبورد:
1. الصفحة الرئيسية → **المستخدمون** → أضف مستخدم جديد
2. **مفاتيح API** → أنشئ مفتاح جديد → انسخه (يظهر مرة واحدة فقط!)
3. أعطِ المفتاح للمستخدم ليضعه في إعدادات البرنامج

---

## 📦 بناء الـ Installer (ويندوز)

```bash
cd client
pip install pyinstaller
python installer/build.py
```

الـ installer يُنشأ في: `client/installer/Output/ScreenTranslatorSetup.exe`

---

## 🔄 نظام التحديث التلقائي

عند رفع إصدار جديد على GitHub:

1. عدّل `server/versions.json` بالإصدار الجديد ورابط التحميل
2. ارفع الملف للسيرفر
3. البرنامج يفحص تلقائياً عند كل تشغيل ويعلم المستخدمين

```json
{
  "version": "1.1.0",
  "download_url": "https://github.com/OWNER/REPO/releases/download/v1.1.0/ScreenTranslatorSetup.exe",
  "release_notes": "تحسينات الأداء وإصلاح الأخطاء",
  "released_at": "2026-04-08T00:00:00Z",
  "min_version": "1.0.0"
}
```

---

## 📡 API Reference

### ترجمة نص
```http
POST /api/v1/translate
X-API-Key: sk-xxxxxxxxxxxxxxxx
Content-Type: application/json

{
  "text": "Hello World",
  "source_language": "auto",
  "target_language": "ar"
}
```

### التحقق من API Key
```http
POST /api/v1/auth/validate
Content-Type: application/json

{"api_key": "sk-..."}
```

### صحة السيرفر
```http
GET /api/v1/health
```

---

## 🗂️ هيكل المشروع

```
screen-translator/
├── client/          # تطبيق ويندوز (PyQt6)
├── server/          # FastAPI + Ollama
├── dashboard/       # لوحة التحكم
└── docs/            # التوثيق
```

---

## 📄 الرخصة

MIT License
