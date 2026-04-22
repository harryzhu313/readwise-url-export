#!/usr/bin/env python3
"""
Readwise Reader 按标签导出 Reader 链接
====================================
功能：通过 Readwise Reader API v3 的 /list/ 端点，
      获取指定标签下所有文档的 Reader 链接（read.readwise.io/read/{id}）
      和原始 source_url，输出为 CSV 文件。

Reader 链接是给下游 Readwise MCP 读取全文用的，本脚本不抓原文。

使用方法：
  1. 在脚本同目录下的 .env 文件中写入 READWISE_TOKEN=xxx（推荐）
  2. 或通过命令行传入: python3 readwise_export_by_tag.py --token YOUR_TOKEN --tag 标签名

获取 Token：https://readwise.io/access_token
"""

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = "https://readwise.io/api/v3"
READER_URL_PREFIX = "https://read.readwise.io/read/"
SCRIPT_DIR = Path(__file__).resolve().parent

# 手动打标签的文章只会出现在这 4 个位置，跳过 feed 可避免拉取上万条 RSS 自动抓取内容
NON_FEED_LOCATIONS = ["new", "later", "shortlist", "archive"]


def load_dotenv():
    """从脚本同目录的 .env 文件加载环境变量（不覆盖已有值）。"""
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def fetch_all_documents(token: str) -> list:
    """
    通过 Reader v3 /list/ 端点分页获取所有文档（不含 html 正文）。
    仅遍历 NON_FEED_LOCATIONS，跳过 feed 以避免 RSS 自动抓取内容拖慢速度。

    /list/ 不带 withHtmlContent 时限速 20 req/min；正文由下游 MCP 取。
    """
    all_results = []

    for location in NON_FEED_LOCATIONS:
        print(f"\n📂 位置 [{location}]")
        next_cursor = None
        page = 0
        loc_count = 0

        while True:
            page += 1
            params = f"location={location}"
            if next_cursor:
                params += f"&pageCursor={next_cursor}"
            url = f"{API_BASE}/list/?{params}"

            req = Request(url)
            req.add_header("Authorization", f"Token {token}")

            print(f"  正在获取第 {page} 页...")

            try:
                with urlopen(req) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except HTTPError as e:
                if e.code == 429:
                    retry_after = int(e.headers.get("Retry-After", 60))
                    print(f"  ⚠️  触发限流，等待 {retry_after} 秒后重试...")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"  ❌ API 请求失败: HTTP {e.code}")
                    sys.exit(1)

            results = data.get("results", [])
            all_results.extend(results)
            loc_count += len(results)
            print(f"  本页 {len(results)} 条，位置累计 {loc_count} 条（总累计 {len(all_results)}）")

            next_cursor = data.get("nextPageCursor")
            if not next_cursor:
                break

            # Reader /list/ 限速 20 req/min
            time.sleep(3)

    return all_results


def fetch_inbox_recent(token: str, limit: int) -> list:
    """
    仅抓取 location=new (Inbox)，按 created_at 倒序取前 limit 条。
    Reader API 未暴露排序参数，所以整页拉完再本地排序。
    """
    all_results = []
    next_cursor = None
    page = 0

    print(f"📂 位置 [new / Inbox]，将按 created_at 倒序取前 {limit} 条")

    while True:
        page += 1
        params = "location=new"
        if next_cursor:
            params += f"&pageCursor={next_cursor}"
        url = f"{API_BASE}/list/?{params}"

        req = Request(url)
        req.add_header("Authorization", f"Token {token}")

        print(f"  正在获取第 {page} 页...")

        try:
            with urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", 60))
                print(f"  ⚠️  触发限流，等待 {retry_after} 秒后重试...")
                time.sleep(retry_after)
                continue
            else:
                print(f"  ❌ API 请求失败: HTTP {e.code}")
                sys.exit(1)

        results = data.get("results", [])
        all_results.extend(results)
        print(f"  本页 {len(results)} 条，累计 {len(all_results)} 条")

        next_cursor = data.get("nextPageCursor")
        if not next_cursor:
            break

        time.sleep(3)

    all_results.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    return all_results[:limit]


def filter_by_tag(docs: list, tag_name: str) -> list:
    """
    筛选出包含指定标签的 Reader 文档。
    Reader /list/ 的 tags 是 dict：{"tag_name": {"name": ..., ...}, ...}。
    """
    matched = []
    tag_lower = tag_name.lower().strip()

    for doc in docs:
        tags_dict = doc.get("tags") or {}
        tag_names = [str(k).lower().strip() for k in tags_dict.keys()]
        if tag_lower in tag_names:
            matched.append(doc)

    return matched


