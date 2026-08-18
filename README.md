# Shaxsiy AI Kotib — Telethon Userbot

Bu loyiha Telegram Business obunasi **talab qilmaydi**. Bot alohida "bot hisob"
sifatida emas, sizning shaxsiy Telegram akkauntingiz nomidan (Telethon
kutubxonasi orqali) ishlaydi.

## Qanday ishlaydi

1. Kimdir sizga shaxsiy xabar yozadi.
2. Agar siz o'sha suhbatda oxirgi `OWNER_PAUSE_MINUTES` daqiqa ichida
   shaxsan javob yozmagan bo'lsangiz — bot avtomatik javob beradi (OpenRouter
   orqali, xotira xulosasi asosida).
3. Agar siz o'zingiz yozsangiz — bot o'sha suhbatda vaqtincha jim bo'lib
   qoladi, keyin avtomatik davom etadi.
4. O'zingizga ("Saved Messages"ga) `/messages` deb yozsangiz — bot sizga
   javob berilgan barcha suhbatlarning qisqa xulosasini yuboradi. `/read-all`
   deb yozsangiz — bu ro'yxat tozalanadi.
5. Agar kelgan xabar **muhim** deb baholansa (ish taklifi, mijoz, to'lov
   va h.k.) — suhbatdoshga "band, tez orada javob beradi" deb javob
   beriladi, siz esa Saved Messages'ga darhol qisqa xabarnoma olasiz
   (kim yozdi, nima yozdi, suhbatga havola).
6. O'zingizni boshqarish uchun komandalar (Saved Messages'ga yoziladi):
   - `/pause` — botni butunlay to'xtatadi (hech kimga javob bermaydi)
   - `/pause 30m` yoki `/pause 2h` — ma'lum muddatga to'xtatadi
   - `/resume` — botni qayta ishga tushiradi
   - `/status` — hozirgi holatni (faolmi/to'xtatilganmi, nechta
     o'qilmagan yozuv bor, shu soatda nechta javob yuborilgan) ko'rsatadi

## O'rnatish

```bash
cd telegram-secretary-bot
pip install -r requirements.txt
cp .env.example .env
```

`.env` faylini oching va quyidagilarni to'ldiring:

- **API_ID / API_HASH** — https://my.telegram.org/apps saytidan, telefon
  raqamingiz bilan kirib oling (bepul).
- **PHONE_NUMBER** — sizning haqiqiy Telegram raqamingiz.
- **OPENROUTER_API_KEY** — https://openrouter.ai/keys saytidan (bepul
  qatlam yetarli).

## Ishga tushirish

```bash
python main.py
```

Birinchi marta ishga tushirganda Telegram ilovangizga tasdiqlash kodi
keladi — shuni terminalga kiritasiz. Shundan keyin sessiya fayl
(`secretary_session.session`) saqlanadi, keyingi safar kod so'ralmaydi.

## MUHIM — xavfsizlik va xatarlar

1. **`.env` va `.session` fayllarini hech qachon GitHub'ga yoki boshqa
   birovga yubormang** — ular orqali sizning Telegram hisobingizga to'liq
   kirish mumkin bo'ladi.
2. Bu — Telegram'ning rasmiy Business API'si emas, **userbot** deb
   ataladi. Telegram'ning foydalanish shartlariga qat'iy zid emas, lekin
   rasman qo'llab-quvvatlanmaydi. Juda ko'p xabar yuborish yoki shubhali
   faollik hisobingiz vaqtincha cheklanishiga sabab bo'lishi mumkin —
   shuning uchun avval **faqat o'zingizning test suhbatlaringizda** sinab
   ko'ring, keyin ehtiyotkorlik bilan kengaytiring.
3. Xotira Neon PostgreSQL'da saqlanadi (`DATABASE_URL`) — server qayta
   ishga tushsa ham yo'qolmaydi. Faqat `.session` (yoki `TELEGRAM_SESSION`)
   va `.env` maxfiy qoladi, ularni hech qachon commit qilmang.
4. Flood himoyasi bor (`MAX_REPLIES_PER_HOUR_PER_CHAT` /
   `MAX_REPLIES_PER_HOUR_GLOBAL`), lekin baribir avval faqat o'zingizning
   test suhbatlaringizda sinab ko'ring.

## Keyingi qadamlar (kengaytirish uchun)

- Doimiy serverga (masalan, Google Cloud e2-micro bepul tarif) joylab,
  `systemd` service sifatida ishga tushirish — jarayon o'lib qolsa avtomatik
  qayta ko'tarilishi uchun
- Bir nechta mijoz uchun bir xil kodni har biriga alohida `.env` bilan
  ishga tushirish (har biriga alohida API_ID/API_HASH kerak — chunki har
  biri o'z shaxsiy hisobidan ishlaydi)
- Kalendar integratsiyasi va tool-calling (haqiqiy harakat qila oladigan
  agent uchun)
