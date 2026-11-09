#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""douban_book_list_fetch.py — 豆瓣图书列表抓取(搜索 + 标签),带腾讯点选验证码自动求解。

功能
  1. 搜索采集: search.douban.com/book/subject_search?search_text=<kw>&cat=1001&start=<i>0
     解析 window.__DATA__ 中的 search_subject 条目。
  2. 标签采集: book.douban.com/tag/<tag>?start=<n>&type=T
  3. 详情采集: 逐个进入 subject 页,提取书名 + ISBN,仅保留 9787 开头。
  4. 验证码: 被引到 /misc/sorry 时自动求解腾讯点选验证码(逆向自 dy-ele.js):
       - PoW: 找 n 使 md5(prefix+n) == pow_cfg.md5,pow_answer = prefix+n
       - collect/eks: 本地 node 运行豆瓣版 tdc.js (jsdom)
       - ans: 精灵图三格模板匹配 -> 背景图自然坐标的标记中心
       - 成功后 POST /misc/sorry 换取放行 cookie
  5. 断点续跑: 全部进度落盘,可反复运行。

用法
  python douban_book_list_fetch.py --search AI --out ai_zh_books.json
  python douban_book_list_fetch.py --tags 计算机,编程,算法 --out cs-zh-books.json

依赖
  pip install requests curl_cffi browser_cookie3 opencv-python numpy
  验证码 TDC 指纹需要 node + jsdom,以及 D:/src/doctool/tdc_collect_douban.js + tdc_douban.js
  (可用环境变量 TDC_DIR 覆盖目录)。
