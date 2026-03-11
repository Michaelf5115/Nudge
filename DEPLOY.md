# Deployment Guide

## 1. Supabase setup
1. Create a free project at supabase.com
2. Open the SQL Editor and paste the contents of `supabase/schema.sql`
3. Run it — all 7 tables will be created
4. Copy your project URL and anon key from Settings → API

## 2. Twilio setup
1. Create a free trial account at twilio.com
2. Buy one phone number (~$1/mo)
3. Note your Account SID and Auth Token
4. Come back to set the webhook URL after deploying

## 3. Resend setup
1. Sign up at resend.com (free tier: 100 emails/day)
2. Verify a sending domain or use the sandbox
3. Copy your API key

## 4. Deploy to Railway
1. Install Railway CLI: `npm install -g @railway/cli`
2. `railway login`
3. `railway init` (in this directory)
4. `railway up`
5. Set all environment variables in the Railway dashboard:
   ```
   ANTHROPIC_API_KEY=...
   TWILIO_ACCOUNT_SID=...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+1...
   SUPABASE_URL=...
   SUPABASE_ANON_KEY=...
   RESEND_API_KEY=...
   BASE_URL=https://your-app-name.railway.app
   NODE_ENV=production
   ```
6. Copy your Railway app URL

## 5. Configure Twilio webhook
1. Go to Twilio Console → Phone Numbers → your number
2. Under "Messaging" set:
   - Webhook URL: `https://your-app.railway.app/sms`
   - HTTP Method: POST
3. Save

## 6. Test the flow
Text "setup" to your Twilio number. You should get:
> "Welcome to TextApp! 👋 What's your team name?"

## GitHub Pages (static preview — waitlist only)

Use this to quickly share a landing page with potential users before the backend is live.

### One-time setup
1. Create a free [Formspree](https://formspree.io) account
2. Create a new form — copy the form ID (looks like `xabcdefg`)
3. In `docs/index.html`, replace `YOUR_FORM_ID` with your real ID:
   ```
   https://formspree.io/f/YOUR_FORM_ID  →  https://formspree.io/f/xabcdefg
   ```

### Deploy
```bash
git init          # if not already a git repo
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Then in GitHub:
1. Go to your repo → **Settings** → **Pages**
2. Under "Source" select **Deploy from a branch**
3. Branch: `main`, Folder: `/docs`
4. Click **Save**

Your site will be live at `https://YOUR_USERNAME.github.io/YOUR_REPO` within ~2 minutes.

> **Note:** Only the waitlist email form works on GitHub Pages (via Formspree). The Login button and dashboard require the Railway backend.

---

## Deploy to Render (alternative)
1. Push code to GitHub
2. Create a new Web Service on render.com
3. Connect your repo, set build command: `npm install`
4. Set start command: `node src/index.js`
5. Set all env vars in Render dashboard
6. Deploy

## Cost estimate (small team, ~100 msgs/day)
| Service     | Cost/month  |
|-------------|-------------|
| Railway     | ~$5 (Hobby) |
| Twilio SMS  | ~$2.40 (300 msgs × $0.0079) |
| Supabase    | $0 (free tier) |
| Resend      | $0 (free tier) |
| Anthropic   | ~$0.10 (Haiku, 100 msgs × ~$0.001) |
| **Total**   | **~$7.50/mo** |

## Timezone configuration
Default digest time is 8am ET. To change per team, update the `timezone`
and `digest_hour` columns in the `teams` table directly in Supabase.
(A future SMS command `"set digest to 9am"` can be added easily.)
