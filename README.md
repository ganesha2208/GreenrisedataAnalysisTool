# Lead Intelligence Dashboard

A Streamlit dashboard for analysing IndiaMART lead exports — built for sales & marketing stakeholders.

## Features
- Executive summary with period-over-period KPIs
- Trends, geography (India map), products, channels, crops
- Prospect segmentation (RFM: Champions / New / Active / Slipping / Dormant)
- Hot-lead scoring
- WhatsApp campaign builder with per-segment templates
- Data-quality audit (spam / duplicate / fake detection)
- CSV exports for every view

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then upload a lead-export CSV/Excel via the sidebar. Expected columns include
`QUERY_TIME`, `SENDER_MOBILE`, `SENDER_EMAIL`, `SENDER_STATE`, `SENDER_CITY`,
`QUERY_MCAT_NAME`, `QUERY_MESSAGE`, `QUERY_TYPE`.

## Deploy to Streamlit Community Cloud

1. Fork / push this repo to your GitHub account.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → select this repo → branch `main` → main file `app.py` → **Deploy**.
4. Share the generated `https://<app-name>.streamlit.app` URL.

## Tech
- Python 3.10+
- Streamlit, pandas, plotly, openpyxl

## Note
No data is bundled with this repo. Lead CSVs are PII-sensitive — upload them at runtime only.