"""
import argparse
import base64
import hashlib
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse

import requests

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CAPTCHA_HOST = "https://turing.captcha.qcloud.com"
CAPTCHA_AID = "2003459237"
SORRY_POST = "https://www.douban.com/misc/sorry"
TDC_DIR = os.environ.get("TDC_DIR", r"D:\src\doctool")


# --------------------------------------------------------------------------- #
# 会话与 cookie
# --------------------------------------------------------------------------- #
def firefox_cookies(domain="douban.com"):
    if browser_cookie3 is None:
        return []
    try:
        return [{"name": c.name, "value": c.value, "domain": c.domain, "path": "/"}
                for c in browser_cookie3.firefox(domain_name=domain)]
    except Exception as e:
        print(f"[!] 读取浏览器 cookie 失败: {e}", flush=True)
        return []


class DoubanClient:
    """豆瓣会话: curl_cffi(Chrome 指纹) + Firefox cookie,被封时自动解验证码。"""

    def __init__(self, impersonate="chrome", auto_captcha=True):
        self.imp = impersonate
        self.auto_captcha = auto_captcha
        self.blocked = 0
        self._new_session()

    def _new_session(self):
        if cr is not None:
            s = cr.Session(impersonate=self.imp)
        else:  # 退化到 requests(可能被 403)
            s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        for c in firefox_cookies():
            try:
                s.cookies.set(c["name"], c["value"], domain=c["domain"])
            except Exception:
                pass
        self.s = s

    @staticmethod
    def is_blocked(url, text):
        return ("misc/sorry" in str(url)) or ("error code" in text[:300]) \
            or ('id="sec"' in text and "sha512" in text)

    def get(self, url, tries=3, timeout=25, **kw):
        for k in range(tries):
            try:
                r = self.s.get(url, timeout=timeout, **kw)
            except Exception as e:
                print(f"   [!] {type(e).__name__} {url[:70]}", flush=True)
                time.sleep(3 * (k + 1))
                continue
            text = r.text
            if self.is_blocked(r.url, text):
                print(f"[!] 被拦截 -> {str(r.url)[:90]}", flush=True)
                self.blocked += 1
                if self.auto_captcha and solve_douban_captcha(self.s, target=url):
                    continue
                return None
            if r.status_code == 200:
                return text
            print(f"   [!] HTTP {r.status_code} {url[:70]}", flush=True)
            time.sleep(3 * (k + 1))
        return None

    def post(self, url, data=None, timeout=25, **kw):
        try:
            return self.s.post(url, data=data, timeout=timeout, **kw)
        except Exception as e:
            print(f"   [!] POST 失败 {url[:70]}: {e}", flush=True)
            return None


# --------------------------------------------------------------------------- #
# 腾讯点选验证码求解(逆向自 turing.captcha.qcloud.com SDK / dy-ele.js)
# --------------------------------------------------------------------------- #
def _tdc_collect():
    """node 运行豆瓣版 tdc.js,返回 {collect, info, tokenid}。"""
    js = os.path.join(TDC_DIR, "tdc_collect_douban.js")
    if not os.path.exists(js):
        raise RuntimeError(f"缺少 {js} (TDC 指纹采集器)")
    p = subprocess.run(["node", js], capture_output=True, text=True,
                       cwd=TDC_DIR, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("tdc_collect_douban.js 失败: " + (p.stderr or "")[:200])
    return json.loads(p.stdout)


def pow_solve_exact(prefix, target_md5, max_tries=50_000_000):
    """官方 worker 算法: md5(prefix+n) == pow_cfg.md5(完整十六进制精确匹配)。"""
    tb = target_md5.strip().lower().encode()
    for n in range(max_tries):
        if hashlib.md5((prefix + str(n)).encode()).hexdigest().encode() == tb:
            return n
    return None


def _prehandle(entry_url):
    p = {"aid": CAPTCHA_AID, "protocol": "https", "accver": "1", "showtype": "popup",
         "ua": base64.b64encode(UA.encode()).decode(), "noheader": "1", "fb": "0",
         "isJsVersion": "1", "clientype": "2", "lang": "zh-cn", "entry_url": entry_url,
         "cap_cd": "", "uid": "", "subsid": "1", "callback": "_",
         "js": "/tcaptcha-frame.211eaaf4.js"}
    r = requests.get(CAPTCHA_HOST + "/cap_union_prehandle", params=p,
                     headers={"User-Agent": UA, "Referer": entry_url}, timeout=20)
    txt = r.text.strip()
    return json.loads(txt[2:-1] if txt.startswith("_(") else txt)


def _match3(bg, sp, scale):
    """精灵图按 scale 放大后切三格,在背景图中模板匹配。"""
    import cv2
    s2 = cv2.resize(sp, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    w = s2.shape[1]
    cell, pad = w // 3, int(w * 0.05)
    cells = [s2[:, pad:cell], s2[:, cell:2 * cell], s2[:, 2 * cell:w - pad]]
    locs, scores = [], []
    for c in cells:
        res = cv2.matchTemplate(bg, c, cv2.TM_CCOEFF_NORMED)
        _, sc, _, loc = cv2.minMaxLoc(res)
        locs.append(loc)
        scores.append(sc)
    return locs, scores


def _solve_captcha_challenge(sess_http, entry_url, ck, original_url):
    """完整点选流程: prehandle -> 定位 -> TDC -> PoW -> verify -> POST /misc/sorry。"""
    j = _prehandle(entry_url)
    if j.get("state") != 1:
        print("[!] prehandle state", j.get("state"), flush=True)
        return False
    d = j.get("data", {})
    dyn = d.get("dyn_show_info", {})
    bg_cfg = dyn.get("bg_elem_cfg", {})
    img_url, sprite_url = bg_cfg.get("img_url", ""), dyn.get("sprite_url", "")
    pow_cfg = d.get("comm_captcha_cfg", {}).get("pow_cfg", {})
    if not (img_url and sprite_url):
        print("[!] prehandle 缺少图元", flush=True)
        return False

    import cv2
    import numpy as np
    hdr = {"User-Agent": UA, "Referer": entry_url}
    bg = cv2.imdecode(np.asarray(bytearray(requests.get(CAPTCHA_HOST + img_url, headers=hdr).content), dtype="uint8"), cv2.IMREAD_COLOR)
    sp = cv2.imdecode(np.asarray(bytearray(requests.get(CAPTCHA_HOST + sprite_url, headers=hdr).content), dtype="uint8"), cv2.IMREAD_COLOR)
    if bg is None or sp is None:
        print("[!] 验证码图片下载失败", flush=True)
        return False

    bw, bh = bg_cfg.get("size_2d", [672, 480])
    ah, aw = bg.shape[:2]
    sx, sy = bw / aw, bh / ah
    best = None
    for sc in (0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.75, 2.0):
        locs, scores = _match3(bg, sp, sc)
        avg = sum(scores) / 3
        if best is None or avg > best[0]:
            best = (avg, sc, locs, scores)
    _, scale, locs, scores = best
    print(f"[*] 缩放 {scale} 匹配分 {[round(x, 3) for x in scores]}", flush=True)
    tw, th = 170 * scale / 3, 50 * scale
    pos = lambda loc: (int((loc[0] + tw / 2) * sx), int((loc[1] + th / 2) * sy))
    c1, c2, c3 = pos(locs[0]), pos(locs[1]), pos(locs[2])
    print(f"[*] 点击坐标 {c1} {c2} {c3}", flush=True)

    tdc = _tdc_collect()
    collect = tdc["collect"]                      # 已 URL 编码的密文
    eks = tdc["info"]
    tlg = len(urllib.parse.unquote(collect))      # 官方: tlg = len(decodeURIComponent(collect))

    ans = json.dumps([
        {"elem_id": 1, "type": "DynAnswerType_POS", "data": f"{c1[0]},{c1[1]}"},
        {"elem_id": 2, "type": "DynAnswerType_POS", "data": f"{c2[0]},{c2[1]}"},
        {"elem_id": 3, "type": "DynAnswerType_POS", "data": f"{c3[0]},{c3[1]}"},
    ], separators=(",", ":"))

    params = {"collect": collect, "tlg": tlg, "eks": eks, "sess": j["sess"], "ans": ans}
    prefix, target = pow_cfg.get("prefix", ""), pow_cfg.get("md5", "")
    if prefix and target:
        t0 = time.time()
        n = pow_solve_exact(prefix, target)
        pow_time = int((time.time() - t0) * 1000)
        if n is None:
            print("[!] PoW 未解出", flush=True)
            return False
        params["pow_answer"] = prefix + str(n)    # 官方格式: prefix + nonce
        params["pow_calc_time"] = pow_time
        print(f"[*] PoW n={n} ({pow_time}ms)", flush=True)

    r = requests.post(CAPTCHA_HOST + "/cap_union_new_verify", data=params,
                      headers={"User-Agent": UA, "Referer": entry_url}, timeout=25)
    try:
        vj = r.json()
    except Exception:
        print("[!] verify 响应异常", r.text[:120], flush=True)
        return False
    if str(vj.get("errorCode")) != "0":
        print(f"[!] verify 失败 errorCode={vj.get('errorCode')}", flush=True)
        return False
    ticket, randstr = vj.get("ticket"), vj.get("randstr")
    print(f"[*] ticket={str(ticket)[:24]}… randstr={randstr}", flush=True)

    r2 = sess_http.post(SORRY_POST,
                        data={"ck": ck, "ticket": ticket, "randstr": randstr,
                              "original-url": original_url},
                        timeout=25, allow_redirects=True)
    print(f"[*] 提交 /misc/sorry -> {r2.status_code}", flush=True)
    return True


def solve_douban_captcha(session, target):
    """当前会话被 /misc/sorry 拦截时调用;成功返回 True。"""
    for attempt in range(3):
        try:
            r = session.get(target, timeout=25)
            page_url, text = str(r.url), r.text
            if not DoubanClient.is_blocked(page_url, text):
                return True
            m_ck = re.search(r'name="ck" value="([^"]*)"', text)
            m_ou = re.search(r'name="original-url" value="([^"]*)"', text)
            if not (m_ck and m_ou):
                print("[!] 验证页缺少 ck/original-url", flush=True)
                return False
            if _solve_captcha_challenge(session, page_url, m_ck.group(1), m_ou.group(1)):
                chk = session.get(target, timeout=25)
                if not DoubanClient.is_blocked(str(chk.url), chk.text):
                    print("[✓] 验证码通过,已放行", flush=True)
                    return True
        except Exception as e:
            print(f"[!] 验证码流程异常: {type(e).__name__} {e}", flush=True)
            if "node" in str(e).lower() or "tdc" in str(e).lower():
                print("[!] 需要 node+jsdom 与 TDC_DIR/tdc_collect_douban.js", flush=True)
                return False
        time.sleep(3)
    return False


# --------------------------------------------------------------------------- #
# 页面解析
# --------------------------------------------------------------------------- #
def parse_search_subjects(text):
    """从 subject_search 页面的 window.__DATA__ 提取图书条目。"""
    i = text.find("window.__DATA__")
    if i < 0:
        return []
    st = text.find("{", i)
    try:
        d, _ = json.JSONDecoder().raw_decode(text[st:])
    except Exception:
        return []
    err = d.get("error_info") or ""
    if ("频繁" in err or "超出" in err):
        raise RuntimeError("RATE_LIMITED")
    return [{"title": it.get("title", ""), "url": it["url"]}
            for it in d.get("items", [])
            if it.get("tpl_name") == "search_subject" and it.get("url")]


def parse_tag_subjects(text):
    out = []
    for blk in re.findall(r'<li class="subject-item">([\s\S]*?)</li>', text):
        m = re.search(r"subject/(\d+)/", blk)
        if not m:
            continue
        sid = m.group(1)
        mt = re.search(r'<a href="https://book\.douban\.com/subject/' + sid +
                       r'/" title="([^"]*)"', blk)
        out.append({"title": html.unescape(mt.group(1)).strip() if mt else "",
                    "url": f"https://book.douban.com/subject/{sid}/"})
    return out


def parse_detail(text, fallback=""):
    m = re.search(r'property="v:itemreviewed">(.*?)</span>', text, re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else None
    isbn = None
    m = re.search(r'"isbn"\s*:\s*"([^"]+)"', text)
    if m:
        isbn = m.group(1)
    if not isbn:
        m = re.search(r'<span class="pl">\s*ISBN[:\s]*</span>\s*([0-9Xx\-]+)', text)
        if m:
            isbn = m.group(1)
    if not title and not isbn:
        return None
    isbn = re.sub(r"[^0-9Xx]", "", isbn or "")
    return {"title": (title or fallback).strip(), "isbn": isbn}


# --------------------------------------------------------------------------- #
# 断点存取
# --------------------------------------------------------------------------- #
def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def save_json(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sleep_range(rng):
    a, b = rng
    time.sleep(random.uniform(a, b))


# --------------------------------------------------------------------------- #
# 采集阶段
# --------------------------------------------------------------------------- #
def phase_search(client, kw, cache_urls, cache_prog, max_start, delay):
    urls, seen = [], set()
    for it in cache_urls:
        if it["url"] not in seen:
            seen.add(it["url"])
            urls.append(it)
    resume = int(cache_prog.get("next_start", 0)) if cache_prog else 0
    print(f"[*] 搜索: 缓存 {len(urls)} 条, 从 start={resume} 继续", flush=True)
    empty = fail = 0
    for start in range(resume, max_start + 1, 10):
        url = ("https://search.douban.com/book/subject_search?"
               f"search_text={urllib.parse.quote(kw)}&cat=1001&start={start}")
        try:
            text = client.get(url)
        except RuntimeError as e:  # RATE_LIMITED
            text = None
        if not text:
            fail += 1
            print(f"[*] start={start} 失败({fail})", flush=True)
            if fail >= 5:
                print("[!] 连续失败过多, 结束搜索阶段", flush=True)
                break
            time.sleep(30)
            continue
        fail = 0
        items = parse_search_subjects(text)
        if not items:
            empty += 1
            print(f"[*] start={start} 空 (连续 {empty})", flush=True)
            if empty >= 2:
                print("[*] 搜索到头", flush=True)
                break
            time.sleep(10)
            continue
        empty = 0
        new = 0
        for it in items:
            if it["url"] not in seen:
                seen.add(it["url"])
                urls.append(it)
                new += 1
        save_json(cache_urls, urls)
        save_json(cache_prog, {"next_start": start + 10})
        print(f"[*] start={start}: {len(items)} 条, 新增 {new}, 累计 {len(urls)}", flush=True)
        sleep_range(delay)
    return urls


def phase_tags(client, tags, cache_urls, max_pages, delay):
    links, seen = [], set()
    for it in cache_urls:
        if it["url"] not in seen:
            seen.add(it["url"])
            links.append(it)
    print(f"[*] 标签: 缓存 {len(links)} 条", flush=True)
    for tag in tags:
        empty = 0
        for start in range(0, max_pages * 20, 20):
            url = ("https://book.douban.com/tag/" + urllib.parse.quote(tag) +
                   f"?start={start}&type=T")
            text = client.get(url)
            if not text:
                break
            items = parse_tag_subjects(text)
            if not items:
                break
            new = 0
            for it in items:
                if it["url"] not in seen:
                    seen.add(it["url"])
                    links.append(it)
                    new += 1
            save_json(cache_urls, links)
            if start % 100 == 0:
                print(f"[*] tag={tag} start={start}: 本页 {len(items)}, 新增 {new}, 累计 {len(links)}", flush=True)
            if new == 0:
                empty += 1
                if empty >= 2:
                    break
            else:
                empty = 0
            sleep_range(delay)
    return links


def phase_details(client, links, out_path, checked_path, delay, only_9787=True):
    books = load_json(out_path, [])
    have = {b.get("url") for b in books}
    checked = set(load_json(checked_path, []))
    todo = [x for x in links if x["url"] not in checked]
    print(f"[*] 详情: 链接 {len(links)}, 待抓 {len(todo)}, 已有书 {len(books)}", flush=True)
    for n, item in enumerate(todo, 1):
        text = client.get(item["url"])
        if text is None:
            print(f"[{n}/{len(todo)}] FAIL {item['url']}", flush=True)
            continue
        b = parse_detail(text, item.get("title", ""))
        checked.add(item["url"])
        if b and (not only_9787 or b["isbn"].startswith("9787")):
            if item["url"] not in have:
                b["url"] = item["url"]
                books.append(b)
                have.add(item["url"])
            print(f"[{n}/{len(todo)}] OK  {b['title']}  {b['isbn']}", flush=True)
        if n % 25 == 0:
            save_json(out_path, books)
            save_json(checked_path, sorted(checked))
            print(f"  … 检查点: 书 {len(books)}, 已查 {len(checked)}", flush=True)
        sleep_range(delay)
    save_json(out_path, books)
    save_json(checked_path, sorted(checked))
    print(f"[✓] 详情完成: 书 {len(books)}, 已查 {len(checked)}", flush=True)
    return books


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="豆瓣图书列表抓取(9787 过滤)")
    ap.add_argument("--search", default="", help="搜索关键词, 如 AI")
    ap.add_argument("--tags", default="", help="逗号分隔的标签, 如 计算机,编程")
    ap.add_argument("--out", default="douban_books.json", help="输出 JSON 路径")
    ap.add_argument("--max-search", type=int, default=3000, help="搜索 start 上限")
    ap.add_argument("--max-tag-pages", type=int, default=50, help="每标签最大页数(20条/页)")
    ap.add_argument("--search-delay", default="20,30", help="搜索页间隔秒区间")
    ap.add_argument("--tag-delay", default="1,2", help="标签页间隔秒区间")
    ap.add_argument("--detail-delay", default="1.5,2.5", help="详情页间隔秒区间")
    ap.add_argument("--no-captcha", action="store_true", help="关闭验证码自动求解")
    args = ap.parse_args()

    if not args.search and not args.tags:
        ap.error("需要 --search 或 --tags 至少一个")

    stem = os.path.splitext(args.out)[0]
    search_cache = stem + ".search_urls.json"
    search_prog = stem + ".search_progress.json"
    tag_cache = stem + ".tag_urls.json"
    checked_cache = stem + ".checked.json"

    def rng(s):
        a, b = s.split(",")
        return float(a), float(b)

    client = DoubanClient(auto_captcha=not args.no_captcha)
    links = []
    if args.search:
        links = phase_search(client, args.search,
                             load_json(search_cache, []), load_json(search_prog, {}),
                             args.max_search, rng(args.search_delay))
    if args.tags:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        tag_links = phase_tags(client, tags, load_json(tag_cache, []),
                               args.max_tag_pages, rng(args.tag_delay))
        merged, seen = list(links), {x["url"] for x in links}
        for it in tag_links:
            if it["url"] not in seen:
                seen.add(it["url"])
                merged.append(it)
        links = merged

    print(f"[*] 链接总数: {len(links)}", flush=True)
    phase_details(client, links, args.out, checked_cache, rng(args.detail_delay))
    print(f"[✓] 输出: {args.out} ({len(load_json(args.out, []))} 本)", flush=True)


if __name__ == "__main__":
    main()
