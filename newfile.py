# -*- coding: utf-8 -*-
"""
Yangi Mahalliy Xizmatlar — rasmiy Telegram bot (mini appga mos).

Imkoniyatlar:
  • Xizmatlar ro'yxati + bot orqali buyurtma berish
  • Premium va Donat bo'limlari (narxlar mini app bilan avtomatik bir xil)
  • Aloqa: foydalanuvchi yozadi -> admin javob beradi (reply orqali)
  • Admin: yangi buyurtma / Premium so'rovi / do'kon buyurtmasi / donat bildirishnomalari
  • Admin buyruqlari: /stats, /status, /broadcast

O'rnatish:  pip install pyTelegramBotAPI
Ishga tushirish:  python bot.py
"""

import base64
import functools
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape as _escape

# ============================================================
# 1) SOZLAMALAR — faqat shu qismni o'zgartiring
# ============================================================
TOKEN = "8839436278:AAFe_LPMB1VdGl6TfKPsG5uD9qcQNrk_7P4"  # @BotFather bergan YANGI token
ADMIN_ID = 8545919348                             # sizning Telegram ID raqamingiz (@userinfobot beradi)
MINI_APP_URL = "https://cozy-gelato-2487b2.netlify.app/"                        # mini app havolasi (https:// bilan boshlansin)
APP_NAME = "Digital Hub"    # ilova nomi (Firebase'dagi nom ustun turadi)

# Mini app ma'lumotlar bazasi (Firebase). Odatda o'zgartirish shart emas.
FIREBASE_DB_URL = "https://telegram-bot-e7974-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = "AIzaSyD_dMDUrLDdEk2NugrE_RvmoaIJhxUhDUo"
LIVE_DATA = True        # True: xizmat/narx/karta ma'lumotlari ilovadan avtomatik olinadi
NOTIFY_ADMIN = True     # True: ilovadagi yangi buyurtma va so'rovlar adminga keladi
POLL_SECONDS = 30       # yangi buyurtmalarni tekshirish oralig'i (soniya)

# Hosting uchun: muhit o'zgaruvchilari berilgan bo'lsa, ular ustun turadi
TOKEN = os.getenv("BOT_TOKEN", TOKEN).strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", ADMIN_ID))
MINI_APP_URL = os.getenv("MINI_APP_URL", MINI_APP_URL).strip()

