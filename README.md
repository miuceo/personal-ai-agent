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
3. Xotira hozircha oddiy SQLite faylida (`secretary.db`) saqlanadi — bu
   ishga tushirilgan kompyuterda qoladi. Agar buni doimiy serverga
   (masalan, Oracle Cloud instance) ko'chirsangiz, fayl ham birga
   ko'chishi kerak, aks holda xotira yo'qoladi.

## Keyingi qadamlar (kengaytirish uchun)

- SQLite'ni Neon PostgreSQL'ga almashtirish (server uchun barqarorroq)
- Serverga (Oracle Cloud) joylab, doimiy ishlaydigan qilish (masalan,
  `systemd` service yoki `screen`/`tmux` orqali)
- Bir nechta mijoz uchun bir xil kodni har biriga alohida `.env` bilan
  ishga tushirish (har biriga alohida API_ID/API_HASH kerak — chunki har
  biri o'z shaxsiy hisobidan ishlaydi)
