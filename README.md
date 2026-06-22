# A-OSPAN jsPsych / Streamlit 部署版

这是一个中文 Automated Operation Span Task（A-OSPAN）项目。正式收数建议使用 `docs/` 里的 jsPsych 静态网页版本；原 Streamlit 应用仍保留为本地预览和备份。

jsPsych 版本更适合涉及反应时的研究，因为刺激呈现、按键记录和 trial 时间控制主要发生在被试自己的浏览器里，不依赖 Streamlit 的服务端 rerun。

## 功能

- 首页填写姓名、学号，阅读简介和伦理说明
- 字母记忆练习
- 数学判断练习，并在后台计算个人数学作答时间上限
- 双任务整合练习
- 正式实验：set size 3-7，每个 set size 3 个 set，共 75 道数学题和 75 个字母
- 输出 OSPAN score、Total correct、Math errors、Speed errors、Accuracy errors
- 保存 trial-level CSV / JSON
- 可选：自动同步到 Google Sheets，集中收集所有学生数据

## 推荐部署：GitHub Pages + jsPsych

本仓库的 `docs/` 目录是静态 jsPsych 实验页，可以直接用 GitHub Pages 发布。

1. 打开 GitHub 仓库 Settings。
2. 进入 Pages。
3. Source 选择 Deploy from a branch。
4. Branch 选择 `main`，Folder 选择 `/docs`。
5. 保存后等待 GitHub 生成 Pages 链接。

发布后，学生只需要打开 GitHub Pages 链接完成任务。结束时数据会通过 Google Apps Script 写入 Google Sheet。

jsPsych 版已内置当前 Google Apps Script Web App URL：

```text
https://script.google.com/macros/s/AKfycbzX8-SBD26liMvlSB0uci0coLEydmJU9VFwpIwpdp8yG0cmy3v0tOVKHnvVmFvbHqeL6Q/exec
```

如果以后重新部署 Apps Script，需要同步修改：

```text
docs/experiment.js
```

## 本地运行

### jsPsych 静态版

```bash
cd docs
python3 -m http.server 8765
```

然后打开：

```text
http://localhost:8765/
```

### Streamlit 备用版

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

## 备用部署：Streamlit Cloud

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
