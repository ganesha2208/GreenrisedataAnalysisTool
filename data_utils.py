"""Data loading, cleaning, enrichment for IndiaMart-style lead exports."""
import pandas as pd
import numpy as np
import re

# Approximate state centroids for India bubble map
INDIA_STATE_COORDS = {
    'Andhra Pradesh': (15.9129, 79.7400),
    'Arunachal Pradesh': (28.2180, 94.7278),
    'Assam': (26.2006, 92.9376),
    'Bihar': (25.0961, 85.3131),
    'Chhattisgarh': (21.2787, 81.8661),
    'Goa': (15.2993, 74.1240),
    'Gujarat': (22.2587, 71.1924),
    'Haryana': (29.0588, 76.0856),
    'Himachal Pradesh': (31.1048, 77.1734),
    'Jharkhand': (23.6102, 85.2799),
    'Karnataka': (15.3173, 75.7139),
    'Kerala': (10.8505, 76.2711),
    'Madhya Pradesh': (22.9734, 78.6569),
    'Maharashtra': (19.7515, 75.7139),
    'Manipur': (24.6637, 93.9063),
    'Meghalaya': (25.4670, 91.3662),
    'Mizoram': (23.1645, 92.9376),
    'Nagaland': (26.1584, 94.5624),
    'Odisha': (20.9517, 85.0985),
    'Punjab': (31.1471, 75.3412),
    'Rajasthan': (27.0238, 74.2179),
    'Sikkim': (27.5330, 88.5122),
    'Tamil Nadu': (11.1271, 78.6569),
    'Telangana': (18.1124, 79.0193),
    'Tripura': (23.9408, 91.9882),
    'Uttar Pradesh': (26.8467, 80.9462),
    'Uttarakhand': (30.0668, 79.0193),
    'West Bengal': (22.9868, 87.8550),
    'Delhi': (28.7041, 77.1025),
    'Jammu and Kashmir': (33.7782, 76.5762),
    'Ladakh': (34.2996, 78.2932),
    'Puducherry': (11.9416, 79.8083),
    'Chandigarh': (30.7333, 76.7794),
    'Andaman and Nicobar Islands': (11.7401, 92.6586),
    'Dadra and Nagar Haveli and Daman and Diu': (20.1809, 73.0169),
    'Lakshadweep': (10.5667, 72.6417),
}


def normalize_phone(phone):
    """Clean phone number. Returns digits-only 10-12 chars, or None if invalid."""
    if not phone or pd.isna(phone):
        return None
    digits = re.sub(r'\D', '', str(phone))
    # trim 0 prefix
    if len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    # trim 91 prefix for matching
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    if len(digits) == 10:
        return digits
    return None


def phone_for_whatsapp(phone):
    """Return 91XXXXXXXXXX format for WhatsApp."""
    d = normalize_phone(phone)
    return f"91{d}" if d else None


def is_fake_phone(phone):
    """Detect obviously-fake phones."""
    d = normalize_phone(phone)
    if not d:
        return 'invalid-format'
    if len(set(d)) == 1:
        return 'all-same-digit'
    if d in ('1234567890', '0123456789', '9876543210', '1111111111', '9999999999'):
        return 'sequential-fake'
    if d[0] not in '6789':
        return 'invalid-prefix'
    return None


FAKE_NAME_PATTERNS = {
    'buyer', 'test', 'testing', 'abc', 'xyz', 'admin', 'user', 'customer',
    'guest', 'unknown', 'na', 'n/a', 'none', 'nil', '.', '-',
}


