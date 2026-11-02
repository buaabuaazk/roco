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
