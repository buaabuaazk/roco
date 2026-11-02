# 数据存储约定

采集 JSON 统一使用 UTF-8 编码、4 个空格缩进、中文直接显示，并在文件末尾保留换行。保留来源响应的字段和值。

Python 写入方式：

```python
path.write_text(
    json.dumps(data, ensure_ascii=False, indent=4) + "\n",
    encoding="utf-8",
)
```

采集记录保存请求地址、来源及更新时间。试点数据位于 `pilot/`。
