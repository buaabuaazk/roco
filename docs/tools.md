# 查询工具

工具代码位于 `roco_data/tools.py`，执行入口为 `RocoTools.execute(name, arguments)`。
`definitions` 提供 Chat Completions 风格的函数工具规格，模型接入时可作为 `tools` 参数。

| 工具名称 | 用途 | 参数 |
|---|---|---|
| `search_pets` | 按名称关键词或属性搜索精灵候选 | 可选 `query`、`type_name`、`limit` |
| `get_pet` | 精灵概览或指定资料分区 | 必填 `identifier`；可选 `section` |
| `get_skill` | 技能的威力、能耗、属性和效果 | 必填 `identifier` |
| `get_pet_skills` | 可学习技能、来源和学习条件，关联独立技能详情 | 必填 `identifier`；可选 `source`、`max_level`、`skill` |
| `get_skill_pets` | 按技能反查可学习的精灵，合并各自学习条件 | 必填技能 `identifier`；可选 `source`、`limit`、`offset` |
| `compare_pets` | 比较或排序一项种族值 | 必填 `identifiers`（2～10 个对象）；可选 `stat` |

`identifier` 为准确名称或正整数 ID。JSON 查询的 `source` 使用 `level`、`machine`、`blood`、`legendary`。
`section` 与 `stat` 的可选值由工具规格明确列出，模型可依据描述选择。
`section` 的枚举和逐项中文用途由同一份分区说明生成：base、profile、features、family、acquisition、ecology、egg、fruit、handbook、ride、skills、history、training_reference。
当前工具只开放这些 JSON 查询分区；appearance、talents、natures、stories 已从工具选项移除。

`search_pets` 优先匹配完整页面名称，再匹配精灵名称；均未命中时进行关键词搜索。属性筛选始终生效，空关键词用于列举；同名多候选保留供确认。数量限制在选择匹配方式后应用。

Agent 向模型回传 `search_pets` 结果时采用精简格式：唯一匹配为 ID（如 `3001`），多匹配为名称和 ID 列表，无匹配为“未找到”。数量截断时返回 `candidates` 和 `has_more: true`，供模型继续搜索。底层查询结果与调试状态仍保持结构化格式。
其他工具发给模型时保留游戏资料与查询状态，递归移除来源文件、地址、更新时间及缓存元数据。程序侧仍保留完整查询结果和来源记录。

模型结果另由 `roco_agent/presentation.py` 整理：

- `get_pet`：属性等名称引用直接返回名称；移除重复的类别编号和分区列表。JSON 进化分支直接提供起点、终点和明确的等级、特殊条件、首领信物。
- `get_skill`：用名称、属性、类型、威力、能耗、效果表达核心资料。相同的属性及类型只出现一次；类型确有差异时保留伤害类型。额外规则保存在补充信息中。
- `get_pet_skills`：技能详情与学习方式合并为一个条目；升级、血脉条目保留学习等级，血脉保留名称或 ID；技能石条目省去无关的空血脉字段。详情缺失状态与查询范围内的学习资格继续明确返回。
- `get_skill_pets`：返回技能名称、精灵名称及学习方式、等级、血脉或传说要求；保留总数、has_more 和下一页 next_offset。同一精灵的多种学习方式合并，分页按精灵条目（含形态）计数。
- `compare_pets`：保留比较项、排序、数值和两只精灵的差值。

数字字符串中的整数转为数值，零能耗保留为 0；变威力等表达沿用来源文字。
这些变化作用于模型消息，Python 查询接口、SQLite 与原始 JSON 保持完整。

## 本地调用

在项目目录激活 `hello-agents` 环境后：

```python
from roco_data import JsonQueries, RocoTools

with JsonQueries() as queries:
    tools = RocoTools(queries)
    schemas = tools.definitions
    answer = tools.execute(
        "get_pet_skills",
        '{"identifier":"喵喵","source":"machine","skill":"毒沼"}',
    )
    print(answer)
```

执行入口接收 JSON 参数字符串或字典，先校验再查询。返回沿用数据层的 `status`、`data`、`sources`，可附带 `message`。
参数错误返回 `invalid_argument`，未注册工具返回 `unknown_tool`，查询执行故障返回 `tool_error`。
精灵或技能缺失、同名、详情待补齐等业务状态沿用查询层定义。

## 扩展与后续接入

新增工具时，补充查询函数、工具规格和固定执行注册表，并增加对应验证。
六个工具已接入模型请求、工具调用结果回传及多轮执行限制，见 [Agent 使用说明](agent.md)。完整自然语言验收继续按验收用例执行。

## 技能反查精灵

“哪些精灵可以学习丰饶”使用 `get_skill_pets({"identifier": "丰饶"})`，查询遍历本地学习关系后一次返回结果。
工具默认 `limit=100`、`offset=0`；`source` 可限制为升级、技能石、血脉或传说技能。SQLite 兼容查询使用其已有的三类来源。
底层 `data` 中 `items` 按精灵分组，`learning` 保留各条学习条件，`total` 是当前筛选条件下的精灵总数。已知技能的空列表表示当前资料没有匹配关系，未知或同名技能使用标准状态返回。

```sh
python -m roco_data skill-pets 丰饶
python -m roco_data skill-pets 徒长 --source blood --limit 100 --offset 100
```
