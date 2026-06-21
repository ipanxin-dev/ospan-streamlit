# 中文 A-OSPAN Streamlit 部署版

这是一个中文 Automated Operation Span Task（A-OSPAN）Streamlit 应用。它可以本地运行，也可以部署到 Streamlit Community Cloud 后发给学生远程完成。

## 功能

- 首页填写姓名、学号，阅读简介和伦理说明
- 字母记忆练习
- 数学判断练习，并在后台计算个人数学作答时间上限
- 双任务整合练习
- 正式实验：set size 3-7，每个 set size 3 个 set，共 75 道数学题和 75 个字母
- 输出 OSPAN score、Total correct、Math errors、Speed errors、Accuracy errors
- 保存 trial-level CSV / JSON
- 可选：自动同步到 Google Sheets，集中收集所有学生数据

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器会自动打开本地页面；如果没有自动打开，请访问终端里显示的 `http://localhost:8501`。

## 数据输出

完成后会生成：

- `data/*_trials.csv`
- `data/*_trials.json`
- `data/*_summary.json`

如果配置了 Google Apps Script 收数 URL，应用还会自动写入两个工作表：

- `trials`：trial-level 数据
- `summary`：每名学生一行的总分数据

## GitHub + Streamlit Cloud 部署

1. 在 GitHub 创建一个仓库，例如 `ospan-streamlit`。
2. 把本文件夹内所有文件推送到仓库。
3. 打开 Streamlit Community Cloud，新建 app。
4. 选择这个 GitHub 仓库，主文件填写 `app.py`。
5. 部署完成后，把 Streamlit 生成的网址发给学生。

学生只需要打开网址完成任务，不需要安装 Python，也不需要访问 GitHub 仓库。

## 配置 Google Sheets 收集数据（不需要 Google Cloud 付款方式）

1. 新建一个 Google Sheet，用于收集数据。
2. 在 Google Sheet 中打开 Extensions -> Apps Script。
3. 删除默认内容，把 `google_apps_script.gs` 的全部内容粘进去。
4. 保存脚本。
5. 点 Deploy -> New deployment。
6. 类型选择 Web app。
7. Execute as 选择 Me。
8. Who has access 选择 Anyone。
9. 点 Deploy，并授权。
10. 复制 Web app URL。
11. 在 Streamlit Cloud 的 App settings -> Secrets 中粘贴配置。

Secrets 模板见：

```text
.streamlit/secrets.toml.example
```

最少需要：

```toml
google_sheet_id = "你的 Google Sheet ID"
apps_script_webhook_url = "你的 Apps Script Web app URL"
```

## 发给学生的话术

请打开以下链接完成“记忆与注意力任务”。开始前请填写姓名和学号。任务约 20-25 分钟，请在安静环境中一次性完成，中途不要刷新或关闭页面。
