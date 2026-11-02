# BWIKI 试采

来源：新版洛克王国世界 BWIKI，`https://wiki.biligame.com/nrc/`。
通过公开 MediaWiki `action=parse` 接口读取渲染页面，使用 Python 标准库解析，保存中文 JSON。

运行环境为 Conda `hello-agents`，在项目根目录执行：

```sh
python scripts/collect_bwiki.py 喵喵 机械方方
```

每个精灵目录保存：

- `page.json`：接口原始响应，包括页面标题、页面 ID、修订 ID、wikitext 和渲染后的 HTML。
- `extracted.json`：来源链接、采集时间、进化链各分支的名称与条件原文、页面分区文本及正文文本。正文过滤 style/script。

页面模板的 wikitext 可能仅为 `{{精灵}}`，实际数据在渲染后的 HTML 中；本次提取使用 HTML。
`evolution_branches.steps` 按页面顺序保留精灵及连接条件，保留分支边界和条件措辞。
分区正文目前为文本，技能、特性等尚需后续按各自结构解析。
页面修订 ID 用于定位页面版本；模板和数据模块的更新可能独立于页面修订 ID，原始渲染响应与采集时间一起保留供复核。
来源数据使用及后续分发需核对 BWIKI 当时的授权说明。

## 2026-11-02 对比结果

| 关系 | 本地原有 091p 接口资料 | BWIKI 页面原文 |
|---|---|---|
| 喵喵 → 喵呜 | 等级达到 16，另带 items、money 字段 | LV16 进化 |
| 喵呜 → 魔力猫 | 等级达到 32，另带 items、money 字段 | LV32 进化 |
| 魔力猫 → 叶冕魔力猫 | 首领化 | 通过阳光罐头首领化 |
| 魔力猫 → 武斗酷猫 | 首领化 | 通过月光罐头首领化 |
| 机械方方 → 多彩方方 | 等级达到 28 | LV28 需在他人世界 |
| 多彩方方 → 立方人 | 等级达到 40 | LV40 进化 |

BWIKI 补充了机械方方的他人世界条件以及魔力猫首领化的具体道具。
多彩方方 → 立方人仍仅写等级，是否另有条件需继续核验。
两只样本说明 BWIKI 可作为补充来源，其全量准确性与完整性仍需更多样本验证。
试采结果独立存储于本目录；当前 SQLite 导入器及 Agent 沿用 `data/pets`，本次结果尚未合并到查询库。

提取回归检查：

```sh
python -m unittest discover -s scripts -p test_collect_bwiki.py -v
```

## Lua 结构化试采

```sh
python scripts/collect_bwiki_modules.py 喵喵 机械方方
```

新增文件：

- `modules/response.json`：从公开 MediaWiki revisions 接口读取的原始模块响应，含模块修订 ID、修订时间及 Lua 原文。
- `<名称>/structured.json`：结构化精灵数据。`pet` 包含种族值、生态获取、蛋组等；`feature` 为关联特性；`learnset` 保留等级、血脉及技能详情；`evolutions` 保留分支和条件；`handbook` 为图鉴课题；`manual_evolution_conditions` 为适用的人工条件补充。

数据读取 Catalog、Skills、Learnsets、Evolutions、Handbooks 表，按 Wiki 稳定 ID 关联；`game_id` 是游戏 ID，`pet_000177` 等是 Wiki 稳定 ID，两者分别保留。
Lua 只解析数据字面量，遇到可执行代码或不支持语法会报错；空表统一表示为 JSON 空数组。原始 Lua 响应可供复核。
`--from-response data/bwiki/modules/response.json` 可复用本地模块响应进行离线转换，输出时间标记为采集或转换时间，来源修订时间独立保存。

当前页面通过 SeasonData 和 ContentVisibility 适配器使用基础表及修订表。本脚本已核对并实现当前 S5 隐藏策略下、所采字段使用的 Catalog/Skills/Learnsets 修订、异色与课题过滤；当该赛季开关切换时显式停止，需重新核验新版聚合规则。
人工进化条件补充表单独保留：渲染页面的规则是等级保留，人工条件（含空字符串）优先于成员 `cond`，首领分支另用 `item` 描述信物。本试采保留这些原始字段供核对。

样本验证：

- 喵喵：自学 16、技能石 17、血脉 18，共 51；机械方方：自学 13、技能石 18、血脉 18，共 49，与已采页面数量一致。
- 两只样本的种族值与本地原接口资料一致。
- 机械方方进化链中，多彩方方节点明确含 `level: 28` 和 `cond: "需在他人世界"`。
- 喵喵两段普通进化仅有等级，首领分支另含 `item`，不把所有材料字段自动归类为条件。

这是关联数据模块的试点，培养参考、变动历史等模块尚未纳入结构化输出；现有页面快照继续保留。结果仍独立保存，尚未接入 SQLite/Agent。

```sh
python -m unittest discover -s scripts -p 'test_collect_bwiki*.py' -v
```