# Ilovadan o'qib bo'lmaganda ko'rsatiladigan xizmatlar (mini appdagi bilan bir xil)
FALLBACK_SERVICES = [
    {"title": "Telegram Bot Yasash", "desc": "Murakkab botlar", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Veb-sayt Dasturlash", "desc": "Landing page va saytlar", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Telegram Mini App", "desc": "Zamonaviy ilovalar", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "24/7 Server Hosting", "desc": "Botlarni serverga qo'yish", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "UI/UX Dizayn", "desc": "Mobil ilova dizaynlari", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Python Script", "desc": "Avtomatlashtirish", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "YouTube SEO", "desc": "Videolarni optimizatsiya", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Grafik Dizayn", "desc": "Logotip va bannerlar", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Texnik Yordam", "desc": "Konsultatsiya", "price": 0, "days": "", "cat": "", "url": ""},
    {"title": "Maxsus Yechimlar", "desc": "Sizning g'oyangiz asosida", "price": 0, "days": "", "cat": "", "url": ""},
]

DEFAULT_PLANS = {
    "premium": {"active": True, "name": "", "price": 29000, "oldPrice": 0, "days": 30, "perks": ""},
    "plus": {"active": True, "name": "", "price": 59000, "oldPrice": 0, "days": 30, "perks": ""},
}
DEFAULT_PERKS = {
    "premium": "Profilda Premium nishoni|Buyurtmalar navbatsiz ko'riladi|Maxsus chegirmalar|Qo'llab-quvvatlash ustuvorligi",
    "plus": "Premium'ning barcha imkoniyatlari|Profilda Plus nishoni|Eng tezkor javob|Yangi imkoniyatlarga birinchi kirish",
}
PLAN_NAMES = {"premium": "Premium", "plus": "Premium Plus"}

# ============================================================
# 2) YORDAMCHI FUNKSIYALAR
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TZ = timezone(timedelta(hours=5))  # O'zbekiston vaqti


def escape(text):
    """HTML uchun xavfsiz matn (apostrof va qo'shtirnoqni o'zgartirmaydi)."""
    return _escape(str(text), quote=False)


def num(value, default=0.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v


def money(value):
    return f"{int(round(num(value))):,}".replace(",", " ")


def short(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def safe_url(value):
    value = str(value or "").strip()
    return value if re.match(r"^https?://[^\s]+$", value, re.I) else ""


def fmt_time(ts):
    try:
        return datetime.fromtimestamp(float(ts) / 1000.0, TZ).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def full_name(user):
    name = " ".join(x for x in [user.first_name, getattr(user, "last_name", None)] if x).strip()
    return name or "Foydalanuvchi"


# ============================================================
# 3) TEKSHIRUV VA BOTNI YARATISH
# ============================================================
if ":" not in TOKEN or "BU_YERGA" in TOKEN:
    print("❌ Fayl boshidagi TOKEN ga (yoki BOT_TOKEN ga) @BotFather bergan tokenni yozing.")
    sys.exit(1)

import telebot  # noqa: E402
from telebot import types  # noqa: E402
from telebot.apihelper import ApiTelegramException  # noqa: E402

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)
BOT_USERNAME = ""  # ishga tushganda avtomatik to'ldiriladi

# ============================================================
# 4) FOYDALANUVCHILAR RO'YXATI (users.json)
# ============================================================
USERS_FILE = os.path.join(BASE_DIR, "users.json")
lock = threading.Lock()
waiting = {}    # uid -> {"kind": "contact" | "order", "service": "..."}
last_sent = {}  # uid -> oxirgi xabar yuborgan vaqt (spamdan himoya)


def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return set(int(x) for x in json.load(f))
    except (FileNotFoundError, ValueError, TypeError):
        return set()


users = load_users()


def _save_users():
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(users), f)
    os.replace(tmp, USERS_FILE)


def add_user(uid):
    with lock:
        if uid not in users:
            users.add(uid)
            try:
                _save_users()
            except OSError as e:
                print("users.json ga yozib bo'lmadi:", e)


def remove_user(uid):
    with lock:
        if uid in users:
            users.discard(uid)
            try:
                _save_users()
            except OSError as e:
                print("users.json ga yozib bo'lmadi:", e)


# ============================================================
# 5) FIREBASE (mini app ma'lumotlari) — faqat o'qish
# ============================================================
class FbError(Exception):
    def __init__(self, message, code=0):
        super().__init__(message)
        self.code = code


_auth = {"use": False, "id": "", "refresh": "", "exp": 0.0}
_auth_lock = threading.Lock()


def _http_json(url, data=None, headers=None, timeout=8):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise FbError(f"HTTP {e.code}", e.code)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise FbError(str(e))


def _token():
    """Anonim kirish tokeni (ilova ham shunday kiradi). Faqat baza yopiq bo'lsa kerak bo'ladi."""
    if not FIREBASE_API_KEY or "__FIREBASE" in FIREBASE_API_KEY:
        return ""
    with _auth_lock:
        now = time.time()
        if _auth["id"] and now < _auth["exp"] - 60:
            return _auth["id"]
        try:
            if _auth["refresh"]:
                body = urllib.parse.urlencode(
                    {"grant_type": "refresh_token", "refresh_token": _auth["refresh"]}
                ).encode()
                data = _http_json(
                    "https://securetoken.googleapis.com/v1/token?key=" + FIREBASE_API_KEY,
                    body, {"Content-Type": "application/x-www-form-urlencoded"},
                )
                _auth["id"] = data["id_token"]
                _auth["refresh"] = data.get("refresh_token", _auth["refresh"])
                _auth["exp"] = now + float(data.get("expires_in", 3600))
            else:
                body = json.dumps({"returnSecureToken": True}).encode()
                data = _http_json(
                    "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + FIREBASE_API_KEY,
                    body, {"Content-Type": "application/json"},
                )
                _auth["id"] = data["idToken"]
                _auth["refresh"] = data["refreshToken"]
                _auth["exp"] = now + float(data.get("expiresIn", 3600))
        except (FbError, KeyError, TypeError, ValueError):
            _auth["id"] = ""
            _auth["refresh"] = ""
            _auth["exp"] = 0.0
            return ""
        return _auth["id"]


def fb_get(path, params=None, _retry=True):
    query = dict(params or {})
    if _auth["use"]:
        tok = _token()
        if tok:
            query["auth"] = tok
    url = FIREBASE_DB_URL.rstrip("/") + "/" + urllib.parse.quote(path, safe="/-_") + ".json"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    try:
        return _http_json(url, headers={"Accept": "application/json"})
    except FbError as e:
        if e.code in (401, 403) and _retry:
            if not _auth["use"]:
                _auth["use"] = True  # baza yopiq ekan — anonim token bilan urinib ko'ramiz
                return fb_get(path, params, _retry=False)
            with _auth_lock:
                _auth["id"] = ""
                _auth["exp"] = 0.0
            return fb_get(path, params, _retry=False)
        raise


_cache = {}
_fail_until = {}
_cache_lock = threading.Lock()


def live(path, ttl=300):
    """(ok, qiymat). ok=False bo'lsa, ilova bazasidan o'qib bo'lmadi."""
    if not LIVE_DATA:
        return False, None
    now = time.time()
    with _cache_lock:
        item = _cache.get(path)
        blocked = _fail_until.get(path, 0) > now
    if item and now - item[0] < ttl:
        return True, item[1]
    if blocked:
        return (True, item[1]) if item else (False, None)
    try:
        value = fb_get(path)
    except FbError as e:
        print(f"Ilova bazasidan o'qib bo'lmadi ({path}): {e}")
        with _cache_lock:
            _fail_until[path] = now + 60
        return (True, item[1]) if item else (False, None)
    with _cache_lock:
        _cache[path] = (now, value)
        _fail_until.pop(path, None)
    return True, value


def get_settings():
    ok, raw = live("settings")
    return ok, (raw if isinstance(raw, dict) else {})


def app_name():
    ok, s = get_settings()
    name = str(s.get("appName") or "").strip() if ok else ""
    return name or APP_NAME


def parse_services(raw):
    if isinstance(raw, dict):
        values = list(raw.values())
    elif isinstance(raw, list):
        values = raw
    else:
        return []
    items = []
    for v in values:
        if not isinstance(v, dict) or v.get("active") is False:
            continue
        title = str(v.get("title") or "").strip()
        if not title:
            continue
        items.append({
            "title": title,
            "desc": str(v.get("desc") or "").strip(),
            "price": num(v.get("price")),
            "days": str(v.get("days") or "").strip(),
            "cat": str(v.get("cat") or "").strip(),
            "url": safe_url(v.get("url")),
            "order": num(v.get("order")),
        })
    items.sort(key=lambda s: s["order"])
    return items[:40]


def get_services():
    ok, raw = live("services")
    if ok and raw:
        return parse_services(raw)
    return [dict(s) for s in FALLBACK_SERVICES]


def get_plans(settings):
    raw_plans = settings.get("plans") if isinstance(settings.get("plans"), dict) else {}
    plans = []
    for key in ("premium", "plus"):
        data = dict(DEFAULT_PLANS[key])
        raw = raw_plans.get(key)
        if isinstance(raw, dict):
            data.update({k: v for k, v in raw.items() if v is not None})
        if data.get("active") is False:
            continue
        perks_raw = str(data.get("perks") or "").strip() or DEFAULT_PERKS[key]
        plans.append({
            "key": key,
            "name": str(data.get("name") or "").strip() or PLAN_NAMES[key],
            "price": num(data.get("price")),
            "old": num(data.get("oldPrice")),
            "days": int(num(data.get("days"))),
            "perks": [p.strip() for p in re.split(r"\n|\|", perks_raw) if p.strip()][:8],
        })
    return plans


# ============================================================
# 6) MATNLAR
# ============================================================
def svc_icon(s):
    x = (s["title"] + " " + s["cat"]).lower()
    if re.search(r"bot", x):
        return "🤖"
    if re.search(r"sayt|web|veb|site", x):
        return "🌐"
    if re.search(r"app|ilova", x):
        return "📱"
    if re.search(r"host|server|domen", x):
        return "☁️"
    if re.search(r"dizayn|design|logo", x):
        return "🎨"
    return "💼"


def has_app():
    return MINI_APP_URL.startswith("https://")


def banner():
    ok, s = get_settings()
    if not ok:
        return ""
    parts = []
    if s.get("maintenance") is True:
        text = str(s.get("maintenanceText") or "").strip() or "Texnik ishlar olib borilmoqda."
        parts.append("🛠 " + escape(short(text, 300)))
    note = str(s.get("announcement") or "").strip()
    if note:
        parts.append("📢 " + escape(short(note, 400)))
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def welcome_text(name):
    return (
        f"Assalomu alaykum, <b>{escape(name or 'do‘st')}</b>! 👋\n\n"
        f"<b>{escape(app_name())}</b> rasmiy botiga xush kelibsiz.\n\n"
        "Bu yerda xizmatlarimiz bilan tanishishingiz, buyurtma berishingiz, "
        "Premium va donat haqida bilib olishingiz mumkin.\n\n"
        "Kerakli bo'limni tanlang 👇" + banner()
    )


def services_text(items):
    if not items:
        return "🛠 <b>Xizmatlar</b>\n\nHozircha xizmatlar mavjud emas. Keyinroq qayta ko'ring."
    return "🛠 <b>Xizmatlar</b>\n\nKerakli xizmatni tanlang — batafsil ma'lumot va buyurtma shu yerda 👇"


def service_text(s):
    lines = [f"{svc_icon(s)} <b>{escape(s['title'])}</b>"]
    if s["desc"]:
        lines.append("\n" + escape(s["desc"]))
    lines.append("")
    lines.append("💰 Narx: " + (f"{money(s['price'])} so'm dan" if s["price"] > 0 else "kelishiladi"))
    if s["days"]:
        lines.append("⏱ Muddat: " + escape(s["days"]))
    if s["cat"]:
        lines.append("🏷 Toifa: " + escape(s["cat"]))
    return "\n".join(lines)


def premium_text():
    ok, s = get_settings()
    plans = get_plans(s)
    if not plans:
        return "💎 <b>Premium</b>\n\nHozircha Premium obunalar mavjud emas."
    out = ["💎 <b>Premium obuna</b>\n"]
    for p in plans:
        out.append(f"<b>{escape(p['name'])}</b>")
        if ok:
            price = f"💰 {money(p['price'])} so'm"
            if p["old"] > p["price"] > 0:
                price = f"💰 <s>{money(p['old'])}</s> {money(p['price'])} so'm"
            price += f" · {p['days']} kun" if p["days"] > 0 else " · muddatsiz"
            out.append(price)
        out.extend("✅ " + escape(x) for x in p["perks"])
        out.append("")
    if not ok:
        out.append("ℹ️ Joriy narxlarni " + ("ilovada ko'ring." if has_app() else "«📞 Aloqa» orqali so'rang."))
        out.append("")
    if has_app():
        out.append("To'lovni amalga oshirgach, chekni ilovada yuboring — administrator tasdiqlagach obuna yoqiladi.")
    else:
        out.append("Obuna olish uchun «📞 Aloqa» orqali yozing.")
    return "\n".join(out).strip()


def donate_text():
    ok, s = get_settings()
    out = ["❤️ <b>Loyihani qo'llab-quvvatlang</b>\n", "Har bir hissa loyihani balandroq uchiradi.\n"]
    if not ok:
        out.append("Donat qilish va joriy ma'lumotlar uchun " + ("ilovani oching." if has_app() else "«📞 Aloqa» orqali yozing."))
        return "\n".join(out)
    goal, raised = num(s.get("goal")), num(s.get("raised"))
    if goal > 0:
        pct = int(max(0, min(100, raised / goal * 100)))
        filled = pct // 10
        out.append(f"🎯 Maqsad: {money(goal)} so'm")
        out.append(f"📈 Yig'ildi: {money(raised)} so'm ({pct}%)")
        out.append("█" * filled + "░" * (10 - filled) + "\n")
    amounts = [int(n) for n in re.split(r"[,\s]+", str(s.get("amounts") or "")) if n.isdigit() and 1000 <= int(n) <= 100000000]
    if amounts:
        out.append("Tavsiya etilgan summalar: " + " • ".join(money(a) for a in amounts[:6]) + " so'm\n")
    card = s.get("card") if isinstance(s.get("card"), dict) else {}
    number = str(card.get("number") or "").strip()
    if number:
        out.append("💳 <b>Karta</b>")
        if str(card.get("name") or "").strip():
            out.append(escape(card["name"]))
        out.append(f"<code>{escape(number)}</code>")
        if str(card.get("holder") or "").strip():
            out.append(escape(card["holder"]))
        out.append("")
        out.append("Kartaga o'tkazma qilgach, " + ("ilovada «To'lov qildim» tugmasini bosing" if has_app() else "«📞 Aloqa» orqali xabar bering")
                   + ". Administrator to'lovni tekshirib tasdiqlaydi.")
    else:
        out.append("Hozircha to'lov kartasi ko'rsatilmagan.")
    return "\n".join(out).strip()


def about_text():
    text = (
        f"ℹ️ <b>{escape(app_name())} haqida</b>\n\n"
        "Telegram ichida ishlaydigan qulay mini ilova. Unda:\n\n"
        "🛠 <b>Xizmatlar</b> — xizmatlarni ko'rish va buyurtma berish\n"
        "📰 <b>Lenta</b> — qisqa videolar (Reels)\n"
        "👥 <b>Odamlar</b> — foydalanuvchilar bilan tanishish va xabarlashish\n"
        "❤️ <b>Donat</b> — loyihani qo'llab-quvvatlash\n"
        "👤 <b>Kabinet</b> — profil, Premium, do'kon va xabarlar\n"
    )
    if has_app():
        text += "\nHammasi bitta joyda — «📱 Ilovani ochish» tugmasi orqali."
    return text


HELP_TEXT = (
    "❓ <b>Yordam</b>\n\n"
    "/start — bosh menyu\n"
    "/help — shu yo'riqnoma\n\n"
    "• Buyurtma: «🛠 Xizmatlar» → xizmatni tanlang → «🛒 Buyurtma berish»\n"
    "• Premium va donat — tegishli bo'limlarda\n"
    "• Savol yoki taklif: «📞 Aloqa» — javob shu bot ichida keladi"
)

CONTACT_TEXT = (
    "📞 <b>Aloqa</b>\n\n"
    "Savol, taklif yoki shikoyatingizni yozing — xabaringiz administratorga yetkaziladi, "
    "javob shu bot ichida keladi.\n\n"
    "✍️ Xabaringizni hozir yozib yuboring:"
)


# ============================================================
# 7) TUGMALAR
# ============================================================
def btn(text, data):
    return types.InlineKeyboardButton(text, callback_data=data)


def app_button(text="📱 Ilovani ochish"):
    if has_app():
        return types.InlineKeyboardButton(text, web_app=types.WebAppInfo(url=MINI_APP_URL))
    return None


def main_menu():
    kb = types.InlineKeyboardMarkup()
    ab = app_button()
    if ab:
        kb.row(ab)
    kb.row(btn("🛠 Xizmatlar", "services"), btn("💎 Premium", "premium"))
    kb.row(btn("❤️ Donat", "donate"), btn("📞 Aloqa", "contact"))
    kb.row(btn("ℹ️ Ilova haqida", "about"), btn("❓ Yordam", "help"))
    if BOT_USERNAME:
        share = (
            "https://t.me/share/url?url="
            + urllib.parse.quote(f"https://t.me/{BOT_USERNAME}", safe="")
            + "&text="
            + urllib.parse.quote(f"{app_name()} — rasmiy bot", safe="")
        )
        kb.row(types.InlineKeyboardButton("🔗 Do'stlarga ulashish", url=share))
    return kb


def back_menu(target="menu", label="⬅️ Orqaga", with_app=None):
    kb = types.InlineKeyboardMarkup()
    if with_app:
        ab = app_button(with_app)
        if ab:
            kb.row(ab)
    kb.row(btn(label, target))
    return kb


def services_menu(items):
    kb = types.InlineKeyboardMarkup()
    row = []
    for i, s in enumerate(items):
        row.append(btn(f"{svc_icon(s)} {short(s['title'], 26)}", f"svc:{i}"))
        if len(row) == 2:
            kb.row(*row)
            row = []
    if row:
        kb.row(*row)
    kb.row(btn("⬅️ Orqaga", "menu"))
    return kb


def service_menu(i, s):
    kb = types.InlineKeyboardMarkup()
    if s["url"]:
        kb.row(types.InlineKeyboardButton("🔗 Batafsil", url=s["url"]))
    else:
        kb.row(btn("🛒 Buyurtma berish", f"order:{i}"))
    ab = app_button("📱 Ilovada ko'rish")
    if ab:
        kb.row(ab)
    kb.row(btn("⬅️ Xizmatlar", "services"))
    return kb


def premium_menu():
    kb = types.InlineKeyboardMarkup()
    ab = app_button("💎 Obuna olish")
    if ab:
        kb.row(ab)
    kb.row(btn("📞 Savol berish", "contact"))
    kb.row(btn("⬅️ Orqaga", "menu"))
    return kb


def cancel_menu():
    kb = types.InlineKeyboardMarkup()
    kb.row(btn("❌ Bekor qilish", "menu"))
    return kb


def show(call, text, markup):
    """Tugma bosilganda xabarni joyida yangilaydi."""
    chat_id = call.message.chat.id
    try:
        bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            return
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)


