# 命令行 Agent

## 开始使用

在 `roco` 目录使用 Conda 环境 `hello-agents`：

```sh
conda activate hello-agents
python -m pip install -r requirements.txt
python -m roco_data import

# 使用默认模型，进入多轮聊天
python -m roco_agent

# 单次提问并显示工具调用过程
python -m roco_agent "喵喵能学毒沼吗？" --trace

# 返回完整 JSON，适合后续接入其他程序
python -m roco_agent "喵喵和迪莫谁速度种族值高？" --json
```

密钥读取本机环境变量 `ZZZ_API_KEY`。模型按 `--model`、`LLM_MODEL_ID`、默认 `deepseek-v4.1-flash` 的顺序选择。
如需清除当前终端之前的模型设置，可执行 `unset LLM_MODEL_ID` 后使用默认值。
本机环境中已安装 OpenAI Python SDK 3.41.0，依赖版本记录在 `requirements.txt`。

多轮模式中输入 `/reset` 清空上下文，`/exit` 退出；Ctrl+C 也可退出。最近四轮成功对话保存在本次进程内存中。

另一台电脑拉取代码后，配置该电脑的环境变量、安装依赖并导入 JSON，即可使用。

## 执行过程

1. 把用户问题、短期历史和五个工具的规格发送给模型。
2. 模型返回工具名称、参数和调用 ID。
3. 本地工具注册表校验参数，执行 SQLite 只读查询。
4. 查询结果使用对应 `tool_call_id` 回传给模型。
5. 模型继续选择工具或生成最终回答。

查询工具为 `search_pets`、`get_pet`、`get_skill`、`get_pet_skills`、`compare_pets`。
模型调用采用智增增的 OpenAI 兼容 Chat Completions 接口：`https://api.zhizengzeng.com/v1`。
消息结构参考 [OpenAI 官方 Function Calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。
智增增的模型支持和鉴权行为以实际接入为准。

## 调用限制与失败处理

- 每轮最多 6 次模型请求、12 次工具调用，执行总预算为 120 秒；单次模型请求超时上限为 60 秒。
- 单次模型请求的输出上限为 2048 tokens，SDK 自动重试次数设置为 0；临时连接失败后可重新提问。
- 工具结果移除图片链接字段，保留游戏事实和来源。结果超过 50000 字符时向模型返回缩小查询范围的提示。
- 请求上下文超过 120000 字符时优先移除较早的完整对话；当前轮仍过大时返回 `context_limit`。
- 参数错误和未注册工具作为结构化结果回传；模型可据此修正请求。
- HTTP 状态、连接失败和超时使用脱敏错误说明；成功轮次写入短期历史，失败轮次保留原有成功历史。
- 超时预算在执行边界检查；网络和数据库调用按各自超时返回后，再判断本轮剩余预算。

`--json` 返回 `status`、`answer`、`tool_calls`、`sources`。单次提问成功退出码为 0，其他结果为 2。
`tool_calls` 记录工具名称、模型提供的参数和执行状态；`sources` 提供实际返回资料的来源。
发给模型的工具结果移除来源链接、文件路径、更新时间及缓存状态，包括技能条目内的嵌套元数据。原始数据与 Agent 返回的 `sources` 仍供程序侧核验；模型只接收查询状态和游戏资料。升级、技能石、血脉等实际学习方式继续保留。
模型视图合并重复属性、类型和进化条件，将学习方式与技能详情放在同一条记录中，具体格式见 [工具说明](tools.md)。

## Python 接入

```python
from roco_agent import RocoAgent
from roco_agent.llm import ChatModel
from roco_data import RocoQueries

model = ChatModel()  # 从环境变量读取密钥和模型 ID
try:
    with RocoQueries() as queries:
        agent = RocoAgent(model, queries)
        first = agent.ask("喵喵能学毒沼吗？")
        follow_up = agent.ask("它的特性呢？")
finally:
    model.close()
```

目前提供命令行和 Python 接口。网页后端可复用 `agent.ask()`；来源元数据和工具状态可供前端展示。
全量 20 条端到端验收继续按 `docs/agent_acceptance_v1.md` 执行，自动回归测试采用模拟模型，单独覆盖协议与执行边界。
