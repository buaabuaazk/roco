# Roco · 洛克王国世界助手

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
[![数据来源：BWIKI](https://img.shields.io/badge/数据来源-BWIKI-00A1D6)](https://wiki.biligame.com/nrc/首页)
[![在线体验](https://img.shields.io/badge/Demo-在线体验-365C68)](http://49.232.210.244/#damage)

面向《洛克王国：世界》的游戏工具，包含 **Agent 问答助手**和**伤害计算器**。使用 React + TypeScript 构建网页，Python + FastAPI 提供后端服务。

## 在线访问

**公网地址：[http://49.232.210.244/#damage](http://49.232.210.244/#damage)**

当前公网开放伤害计算器。Agent 对话调试和管理后台通过本地服务或 SSH 隧道访问，连接方式见 [部署说明](deploy/README.md)。

## 功能

### Agent 问答助手

- 用自然语言查询精灵资料、技能、学习条件、进化条件和种族值。
- 使用大模型原生 Tool Calling 查询资料，支持多轮提问与指代。
- 支持反查哪些精灵能够学习指定技能，以及比较精灵种族值。
- 网页中可查看工具调用参数、返回结果和执行轨迹；命令行支持 `--trace`。

### 伤害计算器

- 选择攻击方、受击方精灵，展示完整立绘、系别和能力面板。
- 根据 PVP 使用统计填入热门性格与加点，支持手动调整。
- 同时选择最多四个不同技能，自动计算伤害及生命占比。
- 支持物攻、魔攻、物防、魔防、连击和威力 Buff，以及单个技能的基础威力调整。
- 已接入爵士鹿系列与首领形态波普鹿的入场特性加成。
- 可展开查看技能效果和计算过程。

伤害计算采用社区公式估算，部分特殊技能和特性需要手动确认触发条件。公式依据与适用范围见 [伤害计算器说明](docs/damage_calculator.md)。

## 本地运行

Python 使用 Conda 环境 `hello-agents`，前端构建需要 Node.js 22.12+。

在项目根目录执行：

```sh
conda activate hello-agents
python -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
python -m roco_server
```

打开 [http://127.0.0.1:8765/#damage](http://127.0.0.1:8765/#damage) 使用计算器，打开 `/#chat` 使用问答助手。

计算器可独立使用；问答助手通过智增增调用大模型，启动服务前配置 `ZZZ_API_KEY` 环境变量。默认模型为 `deepseek-v4.1-flash`，可用 `LLM_MODEL_ID` 覆盖。

也可从命令行与助手对话：

```sh
python -m roco_agent
python -m roco_agent "喵喵能学毒沼吗？" --trace
```

## 更多说明

- [Agent 使用说明](docs/agent.md)
- [伤害计算器与公式说明](docs/damage_calculator.md)
- [本地网页开发与调试](docs/web_debug.md)
- [服务器部署、SSH 后台与访问统计](deploy/README.md)
