# Roco 数据采集与查询

## 本地调试台

完成依赖安装和前端构建后，运行 `python -m roco_server`，在浏览器打开 `http://127.0.0.1:8765`。
支持多轮聊天、独立会话、实时工具轨迹，以及完整查询结果和模型视图对照。启动与开发步骤见 [调试台说明](docs/web_debug.md)。

## 与 Agent 对话

```sh
conda activate hello-agents
python -m pip install -r requirements.txt
python -m roco_agent
```

模型使用本机 `ZZZ_API_KEY` 环境变量通过智增增调用，默认使用 `deepseek-v4.1-flash`；可用 `--model` 或 `LLM_MODEL_ID` 覆盖。
支持多轮追问、六个查询工具，以及 `--trace` 查看工具调用。开发阶段直接读取 BWIKI 正式 JSON。
命令行默认将问题、工具参数、完整查询结果、模型收到的结果和最终回答保存至本地 `logs/*.jsonl`，日志由 Git 忽略。
完整配置与限制见 [Agent 使用说明](docs/agent.md)。

## JSON 查询

在项目目录运行：

```sh
conda activate hello-agents
python -m roco_data stats
python -m roco_data pet 喵喵
python -m roco_data pet-skills 喵喵 --source machine --skill 毒沼
python -m roco_data skill-pets 丰饶
python -m roco_data compare 喵喵 迪莫 --stat speed
```

默认读取 `data/bwiki/converted` 中的精灵、技能和特性 JSON，支持名称检索、资料分区、技能关联、学习等级筛选和种族值比较。
Agent 启动时载入资料，采集更新后重启生效。`roco_agent --data-dir` 和 `roco_data --json-dir` 可指定目录。
原有 SQLite 保留为可选查询快照，显式指定 `--db data/roco.db` 时使用，见 [SQLite 查询层说明](docs/sqlite.md)。

目前提供六个 Agent 工具：搜索精灵、查精灵、查技能、查询精灵可学技能、反查技能可学精灵、比较种族值。
工具定义、参数校验和固定执行入口已实现，见 [工具说明](docs/tools.md)。

## 两台电脑之间同步

每次开始采集前，在项目目录运行 `git pull --ff-only`。采集结束后提交并推送：

```sh
git add scripts data roco_data roco_agent tests docs AGENTS.md README.md requirements.txt .gitignore .gitattributes
git commit -m "Update collected data"
git push
```

仓库：https://github.com/buaabuaazk/roco （私有）。

另一台电脑完成 GitHub SSH 密钥认证后，首次使用：

```sh
git clone ssh://git@ssh.github.com:443/buaabuaazk/roco.git
cd roco
```

这里使用 GitHub SSH 的 443 端口，本机已验证可用。
脚本和已保存的 JSON 数据一起同步；Python 缓存、临时文件和本地环境文件由 `.gitignore` 忽略。
两台电脑轮流采集，每次开始前拉取、结束后推送，可减少数据文件冲突。

使用 Python 3 和 curl，从 091p 公开只读 API 采集洛克魔法书 Wiki 数据。
以下命令在 `roco` 目录运行。

```sh
# 指定精灵；重复运行复用本地成功响应，并补采失败项
python3 scripts/collect_pets.py --ids 3002 3003

# 从图鉴发现精灵，先采集前 10 只
python3 scripts/collect_pets.py --all --limit 10

# 采集全部图鉴，运行时间取决于数量和接口状态
python3 scripts/collect_pets.py --all

# 更新指定精灵资料与技能关联，间隔设置为 2 秒
python3 scripts/collect_pets.py --ids 3002 --refresh --interval 2

# 离线检查采集逻辑
python3 scripts/test_collect_pets.py
```

请求串行执行，间隔至少 1 秒；失败请求最多尝试 3 次，逐次增加间隔。
每项成功响应立即保存，单只精灵的请求结果持续写入 manifest。批次中出现失败项目时退出码为 1，可按相同命令重跑。

## 数据布局

- `data/api_catalog.json`：公开接口目录；动态识别精灵详情分区。
- `data/lists/`：图鉴分页响应，供 `--all` 使用。
- `data/pets/<ID>/combined.json`：精灵汇总资料；技能部分保存 ID 和学习条件。
- `data/pets/<ID>/pet-*.json`：采集接口的完整 JSON 响应。
- `data/pets/<ID>/manifest.json`：单只精灵的完整性状态、请求来源、更新时间与缓存标记。
- `data/skills/<技能ID>.json`：独立技能库，供精灵通过 `skill_id` 关联查询。
- `data/batch_manifest.json`：最近一次批次所选 ID 和各精灵结果。

JSON 统一为 UTF-8、4 空格缩进和可读中文，文件通过临时文件替换保存。
图片保留来源 URL。进化家族成员保存为关系信息，各形态的完整档案通过对应精灵 ID 单独采集。

精灵脚本的 `--refresh` 会重新请求所选精灵、接口目录及使用的图鉴分页。技能库通过技能脚本单独刷新。
上游仍可能返回旧缓存，时效以响应的 `updated_at`、`stale` 和 `warning` 为依据。
精灵采集的 `complete` 表示公开分区与技能关联均成功获取，空列表按来源实际内容保存。
脚本复用本地数据时检查成功标记与主要 ID；如需修复损坏缓存，可使用 `--refresh`。

`collect_miaomiao.py` 是精灵采集的喵喵快捷入口；批量采集使用 `collect_pets.py`。

## 独立采集技能

直接读取技能图鉴及技能详情，适合集中补齐技能库。

```sh
# 先处理技能图鉴前 10 个技能
python3 scripts/collect_skills.py --all --limit 10

# 采集整个公开技能图鉴
python3 scripts/collect_skills.py --all

# 指定技能 ID 补采
python3 scripts/collect_skills.py --ids 7060140

# 离线检查
python3 scripts/test_collect_skills.py
```

技能脚本将详情写入 `data/skills/`。日志的 `local` 表示复用本地响应，
`network` 表示发起网络请求。技能列表分页保存在 `data/lists/skills_*.json`，
最近一次运行记录保存在 `data/skills_manifest.json`。
支持 `--refresh` 和 `--interval`；`--limit` 包含已有技能，重跑相同命令可补采失败项。
精灵资料的 `skill_ids` 对应技能库的文件名；例如 `7020360` 关联 `data/skills/7020360.json`。
`sections.skills` 按升级、技能石和血脉保存关联，并保留学习等级、血脉 ID。
原始接口响应保留上游随附的技能字段，`combined.json` 使用精简关联结构。
已有精灵目录在下次运行精灵脚本时按新结构重建汇总文件，并复用成功的本地响应。
技能库尚未采齐时，精灵关联 ID 可先保存，详情待技能采集补齐。
