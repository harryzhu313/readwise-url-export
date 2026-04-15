# Readwise 按标签导出工具

通过 [Readwise API v2](https://readwise.io/api_defs) 按标签筛选文章，导出 Readwise URL 和原始链接为 CSV 文件。

## 快速开始

### 1. 获取 Token

前往 [readwise.io/access_token](https://readwise.io/access_token) 获取你的 Access Token。

### 2. 配置 Token

在项目目录下创建 `.env` 文件：

```
READWISE_TOKEN=你的token
```

### 3. 使用

```bash
# 查看所有可用标签
python3 readwise_export_by_tag.py --list-tags

# 按标签导出
python3 readwise_export_by_tag.py --tag 标签名

# 指定输出文件名
python3 readwise_export_by_tag.py --tag 标签名 --output my_export.csv
```

## 参数说明


| 参数            | 必需  | 说明                                    |
| ------------- | --- | ------------------------------------- |
| `--token`     | 否   | Readwise Access Token，未指定时从 `.env` 读取 |
| `--tag`       | 是*  | 要筛选的标签名称                              |
| `--output`    | 否   | 输出文件名，默认为 `readwise_<标签名>.csv`        |
| `--list-tags` | 否   | 列出所有标签（使用时不需要 `--tag`）                |


## 输出格式

导出的 CSV 包含以下字段：


| 字段                | 说明                   |
| ----------------- | -------------------- |
| 标题 (Title)        | 文章/书籍标题              |
| 作者 (Author)       | 作者                   |
| 分类 (Category)     | 内容类型（article、book 等） |
| Readwise URL      | Readwise 阅读链接        |
| 原始链接 (Source URL) | 文章原始来源链接             |
| 高亮数量              | 该文章下的高亮条数            |
| 书籍标签 (Book Tags)  | 书籍级别的所有标签            |


## 标签匹配规则

脚本会在两个层级查找标签：

- **书籍/文档标签** (`book_tags`) — 标记在整篇文章上的标签
- **高亮标签** (`highlight tags`) — 标记在某条高亮上的标签

匹配时忽略大小写。

## 依赖

Python 3.6+，无需安装第三方依赖。