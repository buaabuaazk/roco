# 喵喵（3001）资料

`combined.json` 是精灵查询使用的汇总文件。技能按升级、技能石、血脉分组保存 `skill_id` 及学习条件；顶层 `skill_ids` 为去重后的技能 ID。

技能详情通过 ID 关联到 `../../skills/<技能ID>.json`。本目录内 `skills/` 保留为早期试点存档，统一技能库位于 `data/skills/`。

`pet-*.json` 保留完整来源响应，`manifest.json` 记录来源更新时间与缓存标记。来源为 091p 公开接口及其上游洛克魔法书 Wiki。聚合响应使用旧缓存，故事接口返回空列表，图片保存来源链接。

从 `roco` 目录运行 `python3 scripts/collect_pets.py --ids 3001` 可复用本地响应重建汇总；加 `--refresh` 可重新请求精灵资料。技能通过 `collect_skills.py` 独立采集。

数据拆分前的汇总及记录位于 `data/backups/`，修正报告为 `data/skill_split_report.json`。
