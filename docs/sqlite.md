# SQLite 查询层

## 环境与快速使用

使用 Conda 环境 `hello-agents`，依赖 Python 标准库 `sqlite3`。在 `roco` 目录执行：

```sh
conda activate hello-agents

# 创建查询库，或把最新 JSON 导入现有查询库
python -m roco_data import

# 入库数量、技能详情缺失数量和导入时间
python -m roco_data stats

# 通过名称关键词、属性筛选
python -m roco_data pets 喵
python -m roco_data pets --type 草
python -m roco_data skills 毒

# 精灵概览；名称与 pet_id 均可
python -m roco_data pet 喵喵
python -m roco_data pet 3001 --section profile
python -m roco_data pet 喵喵 --section family
python -m roco_data pet 喵喵 --section acquisition
python -m roco_data pet 喵喵 --section egg

# 独立技能详情
python -m roco_data skill 抓挠
python -m roco_data skill 7020360

# 按来源关联技能详情与学习条件
python -m roco_data pet-skills 喵喵 --source level
python -m roco_data pet-skills 喵喵 --source level --max-level 10
python -m roco_data pet-skills 喵喵 --source machine --skill 毒沼
python -m roco_data pet-skills 喵喵 --source blood --skill 星星撞击

# 比较种族值；按指定数值降序排序
python -m roco_data compare 喵喵 迪莫 --stat speed
python -m roco_data compare 喵喵 水蓝蓝 火花 迪莫 --stat sum

# 数据层回归测试
python -m unittest discover -s tests -v
```

默认数据库路径为 `data/roco.db`，按模块所在位置确定，与终端当前目录独立。
在项目目录执行命令可找到 `roco_data` 模块。自定义路径时将 `--db` 放在子命令之前：

```sh
python -m roco_data --db /tmp/roco-check.db import --data-dir data
python -m roco_data --db /tmp/roco-check.db pet 喵喵
```

## Python 查询接口

```python
from roco_data import RocoQueries, import_data

import_data()  # 在采集更新后调用，导入当前本地快照

with RocoQueries() as queries:
    pet = queries.get_pet("喵喵")
    evolution = queries.get_pet(3001, section="family")
    skill = queries.get_skill("抓挠")
    learnable = queries.get_pet_skills("喵喵", source="machine", skill="毒沼")
    early = queries.get_pet_skills(3001, source="level", max_level=10)
    comparison = queries.compare_pets(["喵喵", "迪莫"], stat="speed")
```

网页后端和 Agent 工具可以复用这些函数。每个查询返回 `status`、`data`、`sources`，必要时附加 `message`。
精灵默认查询提供概览；`section` 可查询 `profile`、`features`、`family`、`acquisition`、`egg`、`ride`、`talents`、`fruit`、`handbook`、`ecology`、`natures`、`stories` 等已有分区。

`sources` 记录数据文件、来源地址、来源更新时间和缓存标记；同一精灵的不同分区可能有不同来源时间。每项技能关联另附该技能的来源记录。

## 查询状态

| 状态 | 含义 |
|---|---|
| `ok` | 查询完成；成功的空列表也是一种有效结果 |
| `not_found` | 当前库未检索到指定名称或 ID |
| `ambiguous` | 名称匹配多个条目，返回候选 ID 供澄清 |
| `data_missing` | 对象存在，所需分区或种族值待补齐 |
| `detail_missing` | 技能 ID 已知，独立技能详情待补齐 |
| `partial` | 学习关系已知，其中部分技能详情待补齐 |
| `invalid_argument` | 查询参数需要修正 |
| `error` | 命令行捕获的文件、导入或 SQLite 错误 |

`get_pet_skills` 按 `level`、`machine`、`blood` 区分学习来源，保留等级、血脉 ID，以及来源可解析的血脉名称。`max_level` 单独使用时默认筛选升级技能，技能石采用独立来源筛选。
指定 `skill` 时，`can_learn_in_selected_scope` 表示该技能是否出现在本次来源和等级条件限定的关系中。

命令行结果输出为可读 JSON；`ok` 退出码为 0，其他状态为 2，调用方可继续读取结构化结果。

## 存储结构

| 表 | 内容 |
|---|---|
| `pets` | 精灵 ID、名称、图鉴编号、可比较的种族值列、完整分区 JSON、来源信息 |
| `pet_types` | 精灵属性，支持按属性筛选 |
| `skills` | 技能 ID、名称、列表概要、独立详情、来源信息 |
| `pet_skills` | 精灵与技能关系、学习来源、顺序、等级、血脉条件 |
| `metadata` | 导入时间、结构版本、条目数量等快照信息 |

仅有列表或关联 ID 的技能也保留记录，详情为待补齐状态。精灵关系通过外键关联该记录，完整性与技能详情采集进度分别表达。
技能威力、能耗在详情中沿用来源类型，保留原始效果描述。种族值作为可比较的整数列保存。

## 更新与同步

1. 采集脚本把数据保存为 JSON。
2. 运行 `python -m roco_data import` 更新本地查询快照。
3. 新查询连接读取更新后的数据。

导入采用单个事务重建逻辑快照；重复导入保持学习关系数量稳定，导入错误会回滚到上一份已提交快照。源 JSON 保持原样。部分目录尚未生成 `combined.json` 时，其精灵资料在后续完成汇总后进入查询库。
查询连接采用只读模式。SQLite 使用 WAL 并设置锁等待，适合当前本地查询与导入更新；长期持有的读事务按 SQLite 快照语义读取数据。

Git 同步代码与采集 JSON。`roco.db` 及 SQLite 辅助文件已加入忽略规则，另一台电脑拉取后运行导入命令即可重建数据库。

## 当前覆盖范围

数据层支持验收用例中的资料、技能关联、筛选、排序、来源与缺失状态查询。多轮指代、自然语言回答、伤害计算的对话引导在后续 Agent 层实现。
后续切换数据库时，保持公开查询函数及结果格式，替换数据导入、表定义和 SQL 执行部分。