def safe(fn):
    """Xato chiqsa ham bot to'xtamasin: xatoni yozib qo'yadi va foydalanuvchiga xabar beradi."""
    @functools.wraps(fn)
    def wrapper(obj):
        try:
            return fn(obj)
        except Exception:
            traceback.print_exc()
            try:
                msg = getattr(obj, "message", None)
                chat_id = msg.chat.id if msg is not None else obj.chat.id
                bot.send_message(chat_id, "⚠️ Kutilmagan xatolik yuz berdi. Iltimos, /start ni bosib qayta urinib ko'ring.")
            except Exception:
                pass
    return wrapper


# ============================================================
# 8) FILTRLAR
# ============================================================
def is_private(m):
    return m.chat.type == "private"


def is_admin(m):
    return m.chat.type == "private" and ADMIN_ID != 0 and m.from_user.id == ADMIN_ID


def is_waiting(m):
    return m.chat.type == "private" and m.from_user.id in waiting


def is_admin_reply(m):
    return is_admin(m) and m.reply_to_message is not None


# ============================================================
# 9) BUYRUQLAR  (tartib muhim: buyruqlar birinchi turishi kerak)
# ============================================================
@bot.message_handler(commands=["start"], func=is_private)
@safe
def cmd_start(m):
    waiting.pop(m.from_user.id, None)
    add_user(m.from_user.id)
    bot.send_message(m.chat.id, welcome_text(m.from_user.first_name), parse_mode="HTML", reply_markup=main_menu())


