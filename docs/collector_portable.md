# BWIKI 独立采集包

解压 `roco-bwiki-collector.zip`，进入 `roco-bwiki-collector` 目录。
支持 Windows、macOS、Linux；使用 Python 3.10+ 和可用的 `curl` 命令。
Python 标准库即可运行。可激活另一台电脑已有的 Conda 环境，例如 `conda activate hello-agents`。

## 1. 检查环境

在解压目录打开终端，执行：

```sh
python --version
curl --version
```

## 2. 正式采集

```sh
python scripts/collect_bwiki_modules.py --all --refresh
```

命令会读取 BWIKI 公开模块，按游戏 ID 转换全部精灵、战斗技能和特性。
无需大模型密钥。网络失败会有限重试；成功结束时输出数量和 `"status": "complete"`。
再次获取最新数据时执行相同命令。已有模块的离线重新转换可省略 `--refresh`。

输出结构与开发项目一致：

```text
roco-bwiki-collector/
  data/
    bwiki/
      modules/
        response.json          原始模块响应及来源修订
        fetch.json             采集地址和时间
      converted/
        pets/3001.json         精灵资料及技能学习关系
        skills/7020360.json    独立技能详情
        features/200076.json   独立特性详情
        reference.json        术语、历史版本及培养参考标签
        manifest.json         本批次文件列表和完整性状态
```

目录位置相对于脚本确定，可将整个解压目录放在任意磁盘位置。

## 3. 打包传回

全量采集成功后运行：

```sh
python scripts/pack_bwiki_results.py
```

会在解压目录生成 `bwiki-data.zip`，将这个文件传回开发电脑即可。
压缩包包含本批次正式 JSON，以及原始模块、来源修订和采集时间；内部路径从 `data/bwiki/` 开始。
打包脚本检查批次状态和文件是否齐全；只收入 manifest 列出的正式文件，避免把其他批次的遗留文件混入。
返回电脑后可先解压到临时目录检查，再将其中的 `data/bwiki` 交给开发项目使用。

## 少量采集与问题排查

```sh
# 只采集两个精灵及其关联技能
python scripts/collect_bwiki_modules.py --ids 3001 3200 --refresh

# 独立采集三个技能
python scripts/collect_bwiki_modules.py --skill-ids 7020360 7120200 7070170 --refresh
```

少量采集会将 manifest 改为该次选择的范围；传回全量数据前，再执行一次 `--all --refresh`。
若提示“展示规则修订已变化”或“赛季展示规则”变化，需核验新版 BWIKI 规则并更新脚本；保留完整报错供处理。
本包只负责采集、转换、打包，输出由开发电脑后续读取。