def flag_spam(df):
    """Add IS_SPAM + SPAM_REASON columns to df."""
    reasons = [[] for _ in range(len(df))]

    if 'SENDER_MOBILE' in df.columns:
        phone_counts = df['SENDER_MOBILE'].value_counts()
        for i, ph in enumerate(df['SENDER_MOBILE'].values):
            fake = is_fake_phone(ph)
            if fake:
                reasons[i].append(f'phone:{fake}')
            if ph in phone_counts and phone_counts[ph] >= 20:
                reasons[i].append(f'phone-freq:{phone_counts[ph]}x')

    if 'SENDER_NAME' in df.columns:
        for i, nm in enumerate(df['SENDER_NAME'].values):
            if pd.isna(nm) or not str(nm).strip():
                reasons[i].append('name:empty')
                continue
            clean = re.sub(r'[^a-z]', '', str(nm).lower())
            if clean in FAKE_NAME_PATTERNS:
                reasons[i].append(f'name:{clean}')
            elif len(clean) <= 1:
                reasons[i].append('name:too-short')

    df = df.copy()
    df['SPAM_REASON'] = [', '.join(r) if r else '' for r in reasons]
    df['IS_SPAM'] = df['SPAM_REASON'] != ''
    return df


# WhatsApp message templates keyed by segment
WA_TEMPLATES = {
    'Champions': (
        "Hi {name} 🙏, great to see you back! You've been checking our {product} range. "
        "We have a special repeat-customer price this month. Shall I share the latest quote? "
        "– Greenrise Agro"
    ),
    'New': (
        "Hi {name} 🙏, thanks for your interest in {product} at Greenrise Agro. "
        "When is a good time to call you with pricing and samples? – Greenrise Agro"
    ),
    'Active': (
        "Hi {name}, quick update on {product} — fresh stock has arrived and prices are firm. "
        "Want me to share the latest rate list? – Greenrise Agro"
    ),
    'Slipping': (
        "Hi {name}, it's been a while 🌱. Season is starting and we're running an offer on {product}. "
        "Reply YES to get the price list. – Greenrise Agro"
    ),
    'Dormant': (
        "Hi {name}, {product} season is here! 🌾 Latest catalogue and prices available. "
        "Reply YES to receive. – Greenrise Agro"
    ),
    'Hot': (
        "Hi {name} 🙏, thank you for your enquiry on {product}. "
        "I am from Greenrise Agro — can I call you now to share the best price? – Greenrise Agro"
    ),
}


def build_whatsapp_message(segment_or_tier, name, product):
    """Return a personalized WhatsApp message string."""
    tpl = WA_TEMPLATES.get(segment_or_tier, WA_TEMPLATES['Active'])
    nm = (name or 'Sir/Madam').split()[0].title() if name else 'Sir/Madam'
    pr = product or 'our fertilizer range'
    return tpl.format(name=nm, product=pr)

QUERY_TYPE_LABELS = {
    'W': 'Website / WhatsApp',
    'B': 'Buy-Lead',
    'P': 'Phone Call',
    'WA': 'WhatsApp',
    'BIZ': 'Buy-Lead (BIZ)',
    'V': 'Verified Lead',
}

CROP_KEYWORDS = [
    'vegetable', 'fruit', 'sugarcane', 'grape', 'pomegranate', 'cotton',
    'paddy', 'rice', 'wheat', 'tomato', 'onion', 'potato', 'chilli', 'chili',
    'banana', 'mango', 'orange', 'soybean', 'maize', 'corn', 'tea', 'coffee',
    'turmeric', 'ginger', 'garlic', 'cauliflower', 'cabbage', 'brinjal',
    'okra', 'groundnut', 'chickpea', 'chana', 'moong', 'urad', 'arhar', 'toor',
    'masoor', 'mustard', 'flower', 'rose', 'marigold', 'papaya', 'guava',
    'watermelon', 'apple', 'capsicum', 'coconut', 'arecanut', 'strawberry',
    'pepper', 'cardamom', 'cumin', 'coriander', 'millet', 'jowar', 'bajra',
    'barley', 'cashew', 'tobacco',
]


def _to_rupees(num_str, unit=''):
    if not num_str:
        return None
    s = str(num_str).strip().lower().replace(',', '')
    unit = (unit or '').lower().strip()
    mult = 1
    if 'lakh' in unit or 'lac' in unit:
        mult = 100_000
    elif 'crore' in unit or unit == 'cr':
        mult = 10_000_000
    elif 'thousand' in unit:
        mult = 1_000
    try:
        return int(float(s) * mult)
    except Exception:
        return None