@bot.message_handler(commands=["help"], func=is_private)
@safe
def cmd_help(m):
    waiting.pop(m.from_user.id, None)
    add_user(m.from_user.id)
    bot.send_message(m.chat.id, HELP_TEXT, parse_mode="HTML", reply_markup=back_menu())


@bot.message_handler(commands=["stats"], func=is_admin)
@safe
def cmd_stats(m):
    with lock:
        count = len(users)
    bot.reply_to(m, f"👥 Foydalanuvchilar soni: {count}")


@bot.message_handler(commands=["status"], func=is_admin)
@safe
def cmd_status(m):
    with lock:
        count = len(users)
    ok, _ = live("settings", ttl=0) if LIVE_DATA else (False, None)
    text = (
        "📊 <b>Bot holati</b>\n\n"
        f"👥 Foydalanuvchilar: {count}\n"
        f"🌐 Ilova ma'lumotlari: {'ulangan ✅' if ok else ('o‘chirilgan' if not LIVE_DATA else 'ulanmagan ⚠️')}\n"
        f"🔔 Bildirishnomalar: {escape(notifier_status)}\n"
        f"📱 Mini app tugmasi: {'yoqilgan ✅' if has_app() else 'MINI_APP_URL yozilmagan'}"
    )
    bot.reply_to(m, text, parse_mode="HTML")


