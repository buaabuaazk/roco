# 本地 Agent 调试台

React + TypeScript + Vite 前端，FastAPI 后端复用 `RocoAgent`、六个查询工具与 BWIKI JSON。
服务地址为 `http://127.0.0.1:8765`，模型密钥由后端环境变量 `ZZZ_API_KEY` 读取。

## 启动

在 `roco` 项目目录执行。Python 使用 Conda `hello-agents`；前端构建使用 Node.js 22.12+（本机验证版本为 24）。

```sh
conda activate hello-agents
python -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
python -m roco_server
```

在浏览器打开 `http://127.0.0.1:8765`。
依赖和前端构建完成后，日常启动只需 `python -m roco_server`。端口可通过 `--port 8766` 调整。
`web/dist` 是本机构建产物，由 Git 忽略；另一台电脑拉取源码后需先构建。

## 使用

- 左侧新建、切换会话，可填写新会话的模型 ID。已创建会话沿用自身模型。
- 中间支持多轮提问，Enter 发送，Shift+Enter 换行。快捷问题先填入输入框，点击发送后调用模型。
- 右侧实时展示模型请求轮次、工具名称、参数、结果状态与总耗时。点击历史回答的轨迹按钮查看对应一轮。
- “模型视图”展示实际回传模型的工具内容，“完整结果”保留底层资料与来源，“参数”展示模型生成的调用参数。
- JSON 支持复制；长内容可展开完整显示；回答支持 Markdown 表格、列表和代码块。
- 顶栏重载按钮重新读取 JSON，并清空所有会话上下文和页面对话。执行前的提示会说明此行为，本地日志继续保留。
- 每个会话同时处理一个问题；不同会话独立。切换或关闭页面只断开事件订阅，后台继续执行；返回会话后恢复记录。

页面会话和模型上下文保存在后端进程内，重启服务后建立新会话。
问题、工具结果和最终回答仍即时保存至 `logs/*.jsonl`，沿用现有脱敏规则；前端事件来自已脱敏的日志记录。
模型请求事件展示轮次和时间，工具事件展示参数与结果。模型内部推理文本继续保留在原有协议内部。

## 前后端分别开发

后端终端：

```sh
conda activate hello-agents
python -m roco_server
```

前端终端：

```sh
npm --prefix web run dev
```

打开 Vite 输出的 `http://127.0.0.1:5173`，`/api` 会代理到本机 8765 端口。
前端默认代理端口在 `web/vite.config.ts` 中配置。生产构建由同一个 FastAPI 服务提供，使用同源 API。

## API

| 接口 | 用途 |
|---|---|
| `GET /api/config` | 默认模型、密钥是否已配置、数据数量及工具名称 |
| `GET/POST /api/sessions` | 列出或创建会话 |
| `GET /api/sessions/{id}` | 获取会话及本次服务运行期间的记录 |
| `POST /api/sessions/{id}/runs` | 提交问题并获得 run_id |
| `GET /api/sessions/{id}/runs/{run_id}/events` | SSE 事件流，支持 Last-Event-ID 续读 |
| `POST /api/sessions/{id}/reset` | 清空对应会话上下文及页面记录 |
| `POST /api/data/reload` | 重载 JSON，清空会话上下文 |

模型在后台线程执行，事件流随日志写入推送。运行中重复提交或重载数据返回 409；输入校验失败返回 422；失效会话返回 404。
应用绑定回环地址并校验 Host，前端通过同源或本地开发代理请求 API。

## 验证

```sh
conda activate hello-agents
python -m unittest discover -s tests -v
npm --prefix web run build
```

自动检查覆盖会话隔离、运行中保护、模型失败、实时事件、密钥脱敏、数据重载及日志失败恢复。
浏览器已验证真实模型查询“机械方方怎么进化？”及多轮追问，确认工具结果与模型视图可切换查看。

## 数据检测页面

左侧「数据检测」或 `http://127.0.0.1:8765/#data`：

- 检测更新：仅请求本地快照中模块的修订编号与时间，列出本地与远端版本差异。
- 一键更新：下载采集器完整模块集（含 S5 分片），暂存转换全部精灵、技能和特性，校验技能引用和 JSON 后切换正式目录；整目录替换会清理上游已撤下的条目。
- 更新成功自动刷新 Agent 数据并清空会话上下文；调用日志保留。更新期间暂停新提问，有对话执行时需等待结束。
- 网络、解析、规则校验或重新加载失败会保留原正式数据并显示原因，可重试。遇到未知的赛季聚合规则版本时，需核对转换器后再更新。
- 检测结果保存在 `data/bwiki/update_status.json`（Git 忽略）；原始响应位于 `data/bwiki/modules`，正式 JSON 位于 `data/bwiki/converted`。

API：`GET /api/data/status`、`POST /api/data/check`、`POST /api/data/update`。两个 POST 启动后台任务，GET 读取任务进度与报告。检测范围为已采集模块；页面正文与图片另行采集。
