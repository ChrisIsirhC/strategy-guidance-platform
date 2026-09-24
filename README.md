# 策略指引平台

策略指引平台的 Streamlit 部署版本。每日原始策略观点仍从腾讯共享表格抓取；经理填写的策略案例与原始观点分层管理。配置 Supabase 后，草稿与发布案例保存在数据库中；未配置时仅在本地开发环境使用测试 JSON。

## 部署

1. 在 Streamlit Community Cloud 选择本仓库的 `main` 分支，入口文件为 `app.py`。
2. GitHub Actions 会在北京时间每日 08:00、18:00 检查共享表并自动提交 `site/site-data.json` 的更新；也可在 Actions 页面手动运行“更新策略日表”。
3. Streamlit Cloud 发现 `main` 分支的新提交后会自动重新部署。

部署后提供以下入口（同一个 Streamlit 应用）：

- `/`：红白配色的新版 prototype，作为主站；
- `/archive`：直接进入主站的历史回溯；主站内的今日／历史切换仍在当前页面完成；
- `/prototype`：prototype v0 历史存档；
- `/new`：当前绿色版网站。
- `/cases`：独立的策略案例页面，只展示已发布案例。
- `/admin`：策略案例后台。测试阶段用户名为 `test`，密码仅在本地或部署 Secrets 中配置，不提交至公开仓库。

主站和两个子站共用同一份精简数据底稿；案例不写回共享表格。共享表格快照由 GitHub Actions 提交 `site/site-data.json`、`data/cloud_history`、`data/cloud_sync_state.json` 到仓库，部署实例重启不会删除仓库里的快照。案例测试 JSON 被 `.gitignore` 忽略，**不会自动提交到 GitHub**；未配置 Supabase 时，线上保存／发布按钮禁用，避免云端临时文件造成假成功。后台测试账号密码从 Streamlit Secrets 读取，不存放在仓库代码中。

## 案例后台首次配置

1. 复制 `.streamlit/secrets.example.toml` 为 `.streamlit/secrets.toml`，填入测试密码。
2. 在 Supabase SQL Editor 执行 `supabase_schema.sql`。
3. 在 Streamlit Cloud 的 Secrets 中配置 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`SUPABASE_URL` 和服务端使用的 `SUPABASE_SECRET_KEY`。旧项目兼容 `SUPABASE_SERVICE_ROLE_KEY`，不要使用公开的 anon/publishable key。
4. 访问 `/admin` 登录，保存草稿或发布案例；已发布案例会出现在 `/cases`。

服务端密钥不能写入前端，也不要提交到 GitHub。`supabase_schema.sql` 只建立案例表，原始共享表格数据仍由现有抓取程序维护。

## 本地运行

双击 `启动策略指引平台.bat`：脚本打开当前 Streamlit 主站 `http://127.0.0.1:8511/`，并在后台保留本地日表同步服务（4174 端口，不再打开旧网站）；重复双击不会重复启动这两个服务。需要只启动前台时，也可运行：

```powershell
C:\Users\chris\AppData\Local\Programs\Python\Python313\python.exe -m streamlit run app.py --server.port 8511
```

`streamlit run app.py` 本身只读 `site/site-data.json`，单独刷新前台不会抓取腾讯表格。由 BAT 启动的本地同步服务会在启动、访问旧服务及每日 08:00／18:00 时按时段判断是否增量抓取；同步完成后刷新 Streamlit 页面即可读取新数据。Streamlit Cloud 的日表则依赖 GitHub Actions 同步后的仓库提交；与 Supabase 案例库是两条独立数据链。

案例发布写入 Supabase 后，新访问或刷新 `/cases` 可直接读到最新已发布内容，无需 Git 提交；草稿只在后台可见。配置之前本机使用忽略入库的测试 JSON，云端禁止保存。公开环境中的测试账号只是过渡方案，正式对外使用前务必换强密码并升级独立账号／权限控制。