def run_broadcast(text, admin_chat):
    ok = 0
    fail = 0
    with lock:
        ids = list(users)
    for uid in ids:
        try:
            bot.send_message(uid, text)
            ok += 1
        except ApiTelegramException as e:
            if e.error_code == 429:  # juda tez — biroz kutib, qayta urinamiz
                time.sleep(5)
                try:
                    bot.send_message(uid, text)
                    ok += 1
                except Exception:
                    fail += 1
            else:
                fail += 1
                if e.error_code == 403:  # foydalanuvchi botni bloklagan
                    remove_user(uid)
        except Exception:
            fail += 1
        time.sleep(0.05)
    try:
        bot.send_message(admin_chat, f"📣 Tarqatish tugadi.\n✅ Yetkazildi: {ok}\n❌ Yetkazilmadi: {fail}")
    except Exception:
        pass


@bot.message_handler(commands=["broadcast"], func=is_admin)
@safe
def cmd_broadcast(m):
    text = m.text.partition(" ")[2].strip()
    if not text:
        bot.reply_to(m, "Foydalanish: /broadcast Xabar matni")
        return
    bot.reply_to(m, "⏳ Tarqatish boshlandi...")
    threading.Thread(target=run_broadcast, args=(text, m.chat.id), daemon=True).start()