def parse_budget(msg):
    """Return (min_rupees, max_rupees) from QUERY_MESSAGE."""
    if not isinstance(msg, str):
        return (None, None)
    low = msg.lower()

    m = re.search(
        r'rs\.?\s*([\d,\.]+)\s*(?:to|-|–|—)\s*([\d,\.]+)\s*(lakh|lac|crore|cr|thousand)?',
        low,
    )
    if m:
        lo = _to_rupees(m.group(1), m.group(3) or '')
        hi = _to_rupees(m.group(2), m.group(3) or '')
        # sanity guard — cap at 10 Cr per query
        if lo is not None and lo > 100_000_000: lo = None
        if hi is not None and hi > 100_000_000: hi = None
        return (lo, hi)

    m = re.search(r'rs\.?\s*upto\s*([\d,\.]+)\s*(lakh|lac|crore|cr|thousand)?', low)
    if m:
        hi = _to_rupees(m.group(1), m.group(2) or '')
        if hi is not None and hi > 100_000_000: hi = None
        return (0, hi)

    return (None, None)


def parse_quantity(msg):
    """Return (qty_raw, unit, qty_in_kg)."""
    if not isinstance(msg, str):
        return (None, None, None)
    m = re.search(
        r'quantity\s*[:\-]\s*([\d,\.]+)\s*(kg|kilogram|tonne|ton|quintal|gram|gm|g|piece|pcs|pc|bag|packet|litre|liter|l|ml)?',
        msg,
        re.I,
    )
    if not m:
        return (None, None, None)
    try:
        qty = float(m.group(1).replace(',', ''))
    except Exception:
        return (None, (m.group(2) or '').lower(), None)
    unit = (m.group(2) or 'kg').lower().strip()
    if unit in ('kg', 'kilogram'):
        kg = qty
    elif unit in ('tonne', 'ton'):
        kg = qty * 1000
    elif unit == 'quintal':
        kg = qty * 100
    elif unit in ('gram', 'gm', 'g'):
        kg = qty / 1000
    elif unit in ('litre', 'liter', 'l'):
        kg = qty
    elif unit == 'ml':
        kg = qty / 1000
    else:
        kg = None
    # cap at 1000 tonne per query (outlier protection)
    if kg is not None and kg > 1_000_000:
        kg = None
    return (qty, unit, kg)


def parse_req_type(msg):
    if not isinstance(msg, str):
        return None
    if re.search(r'business\s*use', msg, re.I):
        return 'Business'
    if re.search(r'personal\s*use', msg, re.I):
        return 'Personal'
    return None


def parse_frequency(msg):
    if not isinstance(msg, str):
        return None
    patterns = [
        (r'monthly', 'Monthly'),
        (r'quarterly', 'Quarterly'),
        (r'half\s*[-]?\s*yearly', 'Half-Yearly'),
        (r'annual|yearly', 'Annual'),
        (r'one[\s-]*time', 'One-Time'),
        (r'sample', 'Sample'),
    ]
    for pat, label in patterns:
        if re.search(pat, msg, re.I):
            return label
    return None


def parse_form(msg):
    if not isinstance(msg, str):
        return None
    m = re.search(
        r'form\s*[:\-]\s*(powder|liquid|granule|granules|pellet|solid|tablet|crystal)',
        msg,
        re.I,
    )
    if m:
        val = m.group(1).lower()
        if val == 'granule':
            val = 'granules'
        return val.capitalize()
    return None


def parse_crops(msg):
    if not isinstance(msg, str):
        return []
    low = msg.lower()
    found = [c for c in CROP_KEYWORDS if re.search(rf'\b{c}s?\b', low)]
    return sorted(set(found))


def budget_tier(v):
    if v is None or pd.isna(v):
        return 'Unknown'
    if v >= 500_000:
        return 'Enterprise (5L+)'
    if v >= 100_000:
        return 'Large (1-5L)'
    if v >= 25_000:
        return 'Mid (25k-1L)'
    if v >= 5_000:
        return 'Small (5-25k)'
    return 'Micro (<5k)'


