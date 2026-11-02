# 第一版五个查询工具

工具代码位于 `roco_data/tools.py`，执行入口为 `RocoTools.execute(name, arguments)`。
`definitions` 提供 Chat Completions 风格的函数工具规格，模型接入时可作为 `tools` 参数。

| 工具名称 | 用途 | 参数 |
|---|---|---|
| `search_pets` | 按名称关键词或属性搜索精灵候选 | 可选 `query`、`type_name`、`limit` |
| `get_pet` | 精灵概览或指定资料分区 | 必填 `identifier`；可选 `section` |
| `get_skill` | 技能的威力、能耗、属性和效果 | 必填 `identifier` |
| `get_pet_skills` | 可学习技能、来源和学习条件，关联独立技能详情 | 必填 `identifier`；可选 `source`、`max_level`、`skill` |
| `compare_pets` | 比较或排序一项种族值 | 必填 `identifiers`（2～10 个对象）；可选 `stat` |

`identifier` 为准确名称或正整数 ID。`source` 使用 `level`、`machine`、`blood`。
`section` 与 `stat` 的可选值由工具规格明确列出，模型可依据描述选择。

## 本地调用

在项目目录激活 `hello-agents` 环境后：

```python
from roco_data import RocoQueries, RocoTools

with RocoQueries() as queries:
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
当前版本完成五个工具的封装；后续接入模型请求、工具调用结果回传及多轮执行限制，再运行 Agent 端到端验收。