# ============================================================
# 10) ADMIN JAVOBI: xabar/bildirishnomaga reply qilsangiz, foydalanuvchiga yetadi
# ============================================================
@bot.message_handler(func=is_admin_reply, content_types=["text"])
@safe
def admin_reply(m):
    source = m.reply_to_message.text or m.reply_to_message.caption or ""
    found = re.search(r"^🆔 ID: (\d+)\s*$", source, re.M)
    if not found:
        bot.reply_to(m, "ℹ️ Javob berish uchun foydalanuvchi xabari yoki buyurtma bildirishnomasiga reply qiling.")
        return
    uid = int(found.group(1))
    try:
        bot.send_message(uid, "💬 <b>Administrator javobi:</b>\n\n" + escape(m.text), parse_mode="HTML")
        bot.reply_to(m, "✅ Javob yuborildi.")
    except ApiTelegramException:
        bot.reply_to(m, "❌ Yuborib bo'lmadi (foydalanuvchi botni bloklagan yoki hali ishga tushirmagan).")


# ============================================================
# 11) «ALOQA» VA «BUYURTMA»: foydalanuvchi xabarini adminga yetkazish
# ============================================================
@bot.message_handler(func=is_waiting, content_types=["text"])
@safe
def contact_text(m):
    user = m.from_user
    text = m.text.strip()
    if len(text) > 2000:
        bot.reply_to(m, "Xabar juda uzun. Iltimos, 2000 belgidan qisqaroq yozing.")
        return
    wait = int(15 - (time.time() - last_sent.get(user.id, 0)))
    if wait > 0:
        bot.reply_to(m, f"⏳ Iltimos, {wait} soniyadan so'ng yana yuboring.")
        return
    state = waiting.get(user.id, {"kind": "contact"})
    username = "@" + escape(user.username) if user.username else "yo'q"
    if state.get("kind") == "order":
        head = f"🛒 <b>Yangi buyurtma (bot orqali)</b>\n🛠 Xizmat: {escape(state.get('service', ''))}\n"
        done = "✅ Buyurtmangiz administratorga yuborildi. Tez orada siz bilan bog'lanamiz."
    else:
        head = "📩 <b>Yangi xabar</b>\n"
        done = "✅ Xabaringiz administratorga yuborildi. Javobni shu yerda olasiz."
    note = (
        head
        + f"🆔 ID: <code>{user.id}</code>\n"
        + f"👤 Ism: {escape(full_name(user))}\n"
        + f"🔗 Username: {username}\n\n"
        + f"{escape(text)}\n\n"
        + "<i>Javob berish uchun shu xabarga reply qiling.</i>"
    )
    try:
        bot.send_message(ADMIN_ID, note, parse_mode="HTML")
    except ApiTelegramException as e:
        print("Adminga yuborib bo'lmadi:", e)
        bot.send_message(m.chat.id, "😔 Xabarni hozir yuborib bo'lmadi. Keyinroq urinib ko'ring.", reply_markup=back_menu())
        return
    last_sent[user.id] = time.time()
    waiting.pop(user.id, None)
    bot.send_message(m.chat.id, done, reply_markup=main_menu())


@bot.message_handler(
    func=is_waiting,
    content_types=["photo", "video", "document", "voice", "audio", "sticker", "video_note", "animation", "contact", "location"],
)
@safe
def contact_other(m):
    bot.reply_to(m, "Iltimos, xabaringizni faqat matn ko'rinishida yozing ✍️", reply_markup=cancel_menu())