BUDGET_TIER_ORDER = [
    'Enterprise (5L+)', 'Large (1-5L)', 'Mid (25k-1L)',
    'Small (5-25k)', 'Micro (<5k)', 'Unknown',
]


def score_row(row):
    """Composite lead score (0-110)."""
    s = 0
    ch = row.get('QUERY_TYPE', '')
    if ch in ('B', 'BIZ'):
        s += 30
    elif ch == 'P':
        s += 25
    elif ch in ('W', 'WA'):
        s += 10
    elif ch == 'V':
        s += 20

    b = row.get('BUDGET_AVG')
    if b is not None and not pd.isna(b):
        if b >= 100_000:   s += 30
        elif b >= 25_000:  s += 20
        elif b >= 5_000:   s += 10

    q = row.get('QTY_KG')
    if q is not None and not pd.isna(q):
        if q >= 1000: s += 20
        elif q >= 100: s += 10
        elif q >= 10:  s += 5

    if row.get('REQ_TYPE') == 'Business':
        s += 10
    if row.get('FREQUENCY') in ('Monthly', 'Quarterly', 'Annual', 'Half-Yearly'):
        s += 10
    if pd.notna(row.get('SENDER_EMAIL')) and row.get('SENDER_EMAIL'):
        s += 5
    if pd.notna(row.get('SENDER_COMPANY')) and row.get('SENDER_COMPANY'):
        s += 5
    return s


def lead_tier(score):
    if score >= 60: return 'Hot'
    if score >= 35: return 'Warm'
    return 'Cold'


def load_and_enrich(source):
    """Load CSV/Excel and enrich with parsed fields + lead scores."""
    name = ''
    if hasattr(source, 'name'):
        name = source.name.lower()
    elif isinstance(source, str):
        name = source.lower()

    if name.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(source)
    else:
        df = pd.read_csv(source, low_memory=False)

    # drop unnamed / empty columns
    df = df.dropna(axis=1, how='all')
    df = df.loc[:, ~df.columns.astype(str).str.startswith('Unnamed')]
    df.columns = [c.strip() for c in df.columns]

    if 'QUERY_TIME' in df.columns:
        df['QUERY_TIME'] = pd.to_datetime(df['QUERY_TIME'], errors='coerce')
        df = df[df['QUERY_TIME'].notna()].copy()
        df['QUERY_DATE']  = df['QUERY_TIME'].dt.date
        df['QUERY_MONTH'] = df['QUERY_TIME'].dt.to_period('M').astype(str)
        df['QUERY_QTR']   = df['QUERY_TIME'].dt.to_period('Q').astype(str)
        df['QUERY_HOUR']  = df['QUERY_TIME'].dt.hour
        df['QUERY_DOW']   = df['QUERY_TIME'].dt.day_name()
        df['QUERY_WEEK']  = df['QUERY_TIME'].dt.to_period('W').astype(str)
        df['QUERY_YEAR']  = df['QUERY_TIME'].dt.year

    if 'QUERY_TYPE' in df.columns:
        df['CHANNEL'] = df['QUERY_TYPE'].map(QUERY_TYPE_LABELS).fillna(df['QUERY_TYPE'].fillna('Unknown'))

    if 'QUERY_MESSAGE' in df.columns:
        msgs = df['QUERY_MESSAGE'].fillna('')
        budgets = msgs.apply(parse_budget)
        df['BUDGET_MIN'] = budgets.apply(lambda x: x[0])
        df['BUDGET_MAX'] = budgets.apply(lambda x: x[1])
        df['BUDGET_AVG'] = df[['BUDGET_MIN', 'BUDGET_MAX']].mean(axis=1)
        df['BUDGET_TIER'] = df['BUDGET_AVG'].apply(budget_tier)

        qties = msgs.apply(parse_quantity)
        df['QTY_RAW']  = qties.apply(lambda x: x[0])
        df['QTY_UNIT'] = qties.apply(lambda x: x[1])
        df['QTY_KG']   = qties.apply(lambda x: x[2])

        df['REQ_TYPE']  = msgs.apply(parse_req_type)
        df['FREQUENCY'] = msgs.apply(parse_frequency)
        df['FORM']      = msgs.apply(parse_form)
        df['CROPS']     = msgs.apply(parse_crops)

    df['LEAD_SCORE'] = df.apply(score_row, axis=1)
    df['LEAD_TIER']  = df['LEAD_SCORE'].apply(lead_tier)

    df = flag_spam(df)

    return df


