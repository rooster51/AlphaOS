# AlphaOS

AlphaOS is a cloud-first Streamlit MVP for trading workflow management. It is designed for Streamlit Community Cloud, GitHub source control, Supabase auth/database/storage, and server-side Python API calls.

The MVP intentionally does not support automated trade execution.

## MVP Pages

- Dashboard
- Market Pulse
- Flow & Rotation
- Scanner
- Budget Strategy Selector
- Trade Journal
- P&L Dashboard
- Quant Lab
- Settings

## Current MVP Features

- Supabase-ready authentication
- User settings foundation
- Manual trade journal
- Open positions and closed trades
- Realized P&L tracking
- Daily, weekly, and monthly P&L views
- Win rate, average win/loss, profit factor, and max drawdown
- Watchlist
- Mock market data
- Scoring placeholders

## Local Preview

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

If Supabase secrets are not configured, use the demo session in the sidebar. Demo data is stored in the Streamlit session only.

## Supabase Setup

1. Create a Supabase project.
2. Open SQL Editor.
3. Run `supabase/schema.sql`.
4. In Authentication settings, enable email/password auth.
5. Copy the project URL and anon public key.

The app uses row-level security policies so each authenticated user can access only their own settings, watchlist, trades, and P&L snapshots.

## GitHub Setup

1. Create a new GitHub repository.
2. Commit and push this project.
3. Do not commit `.streamlit/secrets.toml`.
4. Keep `.streamlit/secrets.toml.example` as the template for required secrets.

## Streamlit Community Cloud Deployment

1. Go to Streamlit Community Cloud.
2. Create a new app from the GitHub repository.
3. Set the main file path to `app.py`.
4. Add secrets in App settings:

```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-supabase-anon-key"
```

5. Deploy the app.

The deployed app is browser-based and usable from desktop and phone browsers.

## Architecture Notes

- `app.py` is the main dashboard entrypoint.
- `pages/` contains Streamlit multipage routes.
- `modules/` contains server-side Python logic for auth, data access, metrics, mock market data, and shared UI.
- `supabase/schema.sql` contains database tables, row-level security, and update triggers.
- API keys belong in Streamlit secrets, never in source control.

