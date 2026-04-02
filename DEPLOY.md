# Deployment Guide

## Stack overview

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Backend   | Python 3.9+, Django 4.2, gunicorn       |
| Database  | Supabase (PostgreSQL), via psycopg2     |
| SMS       | Twilio                                  |
| Email     | Resend                                  |
| NLP       | Anthropic Claude Haiku                  |
| Hosting   | Railway                                 |

---

## 1. Supabase setup

1. Create a free project at [supabase.com](https://supabase.com)
2. Open the **SQL Editor** and paste the contents of `supabase/schema.sql`
3. Run it — all tables and RLS policies will be created
4. Copy your **Database connection string** from:
   - Settings → Database → Connection string → URI
   - It looks like: `postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres`
   - Append `?sslmode=require` to the end

> **Note:** The backend connects directly via psycopg2 — you do **not** need the Supabase URL or anon key anymore.

---

## 2. Twilio setup

1. Create an account at [twilio.com](https://twilio.com)
2. Buy one phone number (~$1/mo)
3. Note your **Account SID** and **Auth Token**
4. Come back to set the webhook URL after deploying (step 5)

---

## 3. Resend setup

1. Sign up at [resend.com](https://resend.com) (free tier: 100 emails/day)
2. Verify a sending domain or use the sandbox
3. Copy your **API key**

---

## 4. Local development

```bash
# Clone and enter the repo
git clone <your-repo>
cd <your-repo>

# Install Python dependencies
pip3 install -r requirements.txt

# Copy env file and fill in your values
cp .env.example .env
# Edit .env — DATABASE_URL and DJANGO_SECRET_KEY are required

# Verify everything loads correctly
python3 manage.py check

# Run the dev server (Twilio webhooks won't reach localhost — use ngrok for that)
SKIP_TWILIO_VALIDATION=true python3 manage.py runserver
```

### Testing the SMS flow locally with ngrok

```bash
# In one terminal
ngrok http 8000

# In another terminal
SKIP_TWILIO_VALIDATION=true python3 manage.py runserver

# Set your Twilio webhook to the ngrok URL: https://xxxx.ngrok.io/sms
```

---

## 5. Deploy to Railway

1. Push your code to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. Set all environment variables in the Railway dashboard:

```
ANTHROPIC_API_KEY=sk-ant-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
DATABASE_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres?sslmode=require
RESEND_API_KEY=re_...
DJANGO_SECRET_KEY=<long random string — generate with: python3 -c "import secrets; print(secrets.token_hex(50))">
DEBUG=false
ALLOWED_HOSTS=localhost,.railway.app
BASE_URL=https://your-app-name.railway.app
```

5. Railway will auto-detect Python via Nixpacks and run the start command from `railway.json`:
   ```
   gunicorn nudge.wsgi:application --bind 0.0.0.0:$PORT
   ```
6. Copy the Railway-assigned URL (e.g. `https://nudge-production.railway.app`)

---

## 6. Configure Twilio webhook

1. Go to Twilio Console → Phone Numbers → your number
2. Under **Messaging** set:
   - Webhook URL: `https://your-app.railway.app/sms`
   - HTTP Method: `POST`
3. Save

---

## 7. Test the flow

Text **"setup"** to your Twilio number. You should get:
> "Welcome to TextApp! What's your team name?"

Then follow the prompts to create your team and first user.

---

## GitHub Pages (static landing page — waitlist only)

Use this to share a landing page with potential users before the backend is live.

### One-time setup
1. Create a free [Formspree](https://formspree.io) account
2. Create a new form and copy the form ID (e.g. `xabcdefg`)
3. In `docs/index.html`, replace `YOUR_FORM_ID`:
   ```
   https://formspree.io/f/YOUR_FORM_ID → https://formspree.io/f/xabcdefg
   ```

### Deploy
```bash
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Then in GitHub:
1. Go to your repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`
4. Click **Save**

Live at `https://YOUR_USERNAME.github.io/YOUR_REPO` within ~2 minutes.

> Only the waitlist form works on GitHub Pages. Login and dashboard require the Railway backend.

---

## Deploy to Render (alternative)

1. Push code to GitHub
2. Create a new **Web Service** on [render.com](https://render.com)
3. Connect your repo and set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn nudge.wsgi:application --bind 0.0.0.0:$PORT`
4. Set all env vars in the Render dashboard (same list as Railway above)
5. Deploy

---

## Cost estimate (small team, ~100 msgs/day)

| Service    | Cost/month                             |
|------------|----------------------------------------|
| Railway    | ~$5 (Hobby plan)                       |
| Twilio SMS | ~$2.40 (300 msgs × $0.0079)            |
| Supabase   | $0 (free tier)                         |
| Resend     | $0 (free tier)                         |
| Anthropic  | ~$0.10 (Haiku, 100 msgs × ~$0.001)     |
| **Total**  | **~$7.50/mo**                          |

---

## Timezone / digest configuration

The default digest time is **8am in the team's local timezone**. This is configured per team in the `teams` table (`timezone` and `digest_hour` columns). You can change it directly in the Supabase table editor.

`timezone` must be a valid IANA timezone string (e.g. `America/New_York`, `America/Los_Angeles`, `Europe/London`).
