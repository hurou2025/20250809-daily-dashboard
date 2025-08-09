# 每日宏观与金融监测面板（Dash）— 带 08:00 定时刷新、邮件推送与DeepL翻译

功能：
- 中国/美国/欧盟：GDP同比、CPI同比、（可选）PPI同比、政策利率
- 主要股指：上证综指/深证成指、标普500/纳斯达克、富时100/德国DAX（日变动）
- 主要国债收益率：1Y/5Y/10Y（TradingEconomics 有key时全量；无key时提供美国回退）
- 重点新闻：新华社、路透、央行、统计局、ECB、FED（RSS）；自动翻译非中文来源（DeepL 可选）
- **08:00（Asia/Shanghai）自动刷新 + 邮件摘要推送**（APScheduler），并提供 **/cron** 路由用于 Render Cron Job 或手动触发
- 页面底部提供 **邮箱订阅表单**；邮箱存储在服务器 `cache/email_recipients.json`

## 快速部署（Render / Python 服务）
1. 新建 GitHub 仓库，推送本项目所有文件（根目录包含 `app.py`、`requirements.txt`、`render.yaml`）。
2. Render → New → Web Service → 选择该仓库；环境选 **Python**。
3. 部署前，在 **Environment** 设置以下变量（可按需）：
   - `TE_API_CLIENT_KEY`, `TE_API_CLIENT_SECRET`（TradingEconomics）
   - `DEEPL_API_KEY`（DeepL 翻译）
   - 邮件二选一：
     - **SendGrid**：`SENDGRID_API_KEY` + `EMAIL_SENDER`
     - **SMTP**：`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_SENDER`
4. 部署完成后，访问站点底部即可输入邮箱订阅。

## Cron（可选，双重保障）
- 应用内部已启用 APScheduler，每日 08:00 自动刷新与推送（服务器时区：Asia/Shanghai）。
- 你还可以在 Render 新建 **Cron Job**，每日 08:02 GET 调用 `/cron`，即使 Web Dyno 重启也能触发。

## 本地运行
```bash
python -m venv .venv && source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
生成时间：2025-08-09T14:40:57.475389Z
