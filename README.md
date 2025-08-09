Here’s a **Render-ready README.md** you can put in your GitHub repo.
I’ve kept it clear, deployment-focused, and fully aligned with the `macro_dashboard_repo_v2` code so Render won’t complain.

---

````markdown
# 每日宏观与金融监测面板（Dash）

## 功能亮点
- **国家覆盖**：中国 / 美国 / 欧盟
- **宏观数据**：GDP同比、CPI同比、（可选）PPI同比、政策利率
- **金融市场**：
  - 主要股指：上证综指 / 深证成指、标普500 / 纳斯达克、富时100 / 德国DAX（含日涨跌幅）
  - 国债收益率：1年 / 5年 / 10年（TradingEconomics API 有 Key 时全量；无 Key 时部分回退）
- **新闻聚合**：新华社、路透社、央行、国家统计局、ECB、FED（RSS）
  - 可选：自动翻译非中文新闻（DeepL API）
- **自动化**：
  - 每日 **08:00 (Asia/Shanghai)** 自动刷新数据并推送邮件摘要（APScheduler）
  - 页面底部可直接输入邮箱进行订阅
  - 提供 `/cron` 路由，可手动触发或结合 Render Cron Job

---

## 本地运行
```bash
# 创建虚拟环境
python -m venv .venv
# 激活虚拟环境（Windows 用 .venv\Scripts\activate）
source .venv/bin/activate
# 安装依赖
pip install -r requirements.txt
# 启动服务
python app.py
````

默认在 `http://127.0.0.1:8050` 打开。

---

## 部署到 Render（推荐）

1. 新建一个 **公开/私有 GitHub 仓库**，将本项目所有文件推送到仓库根目录（必须包含 `app.py`、`requirements.txt`、`render.yaml`）。
2. 在 Render 仪表盘点击 **New + → Web Service**，连接该 GitHub 仓库。
3. 环境类型选择 **Python**（不要选 Docker）。
4. Render 会自动读取 `render.yaml` 配置：

   * Build: `pip install -r requirements.txt`
   * Start: `gunicorn app:server`
5. **配置环境变量（按需）**：

   * TradingEconomics 数据：`TE_API_CLIENT_KEY`、`TE_API_CLIENT_SECRET`
   * DeepL 翻译：`DEEPL_API_KEY`
   * 邮件发送（任选一种）：

     * **SendGrid**：`SENDGRID_API_KEY`、`EMAIL_SENDER`
     * **SMTP**：`SMTP_HOST`、`SMTP_PORT`、`SMTP_USER`、`SMTP_PASS`、`EMAIL_SENDER`
6. 部署完成后访问你的 Render 服务 URL，即可使用。

---

## 邮件推送说明

* 应用会在每天 **08:00 (Asia/Shanghai)** 自动刷新数据并推送当日摘要到订阅邮箱。
* 也可通过访问 `/cron` 手动触发刷新+推送（建议配合 Render Cron Job 作为备用触发）。

---

## 数据来源

* 宏观指标：世界银行 API（免费）+ TradingEconomics API（可选，需 Key）
* 股指 & 美债：Yahoo Finance Chart API（免费）
* 新闻：RSS（新华社、路透、央行、统计局、ECB、FED）
* 翻译（可选）：DeepL API

---

## 目录结构

```
.
├── app.py                  # 主入口
├── modules/
│   ├── data_fetch.py       # 数据抓取、缓存、调度、邮件推送
│   └── utils.py            # UI 辅助函数
├── cache/                  # 数据缓存与订阅邮箱列表
├── requirements.txt        # Python 依赖
├── render.yaml             # Render 部署配置
├── Procfile                # Gunicorn 启动命令
├── Dockerfile              # 可选：Docker 部署
└── README.md               # 项目说明
```

---

**提示**：首次部署后建议先手动访问 `/cron` 来测试数据刷新与邮件推送是否正常。

```

---

Do you want me to **drop this README.md into the repo zip** so your GitHub push is ready to go without changes? That way Render will immediately detect it.
```
