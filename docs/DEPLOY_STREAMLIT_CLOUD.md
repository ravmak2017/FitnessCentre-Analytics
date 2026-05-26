# Deploying to Streamlit Community Cloud (free)

Step-by-step to get a public live demo at `https://<your-app-name>.streamlit.app`.

## 1. Push this repo to GitHub

```bash
cd "GitHub-Portfolio"

# First time only
git init
git add .
git commit -m "Initial commit — ABC Analytics portfolio"

# Create an empty repo on github.com (e.g. abc-analytics), then:
git remote add origin https://github.com/ravmak2017/abc-analytics.git
git branch -M main
git push -u origin main
```

> The `.gitignore` already excludes `.env`, real data, and Streamlit secrets.
> Verify with `git status` before pushing — nothing private should appear.

## 2. Sign in to Streamlit Community Cloud

Go to <https://share.streamlit.io/> and sign in with GitHub.

## 3. Deploy

Click **"Create app"** → select your repo, branch (`main`), and main file
(`Dashboard.py`).

Advanced settings → set the **Python version** to 3.12 (or whichever matches
your local).

## 4. Add the Anthropic API key as a secret

Streamlit Cloud → app settings → **Secrets**. Paste:

```toml
ANTHROPIC_API_KEY = "sk-ant-…"
```

The dashboard's `load_dotenv()` calls fall through to OS env vars when the
`.env` file is missing, and Streamlit Cloud injects secrets as env vars
automatically.

## 5. Wait for build

First build takes ~3 min. Once live, the URL is shareable from anywhere.

## 6. (Optional) Restrict to invited viewers

Free tier of Streamlit Cloud doesn't include SSO, but you can:
- Make the app **private** (visible only to you in the dashboard list), OR
- Add a tiny password-check at the top of `Dashboard.py`:

```python
PASSWORD = st.secrets.get("APP_PASSWORD", "")
if PASSWORD:
    pw = st.text_input("Password", type="password")
    if pw != PASSWORD:
        st.stop()
```

Then add `APP_PASSWORD = "your-secret"` to the same secrets panel.

## Caveats

- **API costs come from your Anthropic key** — anyone who can reach the URL
  can spend tokens. Lock the dashboard down or pre-generate all AI content
  so the live demo never calls the API (it ships with `AI- Output/` already
  populated, so the default browse experience uses zero API).
- **Sample data only** — never push real customer data. The `.gitignore`
  protects against accidents, but double-check before each push.

## Quick alternative — Hugging Face Spaces

Same idea, slightly different config. Create a Space, upload the repo, add
the API key as a secret. Streamlit option is selected on Space creation.

## Self-hosted (Cloudflare Tunnel)

For private deployments where data must stay on your machine, see the
Cloudflare Tunnel quick-start guide (~5 min setup, free permanent HTTPS URL
pointing at your local PC).