# ============================================================
# 12) TUGMALAR (inline)
# ============================================================
@bot.callback_query_handler(func=lambda c: True)
@safe
def on_button(call):
    try:
        bot.answer_callback_query(call.id)
    except ApiTelegramException:
        pass
    if call.message is None:
        return

    uid = call.from_user.id
    data = call.data or ""
    add_user(uid)
    if data != "contact":
        waiting.pop(uid, None)

    if data == "menu":
        show(call, welcome_text(call.from_user.first_name), main_menu())
    elif data == "services":
        items = get_services()
        show(call, services_text(items), services_menu(items))
    elif data.startswith("svc:") or data.startswith("order:"):
        kind, _, raw = data.partition(":")
        items = get_services()
        if not raw.isdigit() or int(raw) >= len(items):
            show(call, services_text(items), services_menu(items))
            return
        i = int(raw)
        s = items[i]
        if kind == "svc":
            show(call, service_text(s), service_menu(i, s))
        else:
            if ADMIN_ID == 0:
                show(call, "🛒 Buyurtma qabul qilish hozircha yoqilmagan.", back_menu("services", "⬅️ Xizmatlar", "📱 Ilovada buyurtma berish"))
                return
            waiting[uid] = {"kind": "order", "service": s["title"]}
            show(
                call,
                f"🛒 <b>{escape(s['title'])}</b>\n\n"
                "Buyurtma tafsilotlarini yozing: nima kerak, qanday muddatda, qo'shimcha istaklar. "
                "Xabaringiz administratorga yetkaziladi va u siz bilan bog'lanadi.\n\n"
                "✍️ Hozir yozib yuboring:",
                cancel_menu(),
            )
    elif data == "premium":
        show(call, premium_text(), premium_menu())
    elif data == "donate":
        show(call, donate_text(), back_menu(with_app="❤️ Ilovada donat qilish"))
    elif data == "about":
        show(call, about_text(), back_menu())
    elif data == "help":
        show(call, HELP_TEXT, back_menu())
    elif data == "contact":
        if ADMIN_ID == 0:
            show(call, "📞 <b>Aloqa</b>\n\nHozircha bu bo'lim mavjud emas.", back_menu())
        else:
            waiting[uid] = {"kind": "contact"}
            show(call, CONTACT_TEXT, cancel_menu())


# ============================================================
# 13) BOSHQA HAR QANDAY MATN
# ============================================================
@bot.message_handler(func=is_private, content_types=["text"])
@safe
def fallback(m):
    add_user(m.from_user.id)
    bot.send_message(m.chat.id, "Quyidagi menyudan tanlang 👇", reply_markup=main_menu())


# ============================================================
# 14) ADMIN BILDIRISHNOMALARI: ilovadagi yangi buyurtma va so'rovlar
# ============================================================
SEEN_FILE = os.path.join(BASE_DIR, "seen.json")
WATCH = ["orders", "premium_requests", "shop_orders", "donations"]
notifier_status = "o'chirilgan"


def _tid(item):
    tid = str(item.get("telegramId") or "").strip()
    return f"🆔 ID: <code>{tid}</code>\n" if re.fullmatch(r"\d{1,15}", tid) else ""


def _who(item):
    name = str(item.get("name") or "").strip() or "Noma'lum"
    uname = str(item.get("username") or "").strip().lstrip("@")
    return f"👤 {escape(short(name, 60))}" + (f" (@{escape(short(uname, 40))})" if uname else "") + "\n"


def _when(item):
    t = fmt_time(item.get("ts"))
    return f"🕒 {t}\n" if t else ""


def format_item(path, it):
    # Diqqat: «🆔 ID» qatori foydalanuvchi yozgan matnlardan OLDIN turishi shart (reply xavfsizligi uchun).
    if path == "orders":
        text = "🛒 <b>Yangi buyurtma (ilova)</b>\n" + _tid(it)
        text += f"🛠 Xizmat: {escape(short(it.get('service') or '—', 120))}\n" + _who(it)
        if str(it.get("phone") or "").strip():
            text += f"📞 Telefon: {escape(short(it['phone'], 30))}\n"
        if num(it.get("price")) > 0:
            text += f"💰 Narx: {money(it['price'])} so'm dan\n"
        text += _when(it)
        if str(it.get("note") or "").strip():
            text += f"\n📝 {escape(short(it['note'], 600))}\n"
        return text.strip()
    if path == "premium_requests":
        plan = PLAN_NAMES.get(str(it.get("plan")), "Premium")
        text = "💎 <b>Premium so'rovi</b>\n" + _tid(it) + _who(it)
        text += f"📦 Tarif: {escape(plan)}\n💰 Summa: {money(it.get('amount'))} so'm\n"
        if num(it.get("days")) > 0:
            text += f"⏱ Muddat: {int(num(it['days']))} kun\n"
        text += _when(it) + "\n✅ Tasdiqlash — ilovadagi admin panelda."
        return text
    if path == "shop_orders":
        text = "🛍 <b>Do'kon buyurtmasi</b>\n" + _tid(it) + _who(it)
        text += f"🧾 Mahsulot: {escape(short(it.get('title') or '—', 120))}\n"
        if num(it.get("price")) > 0:
            text += f"💰 Narx: {money(it['price'])} so'm\n"
        text += _when(it) + "\n✅ Tasdiqlash — ilovadagi admin panelda."
        return text
    text = "❤️ <b>Yangi donat</b>\n" + _tid(it) + _who(it)
    text += f"💰 Summa: {money(it.get('amount'))} so'm\n"
    if str(it.get("card") or "").strip():
        text += f"💳 Karta: {escape(short(it['card'], 40))}\n"
    if it.get("anon") is True:
        text += "🕶 Homiylar devorida anonim ko'rinadi\n"
    text += _when(it) + "\n✅ Tasdiqlash — ilovadagi admin panelda."
    return text


