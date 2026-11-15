# Ubuntu 单机测试部署

结构：公网 Nginx（80端口）提供计算器页面，只代理 `/api/damage/`；Python 服务监听 `127.0.0.1:8765`，完整调试页面通过 SSH 隧道使用。模型密钥与本机会话日志不包含在部署包中。

## 构建

在项目根目录执行：

```sh
npm --prefix web ci
npm --prefix web run build
VITE_PUBLIC_ONLY=1 npm --prefix web run build -- --outDir dist-public
```

普通构建在 `web/dist`，公开构建在 `web/dist-public`。本机默认保持普通构建。

也可执行 `bash deploy/package.sh` 一次构建并打包到 `/tmp/roco-deploy.tar.gz`。打包仅包含代码、正式数据、原始模块快照和两份前端；排除Mac附带文件、Python缓存、本机环境变量和会话日志。

## 服务器目录

- `/opt/roco/app`：Python 代码、JSON 数据和 `web/dist` 完整调试页面。
- `/opt/roco/public`：公开计算器构建。
- `/opt/roco/conda/envs/hello-agents`：Python 3.11 Conda 环境。
- `/etc/roco/roco.env`：可选模型环境变量，仅服务器管理员可读。
- `/etc/systemd/system/roco.service`：按本目录模板安装。
- `/etc/nginx/sites-available/roco`：按本目录 `nginx.conf` 安装并启用。

Python 依赖按 `requirements.txt` 安装；服务使用独立 `roco` 用户。代码可读，`data` 和 `logs` 可写。启动前创建 `logs` 目录。代码与两份前端就位后，可执行 `sudo bash /opt/roco/app/deploy/configure.sh` 安装配置、启动服务并检查就绪状态。其主要步骤为：

```sh
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now roco nginx
```

仅对外开放网页80端口；8765保持本机监听。SSH继续采用密钥认证。

## 管理后台

从开发电脑建立隧道（替换路径和公网IP）：

```sh
ssh -i ~/.ssh/roco_deploy_ed25519 -N -L 8766:127.0.0.1:8765 ubuntu@SERVER_IP
```

然后访问 http://127.0.0.1:8766/#data 或 `#chat`。后台默认没有部署大模型密钥，使用对话前在服务器 `/etc/roco/roco.env` 配置 `ZZZ_API_KEY` 后重启服务。

## 验证与更新

公网 `GET /api/damage/pets` 和 `POST /api/damage/matchup` 应成功；`/api/sessions`、`/api/data/update`、`/api/config` 应返回403。公网首页只显示伤害计算入口。

后续更改重新构建两份前端，替换代码和构建文件后执行 `sudo systemctl restart roco`。更新前保存旧版本目录和数据副本。数据更新后台也可以在SSH隧道内使用。

公网冒烟验证：`python deploy/smoke_test.py http://SERVER_IP`（使用hello-agents环境）。

检查服务日志：`sudo journalctl -u roco -n 100 --no-pager`。试用到期前导出数据与服务器配置。

## 访问统计

公开版每次打开或刷新页面通过`POST /api/visits`记录一次访问，浏览器本地保存随机匿名标识；服务端按北京时间逐日哈希去重，数据库保存在`data/visits.db`。只统计公开版页面，不统计计算API调用，本机调试页面也不计入。浏览器禁止本地存储时仍记录访问次数，独立访客计数可能偏低。清理存储、无痕窗口和更换设备可能重复计为访客。

数据检测页展示今日访问次数、今日独立访客、累计访问次数及最近7天。`GET /api/visits/stats`仅通过SSH隧道访问，公网返回403。统计从功能上线起开始记录；数据库及WAL/SHM由Git忽略，更新应用时保留该数据库。
