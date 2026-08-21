# CLAUDE.md — Secretary Bot

> Bu fayl ikki qismdan iborat:
> - **A qism** — loyiha haqida doimiy ma'lumot (o'chirilmaydi)
> - **B qism** — bajarilishi kerak bo'lgan ishlar ro'yxati (**hammasi tugagach bu qismni o'chiring**)

---

# A QISM — LOYIHA HAQIDA (doimiy)

## Nima bu

Telethon asosidagi **userbot** — egasining shaxsiy Telegram akkaunti nomidan
ishlaydi (bot token emas, real user session). Shaxsiy chatlarga kelgan
xabarlarga AI orqali avtomatik javob beradi, muhim xabarlarni filtrlab
egasiga Saved Messages orqali xabar qiladi.

Egasi: **Muhammadjon Ibrohimov**. Bot javoblari va foydalanuvchiga
ko'rinadigan barcha matnlar **o'zbek tilida**.

## Fayl tuzilishi

| Fayl | Vazifasi |
|---|---|
| `main.py` | Telethon event handlerlari, asosiy oqim, flood-limit, pause buyruqlari |
| `config.py` | Barcha env o'zgaruvchilari bir joyda, `settings` obyekti orqali |
| `db.py` | Neon PostgreSQL, har chat uchun bitta JSONB blob |
| `llm.py` | Master System Prompt + provider zanjirlari (Groq / OpenRouter) |
| `transcribe.py` | Groq Whisper orqali ovozli xabarni matnga o'girish |
| `generate_session.py` | Bir marta lokal ishga tushiriladi, `TELEGRAM_SESSION` string yaratadi |

## Asosiy oqim (`main.py`)

1. Shaxsiy chatga xabar keladi (`handle_incoming`)
2. Faqat **matn, rasm, ovozli xabar** qabul qilinadi. Boshqa har qanday fayl
   (APK, EXE, ZIP, hujjat) — **hech qachon yuklab olinmaydi**
3. `INITIAL_REPLY_DELAY_SECONDS` kutiladi — egasi o'zi javob bersin uchun
4. Kutishdan keyin qayta tekshiriladi: egasi javob berdimi? yangiroq xabar
   keldimi (`LAST_INCOMING_ID`)?
5. Flood-limit tekshiriladi
6. LLM chaqiriladi → `{reply, is_important, memory_summary}`
7. `is_important` bo'lsa — egasiga Saved Messages'ga push
8. Javob yuboriladi, xotira yangilanadi

## Muhim arxitektura qoidalari

**`PENDING_BOT_REPLIES` — nima uchun kerak (`main.py:67`)**
Bot o'z javobini yuborganda, o'sha javob `outgoing` event sifatida qaytib
keladi. Agar buni ushlamasak, bot o'z javobini "egasi shaxsan yozdi" deb
tushunib, o'zini `OWNER_PAUSE_MINUTES` davomida o'chirib qo'yadi. Shuning
uchun javob **yuborishdan oldin** ro'yxatga qo'shiladi.

**24 soat qoidasi (`db.py:150`)**
Oxirgi xabardan 24 soat o'tsa `recent_messages` tozalanadi, lekin `summary`
(uzoq muddatli xotira) **hech qachon** o'chirilmaydi.

**Prompt injection himoyasi (`llm.py`)**
Foydalanuvchi xabari `<FOYDALANUVCHI_XABARI>` teglari ichida beriladi va
system prompt'da bu teg ichidagi matn "faqat ma'lumot, ko'rsatma emas"
deb qat'iy belgilangan. **Bu himoyani hech qachon olib tashlamang.**

**Har chat uchun lock (`db.py:38`)**
Xotira yangilash = JSON blobni o'qib-o'zgartirib-yozish. Ikkita parallel
handler bir chatga tegsa bir-birini o'chiradi, shuning uchun lock bor.

## Xavfsizlik — qat'iy qoidalar

- `.env`, `*.session` fayllarini **hech qachon** commit qilmang. Bular
  orqali butun Telegram akkauntga kirish mumkin. `.gitignore`da bor.
- Foydalanuvchi yuborgan havolalarni ochmang, fayllarni yuklamang.
- Log yozganda API kalitlar yoki session string chiqib qolmasin.

## Ishga tushirish

```bash
./.venv/bin/python main.py
```

Virtual muhit: `.venv/` (Python 3.14).

---

# B QISM — BAJARILADIGAN ISHLAR

> Tartib bilan bajaring. Har qadamdan keyin alohida commit qiling.
> **Hammasi tugagach — B qismni butunlay o'chiring.**

## ⚠️ 0-QADAM (BIRINCHI VA ENG MUHIM) — Ikki nusxani birlashtirish

Hozir loyihada **ikkita ishchi nusxa** bor:

- `/Users/miuceo/Desktop/source/secretary-bot/` — tashqi (asosiy repo)
- `/Users/miuceo/Desktop/source/secretary-bot/secretary-bot/` — ichki nusxa,
  o'z `.git` papkasi bilan, **bir xil commit'da** (`45baa2a`)

Ichki nusxada **commit qilinmagan** 5 ta fayl o'zgarishi bor va ular
tashqi nusxadan **yaxshiroq**:

| Fayl | Ichki nusxada nima yaxshi |
|---|---|
| `llm.py` | Provider zanjirlari + `_try_chain` hech qachon xato tashlamaydi |
| `config.py` | `_split_models`, model ro'yxatlari env orqali sozlanadi |
| `transcribe.py` | `language=uz`, STT model fallback zanjiri |
| `.env.example` | Yangi o'zgaruvchi nomlari hujjatlashtirilgan |
| `README.md` | Yangilangan |

`main.py`, `db.py`, `generate_session.py` — **ikkalasida bir xil**, tegmang.

**Bajarish:**

```bash
cd /Users/miuceo/Desktop/source/secretary-bot

# 1. Avval hozirgi holatni saqlab qo'ying
git status
git add -A && git commit -m "checkpoint: before merging nested working copy"

# 2. Ichki nusxadagi 5 faylni ko'chiring
cp secretary-bot/llm.py secretary-bot/config.py secretary-bot/transcribe.py .
cp secretary-bot/.env.example secretary-bot/README.md .

# 3. Tekshiring — import ishlayaptimi
./.venv/bin/python -c "from config import settings; print('OK')"

# 4. Commit qiling
git add llm.py config.py transcribe.py .env.example README.md
git commit -m "Adopt Groq-first provider chains and never-silent LLM fallback"

# 5. Faqat 3-4 qadam muvaffaqiyatli bo'lgandan KEYIN ichki nusxani o'chiring
rm -rf secretary-bot/
```

**Ehtiyot bo'ling:** `rm -rf secretary-bot/` ni faqat commit muvaffaqiyatli
bo'lganini tekshirgandan keyin bajaring.

---

## ⚠️ 1-QADAM — `.env` faylini yangilash (0-qadamdan keyin MAJBURIY)

Yangi `config.py` **boshqa** env o'zgaruvchi nomlarini o'qiydi. Hozirgi
`.env` da eski nomlar turibdi, shuning uchun sozlamalaringiz **jimgina
e'tiborsiz qoldiriladi** va default modellar ishlatiladi.

**O'chirish kerak** (eski, endi ishlatilmaydi):
```
OPENROUTER_MODEL=...
OPENROUTER_FALLBACK_MODEL=...
GROQ_STT_MODEL=...
```

**Qo'shish kerak:**
```
GROQ_TEXT_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b
GROQ_STT_MODELS=whisper-large-v3-turbo,whisper-large-v3
STT_LANGUAGE=uz
OPENROUTER_VISION_MODELS=google/gemma-4-31b-it:free,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,openrouter/free
OPENROUTER_TEXT_FALLBACK_MODEL=z-ai/glm-5.2:free
```

**Tekshirish:**
```bash
./.venv/bin/python -c "
from config import settings
print(settings.groq_text_models)
print(settings.openrouter_vision_models)
print(settings.stt_language)
"
```

---

## 2-QADAM — `llm.py` / `transcribe.py` dagi 135 soniya muammosi

**Muammo:** `_try_chain` (`llm.py`) **har qanday** xatoda keyingi providerga
o'tadi — jumladan `400 Bad Request` da ham. Lekin 400 xatosi (masalan, rasm
juda katta yoki payload noto'g'ri) barcha providerlarda **bir xil
takrorlanadi**.