def period_compare(df, date_col='QUERY_TIME', days=30):
    """Returns (current_period_df, previous_period_df) of equal length."""
    if date_col not in df.columns or df[date_col].isna().all():
        return df.iloc[0:0], df.iloc[0:0]
    mx = df[date_col].max()
    cur_start = mx - pd.Timedelta(days=days)
    prev_start = mx - pd.Timedelta(days=days * 2)
    cur = df[df[date_col] > cur_start]
    prev = df[(df[date_col] > prev_start) & (df[date_col] <= cur_start)]
    return cur, prev


def build_prospect_master(df):
    """Dedupe by phone, aggregate stats per prospect."""
    if 'SENDER_MOBILE' not in df.columns or len(df) == 0:
        return pd.DataFrame()

    d = df[df['SENDER_MOBILE'].notna() & (df['SENDER_MOBILE'].astype(str).str.strip() != '')].copy()
    if len(d) == 0:
        return pd.DataFrame()

    g = d.groupby('SENDER_MOBILE', dropna=False)
    idx = list(g.groups.keys())
    master = pd.DataFrame(index=idx)
    master.index.name = 'phone'

    if 'SENDER_NAME' in d.columns:    master['name']    = g['SENDER_NAME'].first()
    if 'SENDER_EMAIL' in d.columns:   master['email']   = g['SENDER_EMAIL'].first()
    if 'SENDER_COMPANY' in d.columns: master['company'] = g['SENDER_COMPANY'].first()
    if 'SENDER_CITY' in d.columns:    master['city']    = g['SENDER_CITY'].first()
    if 'SENDER_STATE' in d.columns:   master['state']   = g['SENDER_STATE'].first()

    master['total_queries']  = g.size()
    if 'QUERY_TIME' in d.columns:
        master['first_query'] = g['QUERY_TIME'].min()
        master['last_query']  = g['QUERY_TIME'].max()
    if 'QUERY_MCAT_NAME' in d.columns:
        master['top_product'] = g['QUERY_MCAT_NAME'].agg(
            lambda x: x.dropna().mode().iat[0] if not x.dropna().mode().empty else None
        )
        master['products_queried'] = g['QUERY_MCAT_NAME'].nunique()
    if 'BUDGET_AVG' in d.columns:
        master['avg_budget']   = g['BUDGET_AVG'].mean()
    if 'QTY_KG' in d.columns:
        master['max_qty_kg']   = g['QTY_KG'].max()
    master['best_score']       = g['LEAD_SCORE'].max()

    master = master.reset_index()

    if 'last_query' in master.columns and master['last_query'].notna().any():
        # anchor to the data's max date, not wall-clock today
        reference = master['last_query'].max()
        master['days_since_last'] = (reference - master['last_query']).dt.days

    master['tier'] = master['best_score'].apply(lead_tier)

    # RFM-style segment (anchored to latest query date in data)
    if 'days_since_last' in master.columns and 'total_queries' in master.columns:
        def segment(r):
            d = r.get('days_since_last', 999) or 999
            q = r.get('total_queries', 1) or 1
            if d <= 30 and q >= 3: return 'Champions'
            if d <= 30 and q == 1: return 'New'
            if d <= 90: return 'Active'
            if d <= 180: return 'Slipping'
            return 'Dormant'
        master['segment'] = master.apply(segment, axis=1)

    return master.sort_values('best_score', ascending=False)