def export_to_csv(docs: list, output_file: str, tag_name: str):
    """将筛选结果导出为 CSV 文件。"""
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "标题 (Title)",
            "作者 (Author)",
            "分类 (Category)",
            "Reader URL",
            "原始链接 (Source URL)",
            "标签 (Tags)",
        ])

        for doc in docs:
            title = doc.get("title", "")
            author = doc.get("author", "")
            category = doc.get("category", "")
            reader_url = f"{READER_URL_PREFIX}{doc['id']}" if doc.get("id") else ""
            source_url = doc.get("source_url", "")
            tags_dict = doc.get("tags") or {}
            tags_str = ", ".join(str(k) for k in tags_dict.keys())

            writer.writerow([
                title,
                author,
                category,
                reader_url,
                source_url,
                tags_str,
            ])

    print(f"\n✅ 已导出到: {output_file}")


def print_summary(docs: list, tag_name: str):
    """在终端打印简要摘要。"""
    print(f"\n{'='*60}")
    print(f"标签 [{tag_name}] 下共找到 {len(docs)} 篇文章")
    print(f"{'='*60}")

    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "(无标题)")
        reader_url = f"{READER_URL_PREFIX}{doc['id']}" if doc.get("id") else "N/A"
        source_url = doc.get("source_url", "")
        print(f"\n{i}. {title}")
        print(f"   Reader: {reader_url}")
        if source_url:
            print(f"   原始链接: {source_url}")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Readwise Reader 按标签导出 Reader 链接"
    )
    parser.add_argument(
        "--token", default=os.environ.get("READWISE_TOKEN"),
        help="Readwise Access Token (默认读取环境变量 READWISE_TOKEN)"
    )
    parser.add_argument(
        "--tag", default=None,
        help="要筛选的标签名称"
    )
    parser.add_argument(
        "--output", default=None,
        help="输出 CSV 文件名 (默认: readwise_<标签名>.csv)"
    )
    parser.add_argument(
        "--list-tags", action="store_true",
        help="列出所有可用的标签（不导出）"
    )
    parser.add_argument(
        "--recent", type=int, default=None,
        help="只抓 Inbox，按添加时间倒序取前 N 条（忽略 --tag）"
    )
    parser.add_argument(
        "--list-only", action="store_true",
        help="仅在终端列出结果，不导出 CSV"
    )

    args = parser.parse_args()

    if not args.token:
        parser.error(
            "未提供 Token。请在 .env 文件中设置 READWISE_TOKEN=xxx，"
            "或通过 --token 参数传入"
        )

    if not args.list_tags and not args.tag and not args.recent:
        parser.error("必须指定 --tag、--recent 或 --list-tags")

    # --recent 模式：只抓 Inbox，不遍历全部位置
    if args.recent:
        print(f"🔄 正在抓取 Inbox 最近 {args.recent} 条...\n")
        docs = fetch_inbox_recent(args.token, args.recent)
        print_summary(docs, f"Inbox 最近 {args.recent} 条")
        if not args.list_only:
            output_file = args.output or f"readwise_inbox_recent_{args.recent}.csv"
            export_to_csv(docs, output_file, "recent")
        return

    print("🔄 正在从 Readwise Reader API 获取数据...\n")
    docs = fetch_all_documents(args.token)
    print(f"\n📚 共获取 {len(docs)} 篇文档")

    # 如果用户只想看标签列表
    if args.list_tags:
        all_tags = set()
        for doc in docs:
            tags_dict = doc.get("tags") or {}
            for k in tags_dict.keys():
                if k:
                    all_tags.add(str(k))
        print(f"\n🏷️  共找到 {len(all_tags)} 个标签:")
        for tag in sorted(all_tags):
            print(f"   - {tag}")
        return

    # 按标签过滤
    print(f"\n🔍 正在筛选标签 [{args.tag}]...")
    matched = filter_by_tag(docs, args.tag)

    if not matched:
        print(f"\n⚠️  未找到标签 [{args.tag}] 下的文章。")
        print("   提示：可以用 --list-tags 参数查看所有可用标签。")
        return

    # 打印摘要
    print_summary(matched, args.tag)

    # 导出 CSV（除非指定 --list-only）
    if args.list_only:
        return
    output_file = args.output or f"readwise_{args.tag}.csv"
    export_to_csv(matched, output_file, args.tag)


if __name__ == "__main__":
    main()
