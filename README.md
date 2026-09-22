# 策略指引平台

只读展示策略日表的 Streamlit Cloud 部署版本。页面仅使用 `site/site-data.json` 中的精简展示数据；本机保存的腾讯文档原始响应、审计文件及会话痕迹不会上传。

## 部署

1. 在 Streamlit Community Cloud 选择本仓库的 `main` 分支，入口文件为 `app.py`。
2. GitHub Actions 会在北京时间每日 08:00、18:00 检查共享表并自动提交 `site/site-data.json` 的更新；也可在 Actions 页面手动运行“更新策略日表”。
3. Streamlit Cloud 发现 `main` 分支的新提交后会自动重新部署。

部署后提供三个入口（同一个 Streamlit 应用）：

- `/`：红白配色的新版 prototype，作为主站；
- `/prototype`：prototype v0 历史存档；
- `/new`：当前绿色版网站。

三个入口共用同一份精简数据底稿；主站和两个子站的搜索、日历与历史浏览均在浏览器内完成。

## 本地运行

```powershell
C:\Users\chris\AppData\Local\Programs\Python\Python313\python.exe -m streamlit run app.py
```

本机需要保留访问级更新、原始审计存档与即时定时任务时，仍使用 `启动策略指引平台.bat`。
