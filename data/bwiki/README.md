# BWIKI 采集与转换

来源：新版洛克王国世界 BWIKI，`https://wiki.biligame.com/nrc/`。
采集公开 MediaWiki revisions 接口中的 Lua 数据表，再按游戏 ID 转换成独立 JSON。
使用 Conda `hello-agents` 中的 Python 标准库及系统 curl。

## 运行

在 `roco` 根目录执行：

```sh
conda activate hello-agents

# 首次采集全部模块并转换；后续默认复用已保存的模块响应
python scripts/collect_bwiki_modules.py --all

# 请求最新模块，再转换全部数据
python scripts/collect_bwiki_modules.py --all --refresh

# 指定完整页面标题或游戏 ID
python scripts/collect_bwiki_modules.py 喵喵 机械方方
python scripts/collect_bwiki_modules.py --ids 3001 3200

# 转换前十个精灵及其关联技能、特性
python scripts/collect_bwiki_modules.py --all --limit 10

# 离线转换已有快照，输出到独立目录
python scripts/collect_bwiki_modules.py --all \
    --from-response data/bwiki/modules/response.json \
    --output /tmp/roco-bwiki-check
```

网络请求失败或接口返回限流、maxlag 等临时错误时最多尝试三次，间隔递增。
一次请求批量获取模块，精灵条目复用同一批数据。`--refresh` 控制网络更新；转换时重新生成所选 JSON。
名称使用完整页面标题以区分形态，`--ids` 使用游戏 ID，`--limit` 按游戏 ID 排序后截取。

## 文件与字段

| 文件 | 内容 |
|---|---|
| `modules/response.json` | 接口原始响应：模块标题、修订 ID、修订时间、Lua 原文 |
| `modules/fetch.json` | 模块请求地址和实际采集时间 |
| `converted/pets/<游戏ID>.json` | 精灵属性、特性 ID、技能学习关系、进化链、图鉴课题、属性克制、培养参考与历史记录 |
| `converted/skills/<游戏ID>.json` | 独立战斗技能，保留来源字段，并关联术语说明及技能石课题 |
| `converted/features/<游戏ID>.json` | 独立特性资料 |
| `converted/reference.json` | 术语、历史版本信息、培养参考标签与统计赛季 |
| `converted/manifest.json` | 本批次数量、有效文件列表、来源修订、转换时间、缺失引用和状态 |

精灵的 `pet_id`、技能及特性的 `skill_id` 使用游戏 ID；`wiki_id` 和 `wiki_skill_id` 保留 Wiki 内部稳定 ID。
精灵的 `skills` 分为 `level`、`machine`、`blood`、`legendary`，关系记录保留等级、血脉和传说技能要求，详情由独立文件关联。
`profile` 保留精灵原始属性及生态获取字段；种族值键为 `hp/atk/def/spa/spd/spe`，其中 `spd` 为魔防，`spe` 为速度。
培养参考保留来源的 `[标签ID, 原始统计值]`，通过 `reference.json` 的标签解释；历史字段与当前资料独立保存。
`evolution_branches` 保留原始分支和成员字段，并生成有方向的 `transitions`：等级为 `level`，特殊条件为 `special`，首领信物为 `item`。
人工补充条件按游戏 ID、Wiki ID、页面标题顺序匹配，覆盖原特殊条件；空字符串表示明确没有额外特殊条件，等级独立保留。

每个 JSON 使用 UTF-8、4 空格缩进和可读中文。缺失技能引用标记为 `detail_missing`，批次标记为 `partial`。
文件逐个原子替换，转换完成后写入 manifest。增量选择不会删除其他条目的旧文件，当前批次范围以 manifest 的 `files` 为准。

## 赛季规则与完整性

当前已核对 S5 隐藏策略下的基础表和修订表合并、异色与图鉴课题过滤、历史版本过滤。
脚本检查 SeasonData、ContentVisibility 的已核验修订 ID，以及当前赛季开关；规则改变时停止并提示重新核验。
Lua 只解析数据字面量；不支持的语法会明确报错。空 Lua 表转换为 JSON 空数组。
未知学习来源明确报错，缺失技能引用明确列出。模块中提供的信息按原字段保存，其内容完整性仍依赖 BWIKI。

本次快照已完成转换：633 个精灵条目（含形态）、579 个战斗技能、246 个特性、31,303 条学习关系；技能引用均能关联。
机械方方的进化条件为等级 28 且“需在他人世界”；喵喵两段普通进化分别记录等级 16、32，首领分支记录阳光罐头或月光罐头。
原始响应、模块修订时间、实际采集时间、转换时间分别保留。
来源数据使用及后续分发按 BWIKI 相应授权说明执行。

## 页面核验样本

`喵喵/` 和 `机械方方/` 中的 `page.json`、`extracted.json` 是先前保存的页面响应及正文提取；`structured.json` 是先前 Lua 试点输出。
当前批量转换的正式输出位于 `converted/`，精灵与技能分开保存。
需要补采页面以对比模块结果时可执行：

```sh
python scripts/collect_bwiki.py 喵喵 机械方方
```

所有 BWIKI 输出独立保存在本目录。SQLite 与现有 Agent 继续沿用原有资料。

## 验证

```sh
python -m unittest discover -s scripts -p 'test_collect*.py' -v
```

回归检查覆盖数据解析、赛季修订、条件覆盖优先级及空条件、分支边界、技能来源、传说要求和批量选择。
本次还逐一检查了全部学习关系、特性文件和进化两端的游戏 ID，并完成指定 ID 的离线转换验证。