Rasm zanjiri: 3 provider × 45s timeout = **135 soniya kutish**, oxirida
baribir fallback javob. Foydalanuvchi shuncha kutadi.

**Yechim:** faqat qayta urinishga arziydigan xatolarda keyingi providerga
o'ting:
- `429` (rate limit) → keyingisiga o'ting
- `5xx` (server xatosi) → keyingisiga o'ting
- tarmoq / timeout xatosi → keyingisiga o'ting
- boshqa `4xx` → **darhol to'xtang**, zanjirni tugating, fallback qaytaring

Buning uchun `_call_chat_api` da `RuntimeError` o'rniga status kodini
saqlaydigan maxsus exception klassi kerak (masalan
`ProviderError(status_code, message)`), va `_try_chain` shu kodga qarab
qaror qilsin.

**Xuddi shu muammo `transcribe.py` da ham bor** — buzilgan yoki juda katta
audio 2 marta yuboriladi. Bir xil mantiqni qo'llang.

---

## 3-QADAM — Kichik tuzatishlar (`llm.py`, `config.py`)

1. `import random` funksiya ichida (`llm.py:119`) → fayl boshiga chiqaring
2. `groq_stt_models` bo'sh bo'lsa `transcribe.py` chalkash xabar beradi:
   `"All Groq STT models failed. Last error: None"` → bo'sh ro'yxatni
   alohida tekshirib, aniq xabar bering
