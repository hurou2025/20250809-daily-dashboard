
import os
import json
import pandas as pd
from datetime import datetime
from dash import Dash, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px

from modules.data_fetch import (
    refresh_all_data,
    load_cached_macro_snapshot,
    load_cached_time_series,
    load_cached_stocks_snapshot,
    load_cached_bonds_snapshot,
    load_cached_news_items,
    add_email_recipient,
    list_email_recipients,
    send_daily_email_summary,
    ensure_scheduler_started,
)
from modules.utils import create_card, pct_fmt, bp_fmt

APP_TITLE = "每日宏观与金融监测面板"
APP_SUB = "中国 / 美国 / 欧盟｜主要宏观指标、股指、国债收益率与重点新闻（自动每日 08:00 刷新 + 邮件推送）"

external_stylesheets = [dbc.themes.BOOTSTRAP]
app = Dash(__name__, external_stylesheets=external_stylesheets, title=APP_TITLE, suppress_callback_exceptions=True)
server = app.server

# Start scheduler once (08:00 Asia/Shanghai by default)
ensure_scheduler_started()

# Initial data
try:
    refresh_all_data(force_if_stale_minutes=180)
except Exception as e:
    print("Warmup refresh failed:", e)

def load_all():
    return (
        load_cached_macro_snapshot(),
        load_cached_stocks_snapshot(),
        load_cached_bonds_snapshot(),
        load_cached_news_items(),
        load_cached_time_series()
    )

macro, stocks, bonds, news_items, hist = load_all()

# ----- UI builders -----
def macro_row(country_key, title_cn):
    block = macro.get(country_key, {})
    items = []
    for label, key in [("GDP增速(同比,%)", "gdp_yoy"),
                       ("CPI(同比,%)", "cpi_yoy"),
                       ("PPI(同比,%)", "ppi_yoy"),
                       ("政策利率(%)", "policy_rate")]:
        v = block.get(key, None)
        items.append((label, None if v is None else f"{v:.2f}"))
    return dbc.Col(create_card(title_cn, dict(items)), md=4, xs=12)

def bonds_row(country_key, title_cn):
    block = bonds.get(country_key, {})
    items = []
    for label, k in [("1Y", "1y"), ("5Y", "5y"), ("10Y", "10y")]:
        v = block.get(k, {})
        val = v.get("value")
        chg = v.get("change_bp")
        s = None
        if val is not None:
            s = f"{val:.2f}%"
            if chg is not None:
                s += f" ({bp_fmt(chg)})"
        items.append((label, s))
    return dbc.Col(create_card(f"{title_cn} 国债收益率", dict(items)), md=4, xs=12)

def stocks_row(country_key, title_cn):
    block = stocks.get(country_key, {})
    items = []
    for label, k in [("市场A", "mkt1"), ("市场B", "mkt2")]:
        v = block.get(k, {})
        lvl = v.get("level")
        chg = v.get("change_pct")
        s = None
        if lvl is not None:
            s = f"{lvl:,.0f}"
            if chg is not None:
                s += f" ({pct_fmt(chg)})"
        items.append((label, s))
    return dbc.Col(create_card(f"{title_cn} 主要股指", dict(items)), md=4, xs=12)

def cpi_chart():
    if hist is None or hist.empty:
        return html.Div("暂无历史数据")
    df = hist.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="%Y").dt.to_period("Y").dt.to_timestamp()
    melted = df.melt(id_vars=["date"], value_vars=[c for c in df.columns if c != "date"],
                     var_name="系列", value_name="数值")
    fig = px.line(melted, x="date", y="数值", color="系列", title="CPI同比（历史）")
    fig.update_layout(margin=dict(l=10,r=10,t=35,b=10), height=320)
    return dcc.Graph(figure=fig)

# --- Email subscribe form ---
email_form = dbc.Card(
    dbc.CardBody([
        html.H6("订阅每日邮件摘要（08:00 推送）"),
        dbc.Row([
            dbc.Col(dbc.Input(id="email-input", type="email", placeholder="输入你的邮箱，例如 name@example.com"), md=8, xs=12),
            dbc.Col(dbc.Button("订阅", id="email-submit", color="primary"), md=4, xs=12),
        ], className="gy-2"),
        html.Div(id="email-status", className="text-success mt-2"),
        html.Small("说明：邮箱列表仅保存在服务器缓存中；发送方需配置 SENDGRID 或 SMTP 环境变量。", className="text-muted")
    ]),
    className="shadow-sm"
)

@app.callback(
    Output("email-status", "children"),
    Input("email-submit", "n_clicks"),
    State("email-input", "value"),
    prevent_initial_call=True
)
def subscribe_email(n, value):
    if not value:
        return "请输入有效邮箱地址。"
    ok, msg = add_email_recipient(value)
    if ok:
        return f"订阅成功：{value}。当前订阅数：{len(list_email_recipients())}"
    else:
        return f"订阅失败：{msg}"

# Layout
app.layout = dbc.Container(
    [
        dbc.Row([dbc.Col(html.H2(APP_TITLE), md=8, xs=12),
                 dbc.Col(html.Div(APP_SUB, className="text-muted"), md=4, xs=12)],
                 className="mt-3 mb-2"),
        html.H4("首页概览"),
        dbc.Row([macro_row("CN","中国"), macro_row("US","美国"), macro_row("EU","欧盟")], className="gy-3"),
        html.Hr(),
        html.H4("主要债券"),
        dbc.Row([bonds_row("CN","中国"), bonds_row("US","美国"), bonds_row("EU","欧盟")], className="gy-3"),
        html.Hr(),
        html.H4("主要股指"),
        dbc.Row([stocks_row("CN","中国"), stocks_row("US","美国"), stocks_row("EU","欧盟")], className="gy-3"),
        html.Hr(),
        html.H4("趋势图"),
        cpi_chart(),
        html.Hr(),
        html.H4("重点新闻（自动翻译非中文来源）"),
        dbc.ListGroup([
            dbc.ListGroupItem(
                html.Div([
                    html.H6(item.get("title","无标题")),
                    html.Small(item.get("source",""), className="text-muted me-2"),
                    html.Small(item.get("pub_time",""), className="text-muted"),
                    html.P(item.get("summary",""), className="mt-2 mb-1"),
                    html.A("原文链接", href=item.get("link","#"), target="_blank")
                ])
            ) for item in (news_items or [])[:15]
        ]),
        html.Hr(),
        email_form,
        html.Div(className="mb-4")
    ],
    fluid=True
)

# ---- Flask routes for cron ----
@server.route("/cron")
def cron():
    try:
        refresh_all_data(force_if_stale_minutes=0)
        # After refresh, send email to subscribers
        sent = send_daily_email_summary()
        return f"Refreshed and email sent to {sent} recipients at {datetime.utcnow().isoformat()}Z\n", 200
    except Exception as e:
        return f"Error: {e}\n", 500

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=True)
