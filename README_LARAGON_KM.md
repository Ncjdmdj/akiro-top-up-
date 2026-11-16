# Telegram Game Top Up Bot — Laragon (Windows)

រត់ដោយគ្មាន Docker៖ MySQL ប្រើរបស់ Laragon, Python រត់ក្នុង `venv`។

## រចនាសម្ព័ន្ធ
```
topup-bot-laragon/
├─ app/ (bot.py, admin.py, ...)
├─ templates/  static/
├─ .env.example  laragon_setup.sql  setup.bat  run.bat  requirements.txt
```

## ដំឡើង
1. ដាក់ folder នេះក្នុង `C:\laragon\www\topup-bot`
2. Laragon → **Start All** (ត្រូវការ MySQL)
3. កែ `laragon_setup.sql`៖ ប្តូរ `CHANGE_ME` (password DB)
4. Laragon Terminal ក្នុង folder project៖ `setup.bat`
   (បង្កើត `.env`, `venv`, install packages, import SQL)
5. កែ `.env`៖ `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `KHMER_TOPUP_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY`, password ក្នុង `DATABASE_URL` (ត្រូវដូច SQL)
6. `run.bat`
7. Admin Panel៖ http://localhost:8080

## ភាពខុសគ្នាពី Docker
| Docker | Laragon |
|---|---|
| DB host `db` | `127.0.0.1` |
| `docker compose up -d --build` | `run.bat` |
| `docker compose logs -f bot` | មើល window `run.bat` |
| restart policy | loop ក្នុង `run.bat` |
| Admin bind `0.0.0.0` | `ADMIN_HOST=127.0.0.1` (ក្នុង .env) |

## កូដដែលបានកែ
- `config.py`: `DEFAULT_MARKUP` និង `ADMIN_TELEGRAM_ID` ជាប់ជួរតែមួយដោយ `\n` អក្សរ → **SyntaxError** (កែហើយ); បន្ថែម `ADMIN_HOST`
- `bot.py`: caption បង្កាន់ដៃមាន `\\n` បង្ហាញជាអក្សរ `\n` ដល់ Admin (កែហើយ)
- `main.py`: ប្រើ `ADMIN_HOST`

## បើមិនដំណើរការ
- `Access denied`: password `.env` ≠ SQL → `ALTER USER 'topup_user'@'127.0.0.1' IDENTIFIED BY '...';`
- `Can't connect to MySQL`: MySQL Laragon មិនទាន់ Start
- `Address already in use`: ប្តូរ `ADMIN_PORT=8081`
- `ModuleNotFoundError: app`: រត់ពី root folder (ដែលមាន `app/`)
- Missing environment variable: មិនទាន់បំពេញ `.env`
- 401/402/429: API key / balance / rate limit

## 24/7
Laragon លើ PC ត្រូវបើកជានិច្ច។ ឬ Task Scheduler ("At startup" → `run.bat`)។ Production ប្រើ VPS ជាមួយ HTTPS។
