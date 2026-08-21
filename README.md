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
| Boshqarish | Faqat yoqish/o'chirish | `/pause`, `/resume`, `/status`, `/inbox` (tugmalar + tabiiy til) |
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
3. Siz javob bermasangiz, AI xabarni tahlil qiladi. Bot hech qachon
   sizning nomingizdan, siz o'zingiz yozayotgandek javob bermaydi — u
   o'zini ochiq ravishda sizning AI kotibingiz sifatida tanishtiradi va
   siz haqingizda doim 3-shaxsda gapiradi:
   - **Kotibga tegishli** (salom, sizni bilish/bog'lanish bilan bog'liq
     savol) → kotib nomidan to'liq javob beradi.
   - **Muhim** (ish taklifi, mijoz, to'lov, shartnoma va h.k.) → suhbatdoshga
     "band, tez orada shaxsan javob beradi" deb yozadi, sizga esa Saved
     Messages'ga darhol qisqa xabarnoma yuboradi (kim, nima yozdi, havola).
   - **Doiradan tashqari** (umumiy bilim savoli, kod yozish, "sen endi X
     san" kabi rol/vazifa berish urinishi) → bajarmaydi, faqat shaxsiy
     kotib ekanini tushuntiradi. Bot ChatGPT yoki umumiy yordamchi emas.
4. Agar siz o'zingiz shu suhbatda yozsangiz — bot avtomatik jim bo'lib
   qoladi (`OWNER_PAUSE_MINUTES` daqiqa), keyin qayta ishga tushadi.
5. Har bir kiruvchi xabar — muhim yoki oddiy, farqi yo'q — inbox'ga
   yoziladi, shunda hech narsa yo'qolib qolmaydi.
6. O'zingizga (Saved Messages) buyruqlar yozib botni boshqarasiz:
   - `/pause` / `/pause 30m` / `/pause 2h` — vaqtincha yoki butunlay to'xtatish
   - `/resume` — qayta davom ettirish
   - `/status` — hozirgi holat, shu soatdagi javoblar soni
   - `/inbox` (yoki `/unread`) — o'qilmagan xabarlar ro'yxati, har biriga
     "✅ O'qildi" / "🗑 O'chirish" tugmalari bilan
   - `/read <raqam>`, `/delete <raqam>`, `/readall` — yoki tabiiy tilda:
     "o'qilmagan xabarlarni ko'rsat", "42-ni o'chir", "hammasini o'qidim"

## Texnologiyalar

- **[Telethon](https://github.com/LonamiWebs/Telethon)** — shaxsiy hisobga
  ulanish (bot token emas, real user session)
- **[Groq](https://groq.com)** — matnli javoblar (`openai/gpt-oss-120b` /
  `gpt-oss-20b`) va ovozli xabarlarni matnga o'girish (Whisper, o'zbek
  tiliga moslangan)
- **[OpenRouter](https://openrouter.ai)** — faqat rasm (vision)
  tushunish uchun — Groq'ning bepul chat modellari rasm qabul qilmaydi
- **PostgreSQL** (masalan, [Neon](https://neon.tech) bepul tarifi) —
  suhbat xotirasi va holatni saqlash

### Hech qachon "yiqilib qolmaslik" strategiyasi

Har bir LLM chaqiruvi **zanjir** shaklida ishlaydi — bitta provayder
yiqilsa yoki bepul limitga urilsa, kod avtomatik keyingisiga o'tadi:

| Vazifa | Zanjir tartibi |
|---|---|
| Matnli javob | Groq `gpt-oss-120b` → Groq `gpt-oss-20b` → OpenRouter `z-ai/glm-5.2:free` |
| Ovozli xabar (STT) | Groq `whisper-large-v3-turbo` (uz) → Groq `whisper-large-v3` (uz) |
| Rasm tushunish (vision) | OpenRouter `gemma-4-31b-it:free` → `nemotron-3-nano-omni:free` → `openrouter/free` (avtomatik router) |

Agar **zanjirdagi hamma provayder bir vaqtda** ishlamay qolsa (juda kam
uchraydigan holat), bot baribir jim qolmaydi: standart "band, tez orada
javob beraman" xabari yuboriladi va bu holat avtomatik "muhim" deb
belgilanadi — ya'ni sizga (Saved Messages'ga) darhol xabarnoma boradi,
chunki AI tushunolmagan xabarni odam ko'rib chiqishi kerak.

Zanjirlar `.env` orqali sozlanadi (`GROQ_TEXT_MODELS`,
`OPENROUTER_VISION_MODELS` va h.k.) — vergul bilan ajratilgan model
ro'yxati, tartib muhim.

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
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) — matnli javoblar va ovozli xabarlar uchun (bepul tarif yetarli) |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) — faqat rasm (vision) tushunish uchun (bepul tarif yetarli) |

Model zanjirlari (`GROQ_TEXT_MODELS`, `GROQ_STT_MODELS`,
`OPENROUTER_VISION_MODELS`, `OPENROUTER_TEXT_FALLBACK_MODEL`) uchun
`.env.example`dagi standart qiymatlar yetarli — o'zgartirish shart emas,
lekin bepul model ro'yxatlari vaqti-vaqti bilan yangilanadi, shuning uchun
ishlamay qolsa avval shu qiymatlarni tekshiring.

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
