
import os
import re
import json
import smtplib
import requests
import feedparser
import pandas as pd
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

_scheduler: Optional[BackgroundScheduler] = None

def _cache_path(name:str) -> str:
    return os.path.join(CACHE_DIR, name)

def _save_json(obj, name):
    with open(_cache_path(name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _load_json(name):
    p = _cache_path(name)
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _is_stale(p:str, minutes:int) -> bool:
    if not os.path.exists(p):
        return True
    mtime = datetime.fromtimestamp(os.path.getmtime(p), tz=timezone.utc)
    return datetime.now(timezone.utc) - mtime > timedelta(minutes=minutes)

# ---------------- Email list management ----------------
EMAIL_FILE = "email_recipients.json"

def _valid_email(addr: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", addr or ""))

def add_email_recipient(addr: str):
    if not _valid_email(addr):
        return False, "邮箱格式不正确"
    lst = list_email_recipients()
    if addr in lst:
        return True, "已订阅"
    lst.append(addr)
    _save_json(lst, EMAIL_FILE)
    return True, "OK"

def list_email_recipients() -> List[str]:
    data = _load_json(EMAIL_FILE)
    return data if isinstance(data, list) else []

# ---------------- Translation (DeepL optional) ----------------
def translate_to_zh(text: str) -> str:
    # If DEEPL_API_KEY set, translate en->zh
    key = os.getenv("DEEPL_API_KEY")
    if not key or not text:
        return text
    try:
        url = "https://api-free.deepl.com/v2/translate"
        data = {"auth_key": key, "text": text, "target_lang": "ZH"}
        r = requests.post(url, data=data, timeout=20)
        r.raise_for_status()
        j = r.json()
        return j["translations"][0]["text"]
    except Exception:
        return text

# ---------------- Data sources ----------------
def _wb(series, country):
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/{series}?format=json&per_page=5"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 2:
        return None
    values = [x for x in data[1] if x.get("value") is not None]
    if not values:
        return None
    values.sort(key=lambda x: x.get("date",""))
    latest = values[-1]
    return float(latest["value"]), latest["date"]

def _yahoo_levels(tickers: Dict[str,str]) -> Dict[str, Dict[str, float]]:
    out = {}
    for label, symbol in tickers.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
            j = requests.get(url, timeout=20).json()
            res = j["chart"]["result"][0]
            closes = res["indicators"]["quote"][0]["close"]
            if closes and len(closes) >= 2:
                last = closes[-1]; prev = closes[-2]
                if last is None or prev is None:
                    raise ValueError("None close")
                chg = (last/prev - 1.0) * 100.0
                out[label] = {"level": float(last), "change_pct": float(chg)}
        except Exception:
            out[label] = {"level": None, "change_pct": None}
    return out

def _te(path:str, params=None):
    key = os.getenv("TE_API_CLIENT_KEY")
    secret = os.getenv("TE_API_CLIENT_SECRET")
    if not key or not secret:
        raise RuntimeError("TradingEconomics API keys not provided.")
    url = f"https://api.tradingeconomics.com/{path}"
    params = params or {}
    params.update({"client": key, "secret": secret, "format":"json"})
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    return r.json()

def fetch_macro_snapshot() -> Dict[str, Any]:
    out = {"CN":{}, "US":{}, "EU":{}}
    mapping = {"CN":"CHN", "US":"USA", "EU":"EUU"}
    for k, wb_code in mapping.items():
        try:
            gdp, _ = _wb("NY.GDP.MKTP.KD.ZG", wb_code)
        except Exception:
            gdp = None
        try:
            cpi, _ = _wb("FP.CPI.TOTL.ZG", wb_code)
        except Exception:
            cpi = None
        ppi = None; policy = None
        try:
            te_ppi = _te(f"indicators/ppi?country={k}")
            if isinstance(te_ppi, list) and te_ppi:
                v = te_ppi[0].get("LatestValue")
                if v is not None: ppi = float(v)
        except Exception:
            pass
        try:
            if k == "US":
                te_rate = _te("federal_funds_rate")
            else:
                te_rate = _te(f"policy_rate/{k}")
            if isinstance(te_rate, list) and te_rate:
                v = te_rate[0].get("LatestValue") or te_rate[0].get("Value")
                if v is not None: policy = float(v)
        except Exception:
            pass
        out[k] = {"gdp_yoy": gdp, "cpi_yoy": cpi, "ppi_yoy": ppi, "policy_rate": policy}
    return out

def fetch_bonds_snapshot() -> Dict[str, Any]:
    out = {"CN":{}, "US":{}, "EU":{}}
    try:
        data = _te("bonds/major")
        by_ccy = {"US":"United States","CN":"China","EU":"Germany"}
        tenors = {"1y":"1Y","5y":"5Y","10y":"10Y"}
        for k, cname in by_ccy.items():
            out[k] = {}
            for key, te_tenor in tenors.items():
                recs = [x for x in data if x.get("Country")==cname and x.get("Group")==te_tenor]
                if recs:
                    v = recs[0].get("Last")
                    chg = recs[0].get("DailyChange")
                    out[k][key] = {"value": float(v) if v is not None else None,
                                   "change_bp": float(chg)*100 if chg is not None else None}
    except Exception:
        # Fallback for US only via Yahoo
        out["US"] = {"1y":{"value":None,"change_bp":None},
                     "5y":{"value":None,"change_bp":None},
                     "10y":{"value":None,"change_bp":None}}
        try:
            j = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/^TNX?range=5d&interval=1d", timeout=20).json()
            closes = j["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            if closes and len(closes) >= 2 and closes[-1] is not None:
                last = closes[-1]/10.0; prev = (closes[-2] or last)/10.0
                out["US"]["10y"] = {"value": last, "change_bp": (last-prev)*100}
        except Exception:
            pass
        try:
            j = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/^FVX?range=5d&interval=1d", timeout=20).json()
            closes = j["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            if closes and len(closes) >= 2 and closes[-1] is not None:
                last = closes[-1]/10.0; prev = (closes[-2] or last)/10.0
                out["US"]["5y"] = {"value": last, "change_bp": (last-prev)*100}
        except Exception:
            pass
    return out

def fetch_stocks_snapshot() -> Dict[str, Any]:
    cn = _yahoo_levels({"mkt1":"000001.SS", "mkt2":"399001.SZ"})
    us = _yahoo_levels({"mkt1":"^GSPC", "mkt2":"^IXIC"})
    eu = _yahoo_levels({"mkt1":"^FTSE", "mkt2":"^GDAXI"})
    return {"CN": cn, "US": us, "EU": eu}

def fetch_news_items(limit:int=30) -> List[Dict[str,Any]]:
    feeds = [
        ("新华社", "http://www.xinhuanet.com/english/rss/businessrss.xml"),
        ("路透", "https://feeds.reuters.com/reuters/businessNews"),
        ("人民银行", "http://www.pbc.gov.cn/english/130721/rss.xml"),
        ("国家统计局", "http://www.stats.gov.cn/english/rss.xml"),
        ("ECB", "https://www.ecb.europa.eu/press/press.rss"),
        ("FED", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ]
    cn_like = {"新华社","人民银行","国家统计局"}  # do not translate
    items = []
    for source, url in feeds:
        try:
            d = feedparser.parse(url)
            for e in d.entries[:10]:
                title = e.get("title","") or ""
                summary = e.get("summary","") or ""
                pub_time = e.get("published","")[:19]
                link = e.get("link","")
                # Auto-translate non-CN sources if key available
                if source not in cn_like:
                    title = translate_to_zh(title)
                    summary = translate_to_zh(summary[:500])
                items.append({
                    "source": source,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "pub_time": pub_time
                })
        except Exception:
            continue
    # Deduplicate by title
    seen = set(); uniq = []
    for it in items:
        t = it["title"]
        if t and t not in seen:
            seen.add(t); uniq.append(it)
    return uniq[:limit]

# ---------------- Orchestration & scheduler ----------------
def load_cached_macro_snapshot() -> Dict[str, Any]: return _load_json("macro_snapshot.json") or {}
def load_cached_time_series() -> pd.DataFrame:
    p = _cache_path("macro_history.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
def load_cached_stocks_snapshot() -> Dict[str, Any]: return _load_json("stocks_snapshot.json") or {}
def load_cached_bonds_snapshot() -> Dict[str, Any]: return _load_json("bonds_snapshot.json") or {}
def load_cached_news_items() -> List[Dict[str, Any]]: return _load_json("news_items.json") or []

def refresh_all_data(force_if_stale_minutes:int=60):
    if _is_stale(_cache_path("macro_snapshot.json"), force_if_stale_minutes):
        _save_json(fetch_macro_snapshot(), "macro_snapshot.json")
    if _is_stale(_cache_path("bonds_snapshot.json"), force_if_stale_minutes):
        _save_json(fetch_bonds_snapshot(), "bonds_snapshot.json")
    if _is_stale(_cache_path("stocks_snapshot.json"), 20):
        _save_json(fetch_stocks_snapshot(), "stocks_snapshot.json")
    if _is_stale(_cache_path("news_items.json"), 30):
        _save_json(fetch_news_items(), "news_items.json")
    # CPI history (yearly) refresh ~ monthly
    if _is_stale(_cache_path("macro_history.csv"), 720):
        series = {"CN":"CHN","US":"USA","EU":"EUU"}
        frames = []
        for k, wb in series.items():
            try:
                url = f"https://api.worldbank.org/v2/country/{wb}/indicator/FP.CPI.TOTL.ZG?format=json&per_page=200"
                r = requests.get(url, timeout=25).json()
                vals = r[1]
                df = pd.DataFrame([{"date": int(v["date"]), f"{k}-CPI": v["value"]} for v in vals])
                frames.append(df)
            except Exception:
                pass
        if frames:
            out = frames[0]
            for f in frames[1:]:
                out = pd.merge(out, f, on="date", how="outer")
            out = out.sort_values("date")
            out.to_csv(_cache_path("macro_history.csv"), index=False)

# ---------------- Email sending ----------------
def _send_via_sendgrid(to_list: List[str], subject: str, html_body: str) -> int:
    key = os.getenv("SENDGRID_API_KEY")
    sender = os.getenv("EMAIL_SENDER")  # e.g., no-reply@yourdomain.com
    if not key or not sender:
        return 0
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Email, To, Content
        sg = sendgrid.SendGridAPIClient(api_key=key)
        sent = 0
        for to in to_list:
            message = Mail(from_email=Email(sender),
                           to_emails=To(to),
                           subject=subject,
                           html_content=html_body)
            resp = sg.client.mail.send.post(request_body=message.get())
            if 200 <= resp.status_code < 300:
                sent += 1
        return sent
    except Exception:
        return 0

def _send_via_smtp(to_list: List[str], subject: str, html_body: str) -> int:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT","587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    sender = os.getenv("EMAIL_SENDER") or user
    if not (host and user and pwd and sender):
        return 0
    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = formataddr(("Macro Dashboard", sender))
    msg["Subject"] = subject
    sent = 0
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, pwd)
            for to in to_list:
                msg["To"] = to
                s.sendmail(sender, [to], msg.as_string())
                sent += 1
    except Exception:
        return 0
    return sent

def send_daily_email_summary() -> int:
    to_list = list_email_recipients()
    if not to_list:
        return 0
    macro = load_cached_macro_snapshot()
    stocks = load_cached_stocks_snapshot()
    bonds = load_cached_bonds_snapshot()
    news = load_cached_news_items()[:8]
    def fmt_macro(k, name):
        b = macro.get(k, {})
        return f"<b>{name}</b> GDP:{b.get('gdp_yoy','—')} CPI:{b.get('cpi_yoy','—')} PPI:{b.get('ppi_yoy','—')} Rate:{b.get('policy_rate','—')}"
    html_body = "<h3>每日宏观与金融摘要</h3>" + \
        "<p>" + "<br>".join([fmt_macro("CN","中国"), fmt_macro("US","美国"), fmt_macro("EU","欧盟")]) + "</p>" + \
        "<h4>新闻</h4><ul>" + "".join([f"<li>{i.get('source','')}: <a href='{i.get('link','#')}'>{i.get('title','')}</a></li>" for i in news]) + "</ul>" + \
        f"<p style='color:#888;'>发送时间：{datetime.utcnow().isoformat()}Z</p>"
    subject = "每日宏观与金融摘要"
    sent = _send_via_sendgrid(to_list, subject, html_body)
    if sent == 0:
        sent = _send_via_smtp(to_list, subject, html_body)
    return sent

# ------------- Scheduler init -------------
def ensure_scheduler_started():
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    # Every day at 08:00 China time
    _scheduler.add_job(lambda: (refresh_all_data(force_if_stale_minutes=0), send_daily_email_summary()),
                       CronTrigger(hour=8, minute=0))
    _scheduler.start()
