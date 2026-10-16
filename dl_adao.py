#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 aweidao1.com 帖子并保存为 JSON。

用法:
    python dl_adao.py download <tid> [--max-pages N] [--sleep S] [-t N] [-o PATH]

主题 URL: https://aweidao1.com/t/{tid}?page={i}
输出文件: adao-{tid}.json

选择器说明（站点为 MUI 哈希类名，部分会随改版变化）:
    .mui-1bkt52b   主题作者（有效）
    .mui-o2828q    时间（已失效，兜底读取 <time datetime="...">）
    .mui-9jay18    主题/回复内容（有效）
    .mui-1b9j49x   分页（已失效，兜底解析 MuiPaginationItem-page 页码）
    .mui-1e6yec8   回复作者（有效；部分回复实际用 .mui-o8uh9i，已一并兜底）
"""

import argparse
import json
import queue
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from os import path

import requests
from BookerDownloadTool.util import request_retry
from pyquery import PyQuery as pq

BASE_URL = "https://aweidao1.com/t/{tid}?page={page}"

# 板块帖子列表：{fid} 是板块 slug（如“兄弟”），列表无总页数，递增 page 直到空页
FORUM_URL = "https://aweidao1.com/f/{fid}?page={page}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ===== 契约选择器（来自需求） =====
SEL_TOPIC_AUTHOR = ".mui-1bkt52b"       # 主题作者
SEL_TOPIC_TIME = ".mui-o2828q > time"   # 主题时间（失效，兜底见下）
SEL_CONTENT = ".mui-9jay18"             # 主题/回复内容
SEL_PAGINATION = ".mui-1b9j49x"         # 回复分页（失效，兜底见下）
SEL_REPLY_AUTHOR = ".mui-1e6yec8"       # 回复作者

# ===== 真实结构兜底 =====
SEL_CARD = ".MuiCard-root"              # 单条帖子容器
SEL_TIME_STALE = ".mui-o2828q"          # 旧时间父类（探测确认失效）
SEL_REPLY_AUTHOR_ALT = ".mui-o8uh9i"    # 部分回复作者的实际类名
SEL_PAGINATION_NEW = "nav[aria-label='pagination navigation'] .MuiPaginationItem-page"
SEL_LIST_ITEM = ".MuiCard-root"         # 列表页中的单个帖子条目卡片


def _text(node):
    """取 pyquery 节点的规范化文本；空节点返回空串。"""
    if node is None or len(node) == 0:
        return ""
    return node.text().strip()


def _nearest_card(node):
    """向上找最近的帖子卡片容器，找不到则返回节点本身。"""
    if len(node) == 0:
        return node
    cards = node.parents(SEL_CARD)
    return cards.eq(0) if len(cards) else node


def _post_author(card):
    """卡片内的作者名：契约类优先，另两种真实类兜底。"""
    if len(card) == 0:
        return ""
    for sel in (SEL_REPLY_AUTHOR, SEL_REPLY_AUTHOR_ALT, SEL_TOPIC_AUTHOR):
        el = card(sel).eq(0)
        if len(el):
            return _text(el)
    return ""


def _post_time(card):
    """卡片内的发布时间：优先读取 <time datetime>，其次取文本。"""
    if len(card) == 0:
        return ""
    t = card("time").eq(0)
    if len(t) == 0:
        return ""
    return t.attr("datetime") or _text(t)


def fetch_page(tid, page):
    url = BASE_URL.format(tid=tid, page=page)
    resp = request_retry('GET', url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return pq(resp.text)


def get_total_pages(root):
    """总页数：契约选择器取最后一个元素；失效时解析 MUI 分页的页码最大值。"""
    spec = root(SEL_PAGINATION)
    if len(spec):
        m = re.search(r"\d+", _text(spec.eq(-1)))
        if m:
            return int(m.group())
    nums = []
    for btn in root(SEL_PAGINATION_NEW).items():
        m = re.search(r"\d+", _text(btn))
        if m:
            nums.append(int(m.group()))
    return max(nums) if nums else 1


def extract_topic(soup):
    """第 1 页的主题帖信息（内容取第一个 .mui-9jay18）。"""
    content = soup(SEL_CONTENT).eq(0)
    card = _nearest_card(content)
    author = _text(soup(SEL_TOPIC_AUTHOR).eq(0)) or _post_author(card)
    # 契约时间选择器已失效，优先契约、兜底卡片内 <time datetime>
    spec_time = _text(soup(SEL_TOPIC_TIME).eq(0))
    return {
        "author": author,
        "time": spec_time or _post_time(card),
        "content": _text(content),
    }


def extract_replies(soup, page):
    """当前页的回复列表；第 1 页的第一个内容属于主题帖，跳过。"""
    contents = list(soup(SEL_CONTENT).items())
    start = 1 if page == 1 else 0
    replies = []
    for i in range(start, len(contents)):
        content = contents[i]
        card = _nearest_card(content)
        replies.append({
            "page": page,
            "author": _post_author(card),
            "time": _post_time(card),
            "content": _text(content),
        })
    return replies


class _Pacer:
    """全局节流：保证任意时刻至多每 interval 秒发起一次网络请求。"""

    def __init__(self, interval):
        self._lock = threading.Lock()
        self._interval = interval
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            target = self._next if self._next > now else now
            self._next = target + self._interval
        delay = target - now
        if delay > 0:
            time.sleep(delay)


def download_topic(tid, max_pages=None, sleep=1.0, single_page=None, threads=1):
    # session = requests.Session()
    root = fetch_page(tid, 1)

    total_pages = get_total_pages(root)
    if max_pages and max_pages < total_pages:
        total_pages = max_pages
    if single_page:
        total_pages = single_page  # 仅调试用：抓单页

    topic = extract_topic(root)
    replies = []

    pages = [p for p in range(1, total_pages + 1) if not (single_page and p != single_page)]

    # 多线程：并发抓各页，按页码顺序汇总结果
    def _tr_fetch_page(page):
        print(f'抓取页面 TID={tid}, P={page}')
        root =  fetch_page(tid, page)
        page_replies =extract_replies(root, page)
        time.sleep(sleep)
        return page_replies

    with ThreadPoolExecutor(threads) as pool:
        futures = {p: pool.submit(_tr_fetch_page, p) for p in pages}
    for page in pages:
        page_replies = futures[page].result()
        replies.extend(page_replies)
        print(f"page {page}/{total_pages}: {len(page_replies)} replies", file=sys.stderr)

    return {
        "tid": tid,
        "url": BASE_URL.format(tid=tid, page=1),
        "total_pages": total_pages,
        "topic": topic,
        "replies": replies,
    }

def download_handle(args):
    out = args.out or f"adao-{args.tid}.json"
    if path.isfile(out):
        print(f'{out} 已存在')
        return
        
    data = download_topic(
        args.tid,
        max_pages=args.max_pages,
        sleep=args.sleep,
        single_page=args.page,
        threads=args.threads,
    )

    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {len(data['replies'])} replies -> {out}", file=sys.stderr)


def fetch_list_tids(fid, page):
    """抓取板块列表一页，返回该页全部 TID；空页返回 []。"""
    url = FORUM_URL.format(fid=fid, page=page)
    resp = request_retry('GET', url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = pq(resp.text)

    tids = []
    for card in soup(SEL_LIST_ITEM).items():
        m = re.search(r"No\.?\s*(\d+)", _text(card))
        if m:
            tids.append(int(m.group(1)))
    return tids


class _TidScanner:
    """多线程递增页码抓取 TID，直到遇到空页。

    列表没有总页数，故用线程池并发抓取递增的页码；某页为空即认为
    之后所有页都为空（列表页逐页递减是单调的），据此终止并发。
    """

    def __init__(self, fid, max_threads=4, max_list_pages=None):
        self._fid = fid
        self._max = max_list_pages
        self._lock = threading.Lock()
        self._next = 1          # 下一个要抓的页码
        self._stop = None       # 已知空页的最小页码（>= stop 的页都为空）
        self._queue = queue.Queue()  # (page, tids)

    def next_page(self):
        """取下一个要抓的页码；没有则返回 None（worker 退出）。"""
        with self._lock:
            if self._stop is not None and self._next >= self._stop:
                return None
            if self._max is not None and self._next > self._max:
                return None
            page = self._next
            self._next += 1
            return page

    def submit(self, page, tids):
        with self._lock:
            if not tids and (self._stop is None or page < self._stop):
                self._stop = page
        self._queue.put((page, tids))

    def ordered_pages(self):
        """按页码升序返回 (page, tids)，丢弃 >= stop 的空页及越界页。"""
        items = []
        while not self._queue.empty():
            items.append(self._queue.get())
        items.sort(key=lambda x: x[0])
        stop = self._stop or (items[-1][0] + 1 if items else 1)
        return [(p, t) for p, t in items if p < stop]


def _scan_worker(fid, scanner):
    """单个 worker：循环取页码抓 TID，直到没有可抓的页。"""
    while True:
        page = scanner.next_page()
        if page is None:
            return
        tids = fetch_list_tids(fid, page)
        scanner.submit(page, tids)


def _save_topic(tid, sleep=1.0, max_pages=None, single_page=None):
    """下载单个帖子并保存；输出已存在则跳过（支持断点续抓）。"""
    out = f"adao-{tid}.json"
    if path.isfile(out):
        print(f"skip {out} (exists)", file=sys.stderr)
        return
    data = download_topic(tid, max_pages=max_pages, sleep=sleep, single_page=single_page)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {len(data['replies'])} replies -> {out}", file=sys.stderr)


def batch_download(fid, max_threads=4, max_list_pages=None, sleep=1.0, max_pages=None):
    """先并发抓取板块所有页的 TID，再按页逐一调用 download 逻辑下载每个帖子。"""
    scanner = _TidScanner(fid, max_threads, max_list_pages)
    with ThreadPoolExecutor(max_threads) as pool:
        for _ in range(max_threads):
            pool.submit(_scan_worker, fid, scanner)

    pages = scanner.ordered_pages()
    tids = [t for _, ts in pages for t in ts]
    print(f"[batch] {fid}: {len(pages)} list pages, {len(tids)} topics", file=sys.stderr)

    done = 0
    for page, page_tids in pages:
        print(f"[batch] downloading list page {page}: {len(page_tids)} topics", file=sys.stderr)
        for tid in page_tids:
            _save_topic(tid, sleep=sleep, max_pages=max_pages)
            done += 1
    print(f"[batch] finished: {done} topics processed", file=sys.stderr)
    return done


def batch_handle(args):
    batch_download(
        args.fid,
        max_threads=args.threads,
        max_list_pages=args.max_list_pages,
        sleep=args.sleep,
        max_pages=args.max_pages,
    )


def main():
    parser = argparse.ArgumentParser(
        prog="dl_adao",
        description="下载 aweidao1.com 帖子并保存为 JSON。",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="下载指定帖子并保存为 JSON")
    dl.add_argument("tid", type=int, help="帖子 ID")
    dl.add_argument("-o", "--out", default=None, help="输出文件路径（默认 adao-{tid}.json）")
    dl.add_argument("--max-pages", type=int, default=None, help="最多抓取页数")
    dl.add_argument("--sleep", type=float, default=1.0, help="翻页间隔秒数（默认 1.0）")
    dl.add_argument("--page", type=int, default=None, help="仅抓取单页（调试用）")
    dl.add_argument("-t", "--threads", type=int, default=4, help="并发抓取回复页的线程数（默认 1 串行）")
    dl.set_defaults(func=download_handle)

    bd = sub.add_parser("dl-batch", help="批量下载某板块的全部帖子并保存为 JSON")
    bd.add_argument("fid", help="板块 slug（如“兄弟”）")
    bd.add_argument("-t", "--threads", type=int, default=8, help="抓取 TID 列表的线程数（默认 4）")
    bd.add_argument("--max-list-pages", type=int, default=None, help="列表页抓取上限（防止无限循环，默认无限）")
    bd.add_argument("--max-pages", type=int, default=None, help="每个帖子的回复页数上限")
    bd.add_argument("--sleep", type=float, default=0, help="帖子翻页间隔秒数（默认 1.0）")
    bd.set_defaults(func=batch_handle)

    args = parser.parse_args()
    args.func(args)
    


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()