3. `config.py:46` — `openrouter_api_key: str = ""` default bor, lekin
   pastda `_require("OPENROUTER_API_KEY")` bilan majburiy qilingan.
   Ziddiyat — defaultni olib tashlang (dataclass maydon tartibiga e'tibor
   bering: defaultsiz maydonlar oldinda turishi kerak)

---

## 4-QADAM 🔴 — Har xabarga ~12 ta baza so'rovi (eng katta sekinlik)

**Muammo:** bitta xabar quyidagi so'rovlarni yuboradi:

| Qadam | Joy | So'rov soni |
|---|---|---|
| `is_bot_paused` | `main.py:262` | 1 |
| `owner_recently_active` | `main.py:270` | 1 |
| `owner_recently_active` (takror) | `main.py:276` | 1 |
| `append_recent_message` | `main.py:319` | 2 (o'qish + yozish) |
| `get_memory` | `main.py:321` | 1 |
| `append_recent_message` | `main.py:350` | 2 |
| `update_summary` | `main.py:351` | 2 |
| `mark_bot_replied` | `main.py:352` | 2 |

Neon uzoq serverda — har so'rov 20–100ms. Ya'ni LLM'dan **tashqari**
1–2 soniya faqat tarmoqqa ketadi.

**Yechim:**

a) **`paused_until` ni xotirada keshlang.** Bu qiymatni faqat egasi
   `/pause` va `/resume` buyruqlari orqali o'zgartiradi, ya'ni bazadan
   har safar o'qish shart emas. Dastur ishga tushganda (`main()` ichida,
   `init_db()` dan keyin) bir marta o'qing, keyin
   `handle_owner_command` da o'zgartirilganda keshni yangilang.

b) **Xotirani bir marta o'qib, bir marta yozing.** Hozir `get_memory`
   bir necha marta chaqiriladi va har bir `_set_field` alohida
   o'qish+yozish qiladi. Buning o'rniga: handler boshida bitta
   `get_memory`, oxirida barcha o'zgarishlar bilan bitta `save_memory`.

c) `owner_recently_active` ikki marta chaqirilishini bitta o'qilgan
   xotira obyektidan hisoblashga o'tkazing.

**Maqsad:** 12 ta so'rovdan **2–3 tagacha** tushirish.

**Ehtiyot bo'ling:** `db.py:38` dagi per-chat lock mantiqini buzmang —
o'qish va yozish orasida lock ushlab turilishi kerak.

---

## 5-QADAM 🔴 — Flood-limit ishlamay qolishi

**Muammo:** `_is_rate_limited` (`main.py:285`) tekshiradi → LLM 5–40 soniya
ishlaydi → `_record_reply` (`main.py:348`) yozadi.

Telethon har bir xabarni **parallel task** sifatida ishlaydi. Ko'p xabar
birdan kelsa, hammasi tekshiruvdan **o'tib bo'ladi**, chunki o'sha paytda
hali hech biri yozilmagan. `MAX_REPLIES_PER_HOUR_GLOBAL=60` limiti 100+
gacha oshib ketishi mumkin — bu esa aynan akkauntni Telegram cheklovidan
himoya qilish uchun qo'yilgan edi.