def send_notification(path, it):
    text = format_item(path, it)
    receipt = it.get("receipt")
    if isinstance(receipt, str):
        found = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", receipt, re.S)
        if found:
            try:
                photo = io.BytesIO(base64.b64decode(found.group(1)))
                photo.name = "receipt.jpg"
                if len(text) <= 1000:
                    bot.send_photo(ADMIN_ID, photo, caption=text, parse_mode="HTML")
                    return
                bot.send_photo(ADMIN_ID, photo)
            except Exception as e:
                print("Chek rasmini yuborib bo'lmadi:", e)
    bot.send_message(ADMIN_ID, text, parse_mode="HTML")


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, ValueError, TypeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {p: set(str(x) for x in raw[p]) for p in WATCH if isinstance(raw.get(p), list)}


def save_seen(seen):
    tmp = SEEN_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({p: sorted(v) for p, v in seen.items()}, f)
        os.replace(tmp, SEEN_FILE)
    except OSError as e:
        print("seen.json ga yozib bo'lmadi:", e)


def notifier_loop():
    global notifier_status
    seen = load_seen()  # bo'limi yo'q bo'lsa: birinchi o'qishda eski yozuvlar haqida xabar bermaymiz
    warned = False
    while True:
        denied = []
        failed = False
        for path in WATCH:
            try:
                raw = fb_get(path, {"shallow": "true"})
                keys = sorted(raw) if isinstance(raw, dict) else []
                if path not in seen:
                    seen[path] = set(keys)
                    save_seen(seen)
                    continue
                new = [k for k in keys if k not in seen[path]][:20]
                for key in new:
                    item = fb_get(f"{path}/{key}")
                    if isinstance(item, dict):
                        try:
                            send_notification(path, item)
                        except ApiTelegramException as e:
                            print("Bildirishnomani yuborib bo'lmadi:", e)
                            if e.error_code == 429:
                                time.sleep(5)
                                break  # keyingi aylanishda qayta uriniladi
                    seen[path].add(key)
                if new:
                    save_seen(seen)
            except FbError as e:
                if e.code in (401, 403):
                    denied.append(path)
                else:
                    failed = True
            except Exception:
                traceback.print_exc()
                failed = True
        delay = POLL_SECONDS
        if len(denied) == len(WATCH):
            notifier_status = "ruxsat yo'q ⚠️"
            delay = 600
        elif denied:
            notifier_status = "qisman ishlayapti (ruxsat yo'q: " + ", ".join(denied) + ")"
        elif failed:
            notifier_status = "aloqa xatosi, qayta uriniladi"
            delay = POLL_SECONDS * 2
        else:
            notifier_status = "ishlayapti ✅"
        if denied and not warned:
            warned = True
            try:
                bot.send_message(
                    ADMIN_ID,
                    "⚠️ Bot ilovadagi buyurtmalarni o'qiy olmayapti (Firebase ruxsat bermayapti: "
                    + ", ".join(denied) + ").\nBildirishnomalar shu bo'limlar uchun ishlamaydi. "
                    "Bot va uning boshqa imkoniyatlari ishlayveradi.",
                )
            except Exception:
                pass
        time.sleep(delay)


# ============================================================
# 15) ISHGA TUSHIRISH
# ============================================================
def main():
    global BOT_USERNAME, notifier_status
    try:
        me = bot.get_me()
    except Exception as e:
        print("❌ Botga ulanib bo'lmadi. Token noto'g'ri yoki internet yo'q:", e)
        sys.exit(1)
    BOT_USERNAME = me.username or ""

    try:
        bot.remove_webhook()
    except Exception:
        pass

    try:
        common = [types.BotCommand("start", "Bosh menyu"), types.BotCommand("help", "Yordam")]
        bot.set_my_commands(common)
        if ADMIN_ID:
            bot.set_my_commands(
                common + [
                    types.BotCommand("stats", "Foydalanuvchilar soni"),
                    types.BotCommand("status", "Bot holati"),
                    types.BotCommand("broadcast", "Hammaga xabar yuborish"),
                ],
                scope=types.BotCommandScopeChat(ADMIN_ID),
            )
    except Exception as e:
        print("Buyruqlar ro'yxatini o'rnatib bo'lmadi (muhim emas):", e)

    if has_app():
        try:
            bot.set_chat_menu_button(
                menu_button=types.MenuButtonWebApp(text="Ilova", web_app=types.WebAppInfo(url=MINI_APP_URL))
            )
        except Exception as e:
            print("Menyu tugmasini o'rnatib bo'lmadi (muhim emas):", e)
    else:
        print("ℹ️ MINI_APP_URL yozilmagan — «Ilovani ochish» tugmasi chiqmaydi.")

    if ADMIN_ID == 0:
        print("⚠️ ADMIN_ID yozilmagan — «Aloqa», buyurtma va admin buyruqlari ishlamaydi.")
    else:
        try:
            bot.send_message(ADMIN_ID, "✅ Bot ishga tushdi.\nHolatni ko'rish: /status")
        except Exception:
            print("⚠️ Adminga xabar yuborib bo'lmadi. Admin hisobidan botga /start bosing.")
        if NOTIFY_ADMIN and LIVE_DATA:
            notifier_status = "ishga tushmoqda..."
            threading.Thread(target=notifier_loop, daemon=True).start()

    print(f"✅ Bot ishga tushdi: @{BOT_USERNAME}")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
