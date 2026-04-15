#!/usr/bin/env python3
"""
Readwise 按标签导出文章 Public 链接
====================================
功能：通过 Readwise API v2 的 /export/ 端点，
      获取指定标签下所有文章的 readwise_url 和 source_url，
      输出为 CSV 文件。

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

API_BASE = "https://readwise.io/api/v2"
SCRIPT_DIR = Path(__file__).resolve().parent


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


def fetch_all_books(token: str) -> list:
    """
    通过 /export/ 端点分页获取所有书籍及其高亮。
    返回 results 列表，每个元素是一本书/文章的完整数据。
    """
    all_results = []
    next_cursor = None
    page = 0

    while True:
        page += 1
        url = f"{API_BASE}/export/"
        if next_cursor:
            url += f"?pageCursor={next_cursor}"

        req = Request(url)
        req.add_header("Authorization", f"Token {token}")

        print(f"  正在获取第 {page} 页数据...")

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
        print(f"  本页获取 {len(results)} 条，累计 {len(all_results)} 条")

        next_cursor = data.get("nextPageCursor")
        if not next_cursor:
            break

        # 尊重速率限制
        time.sleep(1)

    return all_results


def filter_by_tag(books: list, tag_name: str) -> list:
    """
    筛选出包含指定标签的文章。
    同时检查 book_tags（书籍/文档级别标签）和 highlights 中的 tags（高亮级别标签）。
    """
    matched = []
    tag_lower = tag_name.lower().strip()

    for book in books:
        # 检查 book_tags
        book_tags = book.get("book_tags", [])
        book_tag_names = [t.get("name", "").lower().strip() for t in book_tags]

        if tag_lower in book_tag_names:
            matched.append(book)
            continue

        # 检查 highlights 中的 tags
        highlights = book.get("highlights", [])
        for hl in highlights:
            hl_tags = hl.get("tags", [])
            hl_tag_names = [t.get("name", "").lower().strip() for t in hl_tags]
            if tag_lower in hl_tag_names:
                matched.append(book)
                break

    return matched


def export_to_csv(books: list, output_file: str, tag_name: str):
    """将筛选结果导出为 CSV 文件。"""
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "标题 (Title)",
            "作者 (Author)",
            "分类 (Category)",
            "Readwise URL",
            "原始链接 (Source URL)",
            "高亮数量",
            "书籍标签 (Book Tags)",
        ])

        for book in books:
            title = book.get("title", "")
            author = book.get("author", "")
            category = book.get("category", "")
            readwise_url = book.get("readwise_url", "")
            source_url = book.get("source_url", "")
            num_highlights = len(book.get("highlights", []))
            book_tags = ", ".join(
                t.get("name", "") for t in book.get("book_tags", [])
            )

            writer.writerow([
                title,
                author,
                category,
                readwise_url,
                source_url,
                num_highlights,
                book_tags,
            ])

    print(f"\n✅ 已导出到: {output_file}")


def print_summary(books: list, tag_name: str):
    """在终端打印简要摘要。"""
    print(f"\n{'='*60}")
    print(f"标签 [{tag_name}] 下共找到 {len(books)} 篇文章")
    print(f"{'='*60}")

    for i, book in enumerate(books, 1):
        title = book.get("title", "(无标题)")
        readwise_url = book.get("readwise_url", "N/A")
        source_url = book.get("source_url", "N/A")
        print(f"\n{i}. {title}")
        print(f"   Readwise: {readwise_url}")
        if source_url:
            print(f"   原始链接: {source_url}")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Readwise 按标签导出文章 Public 链接"
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

    args = parser.parse_args()

    if not args.token:
        parser.error(
            "未提供 Token。请在 .env 文件中设置 READWISE_TOKEN=xxx，"
            "或通过 --token 参数传入"
        )

    if not args.list_tags and not args.tag:
        parser.error("必须指定 --tag 或使用 --list-tags")

    print("🔄 正在从 Readwise API 获取数据...\n")
    books = fetch_all_books(args.token)
    print(f"\n📚 共获取 {len(books)} 本书/文章")

    # 如果用户只想看标签列表
    if args.list_tags:
        all_tags = set()
        for book in books:
            for t in book.get("book_tags", []):
                all_tags.add(t.get("name", ""))
            for hl in book.get("highlights", []):
                for t in hl.get("tags", []):
                    all_tags.add(t.get("name", ""))
        print(f"\n🏷️  共找到 {len(all_tags)} 个标签:")
        for tag in sorted(all_tags):
            if tag:
                print(f"   - {tag}")
        return

    # 按标签过滤
    print(f"\n🔍 正在筛选标签 [{args.tag}]...")
    matched = filter_by_tag(books, args.tag)

    if not matched:
        print(f"\n⚠️  未找到标签 [{args.tag}] 下的文章。")
        print("   提示：可以用 --list-tags 参数查看所有可用标签。")
        return

    # 打印摘要
    print_summary(matched, args.tag)

    # 导出 CSV
    output_file = args.output or f"readwise_{args.tag}.csv"
    export_to_csv(matched, output_file, args.tag)


if __name__ == "__main__":
    main()