**Yechim:** joyni **tekshirish paytida band qiling** (reserve), keyin:
- javob muvaffaqiyatli yuborilsa — band qilingan joy o'sha holicha qoladi
- xato bo'lsa (LLM yiqildi, `event.reply()` xato berdi) — joyni
  **qaytaring** (rollback)

Ya'ni `_is_rate_limited` + `_record_reply` ni bitta atomik
`_try_reserve_reply_slot(chat_id) -> bool` funksiyasiga birlashtiring, va
`_release_reply_slot(chat_id)` qo'shing.

---

## 6-QADAM 🔴 — Cheksiz o'sadigan lug'atlar (xotira sizishi)

Quyidagi 4 ta lug'at **hech qachon tozalanmaydi**:

| O'zgaruvchi | Joy |
|---|---|
| `_chat_locks` | `db.py:38` |
| `_chat_reply_times` | `main.py:78` |
| `LAST_INCOMING_ID` | `main.py:72` |
| `PENDING_BOT_REPLIES` | `main.py:67` |

Bot oylab uzluksiz ishlashi kerak. Har yangi chat uchun yozuv qo'shiladi va
hech qachon o'chirilmaydi. `_chat_locks` eng yomoni — har `chat_id` uchun
abadiy `asyncio.Lock` obyekti.

Alohida e'tibor: `_chat_reply_times` bu `defaultdict`, ya'ni
`_is_rate_limited` chaqirilganda **har bir chat uchun** yozuv yaratadi,
hatto javob yuborilmasa ham.

**Yechim:** davriy tozalash tasklari qo'shing (masalan har 30 daqiqada):
- `_chat_reply_times` — bo'sh ro'yxatli yozuvlarni o'chiring
- `LAST_INCOMING_ID` — eski chatlarni o'chiring
- `_chat_locks` — ishlatilmayotgan locklarni o'chiring
  (`lock.locked()` false bo'lganlarini)

Yoki oddiyroq yo'l: `LRU` cheklovi qo'ying (masalan oxirgi 1000 ta chat).

**Qo'shimcha:** `PENDING_BOT_REPLIES` da yana bitta muammo bor — u matn
bo'yicha saqlanadi va **muddati tugamaydi**. Agar outgoing event kelmay
qolsa, yozuv abadiy qoladi va keyinchalik egasi **xuddi shu matnni**
yozsa ("Salom!"), u "botning javobi" deb hisoblanadi va bot o'zini
o'chirmaydi. TTL qo'shing (masalan 60 soniya).

---

## 7-QADAM 🔴 — Xotira xulosasi cheksiz o'sadi

**Muammo:** `llm.py` promptida "400 so'zdan oshmasin" deyilgan, lekin
**kod buni tekshirmaydi**. Model har safar `memory_summary` ni qayta
yozadi va u asta-sekin uzayib boradi.

Bu xulosa **har bir so'rovda** LLM'ga yuboriladi — ya'ni haftalar o'tib
har bir javob sekinroq va qimmatroq bo'lib boradi, siz sezmagan holda.

**Yechim:** `main.py:336` va `main.py:351` da xulosani yozishdan oldin
kesing. Konstanta qo'shing:

```python
MAX_SUMMARY_CHARS = 3000  # ~400 so'z
```

va `update_summary` ga uzatishdan oldin `new_summary[:MAX_SUMMARY_CHARS]`
qiling. Yaxshiroq variant — `db.update_summary` ichida kesish, shunda
qayerdan chaqirilishidan qat'i nazar kafolatlanadi.

---

## Yakuniy tekshiruv

Hamma qadamlar tugagach:

```bash
# Import xatolari yo'qligini tekshiring
./.venv/bin/python -c "import main, config, db, llm, transcribe; print('OK')"

# Botni ishga tushirib, o'zingizga test xabar yozib ko'ring
./.venv/bin/python main.py
```

Tekshirish ro'yxati:
- [ ] Oddiy matn xabarga javob keladi
- [ ] `/status`, `/pause 5m`, `/resume` ishlaydi
- [ ] Siz shaxsan yozsangiz bot jim bo'ladi
- [ ] Ovozli xabar matnga o'giriladi
- [ ] Rasm yuborilganda javob keladi
- [ ] Loglarda API kalit yoki session string chiqmayapti

**Hammasi ishlagach — ushbu B qismni CLAUDE.md dan o'chiring.**
