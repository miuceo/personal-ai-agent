# 🤖 Shaxsiy AI Kotib — Telegram Userbot

**Telegram Premium ham, Business obunasi ham kerak emas.** Sizning oddiy,
bepul Telegram akkauntingiz ustida ishlaydigan AI agent — sizga yozganlarga
sizning nomingizdan, kontekstni tushunib, o'zi javob beradi. Muhim xabarlarni
esa filtrlab, faqat sizga darhol yetkazadi.

> Bu — [Telethon](https://github.com/LonamiWebs/Telethon) kutubxonasi orqali
> sizning shaxsiy hisobingizga ulanadigan "userbot". Alohida bot akkaunt
> yaratilmaydi, Telegram'ning pullik funksiyalariga bog'liq emas.

---

## Nega bu loyiha kerak?

Telegram'da "avtomatik javob berish" funksiyasi rasman faqat **Telegram
Business** (pullik) obunasida bor, va u ham juda cheklangan: oldindan
yozilgan shablon xabar, soddagina "away message". U hech qanday
kontekstni tushunmaydi, xabarni "muhim/muhim emas" deb ajratmaydi, va
suhbatni davom ettira olmaydi.

Bu loyiha esa **haqiqiy AI agent** sifatida ishlaydi: har bir xabarni
o'qiydi, avvalgi suhbat xotirasini hisobga oladi, kerak bo'lsa to'liq va
mustaqil javob yozadi, kerak bo'lmasa — sizni band deb bildirib, sizga
darhol xabar beradi. Va bularning barchasi **hech qanday pullik Telegram
tarifisiz** ishlaydi.

## Afzalliklari

| | Telegram Business (Away message) | Bu loyiha |
|---|---|---|
| Narxi | Telegram Premium/Business obunasi kerak | **Bepul** (faqat bepul API'lar) |
| Javob turi | Bir xil shablon matn | AI tomonidan **har safar moslashtirilgan**, tabiiy javob |
| Kontekstni tushunish | ❌ Yo'q | ✅ Suhbat xotirasi (memory) + oxirgi xabarlar tarixi |
| Muhimlik darajasini ajratish | ❌ Yo'q | ✅ AI o'zi "muhim / muhim emas" deb baholaydi |
| Muhim xabar bo'yicha ogohlantirish | ❌ Yo'q | ✅ Saved Messages'ga darhol push-xabar |
| Rasm va ovozli xabarni tushunish | ❌ Yo'q | ✅ Vision model + Whisper orqali matnga o'giradi |
| Sizni "ushlab qolish" | ❌ Yo'q | ✅ Siz shaxsan yozsangiz, bot avtomatik jim bo'lib qoladi |
| Boshqarish | Faqat yoqish/o'chirish | `/pause`, `/pause 30m`, `/resume`, `/status` |
| Xavfsizlik | — | Havola/fayl ochmaslik, prompt-injection himoyasi, flood-limit |

Qo'shimcha afzalliklar:

- **To'liq maxfiylik** — hech qanday uchinchi tomon serverida ishlamaydi,
  siz o'zingiz joylab (host qilib) ishga tushirasiz. Faqat siz tanlagan
  LLM va DB provayderlariga so'rov ketadi.
- **Ko'p tilli** — suhbatdosh qaysi tilda yozsa (o'zbek, rus, ingliz),
  bot o'sha tilda javob beradi.
- **Ovozli xabar va rasmni tushunadi** — Groq Whisper orqali ovozdan
  matnga, vision-qobiliyatli LLM orqali rasmdagi savolga javob beradi.
- **Xavfli fayllardan himoya** — APK/EXE/ZIP/hujjat kabi fayllar hech
  qachon yuklab olinmaydi yoki ochilmaydi; havolalarga amal qilinmaydi.
- **Flood-himoya** — soatlik javob limiti (chat va global) bor, hisobingiz
  Telegram tomonidan cheklab qo'yilishidan saqlaydi.
- **Uzoq muddatli xotira** — har bir suhbat uchun xulosa Postgres'da
  saqlanadi, 24 soatdan keyin ham yo'qolmaydi.

## Qanday ishlaydi

1. Kimdir sizga shaxsiy xabar (matn, rasm yoki ovozli) yozadi.
2. Bot bir necha soniya kutadi — sizga shaxsan javob berish imkoniyati
   beriladi (`INITIAL_REPLY_DELAY_SECONDS`).
3. Siz javob bermasangiz, AI xabarni tahlil qiladi:
   - **Muhim emas** (salom, tabrik, oddiy savol) → to'liq, mustaqil javob
     yozadi, xuddi siz yozgandek.
   - **Muhim** (ish taklifi, mijoz, to'lov, shartnoma va h.k.) → suhbatdoshga
     "band, tez orada shaxsan javob beraman" deb yozadi, sizga esa Saved
     Messages'ga darhol qisqa xabarnoma yuboradi (kim, nima yozdi, havola).
4. Agar siz o'zingiz shu suhbatda yozsangiz — bot avtomatik jim bo'lib
   qoladi (`OWNER_PAUSE_MINUTES` daqiqa), keyin qayta ishga tushadi.
5. O'zingizga (Saved Messages) buyruqlar yozib botni boshqarasiz:
   - `/pause` / `/pause 30m` / `/pause 2h` — vaqtincha yoki butunlay to'xtatish
   - `/resume` — qayta davom ettirish
   - `/status` — hozirgi holat, o'qilmagan yozuvlar, shu soatdagi javoblar soni

## Texnologiyalar

- **[Telethon](https://github.com/LonamiWebs/Telethon)** — shaxsiy hisobga
  ulanish (bot token emas, real user session)
- **[OpenRouter](https://openrouter.ai)** — LLM chaqiruvlari (bepul
  qatlamdagi modellar bilan ham ishlaydi)
- **[Groq](https://groq.com)** — Whisper orqali ovozli xabarlarni matnga
  o'girish
- **PostgreSQL** (masalan, [Neon](https://neon.tech) bepul tarifi) —
  suhbat xotirasi va holatni saqlash

## O'rnatish

```bash
git clone <repo-url> secretary-bot
cd secretary-bot
pip install -r requirements.txt
cp .env.example .env
```

`.env` faylini to'ldiring:

| O'zgaruvchi | Qayerdan olinadi |
|---|---|
| `API_ID`, `API_HASH` | [my.telegram.org/apps](https://my.telegram.org/apps) — telefon raqamingiz bilan kirib olasiz (bepul) |
| `PHONE_NUMBER` | Sizning haqiqiy Telegram raqamingiz |
| `OWNER_ID` | Sizning Telegram user ID'ingiz ([@userinfobot](https://t.me/userinfobot)) |
| `DATABASE_URL` | Neon (yoki boshqa) PostgreSQL ulanish satri (bepul tarif yetarli) |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) (bepul tarif yetarli) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) (ovozli xabarlar uchun, bepul tarif yetarli) |

Birinchi marta sessiya yaratish uchun:

```bash
python generate_session.py
```

Telefoningizga kelgan tasdiqlash kodini kiritasiz, chiqqan
`TELEGRAM_SESSION` qiymatini `.env`ga qo'yasiz. Shundan keyin:

```bash
python main.py
```

## ⚠️ Muhim eslatmalar

1. **`.env` va `.session` fayllarini hech qachon commit qilmang yoki
   ulashmang** — bular orqali sizning butun Telegram hisobingizga kirish
   mumkin bo'ladi. `.gitignore`da bular allaqachon istisno qilingan.
2. Bu — Telegram'ning rasmiy Business API'si emas, **userbot**
   (Telethon orqali shaxsiy sessiya). Foydalanish shartlariga qat'iy zid
   emas, lekin rasman qo'llab-quvvatlanmaydi. Avval faqat o'zingizning
   test suhbatlaringizda sinab ko'ring.
3. Xavfsizlik va flood-limit sozlamalari (`MAX_REPLIES_PER_HOUR_*`,
   `OWNER_PAUSE_MINUTES`, `INITIAL_REPLY_DELAY_SECONDS`) `.env` orqali
   moslashtiriladi — ehtiyotkorlik bilan sinab ko'rib, keyin kengaytiring.

## Kengaytirish g'oyalari

- Doimiy serverga (masalan, bepul VPS/VM) joylab, `systemd` orqali
  avtomatik qayta ishga tushishini ta'minlash
- Bir nechta odam uchun har biriga alohida `.env` va alohida
  API_ID/API_HASH bilan ishga tushirish (har biri o'z hisobidan ishlaydi)
- Kalendar integratsiyasi va tool-calling — real harakat qila oladigan
  (masalan, uchrashuv belgilash) to'liq agent darajasiga chiqarish

## Litsenziya

Ochiq kodli — istagancha fork qiling, o'zgartiring, o'zingizning
ehtiyojingizga moslang.
