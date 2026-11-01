# -*- coding: utf-8 -*-
"""
cnblogs 博客园自动发帖脚本（requests 直连 API）

抓包结论（i.cnblogs.com/posts/edit 编辑器前端 JS 逆向）：
  * 登录态: 浏览器 cookie 中的 .Cnblogs.AspNetCore.Cookies（browser_cookie3 直读）
  * 防伪:   GET /api/xsrf -> {requestToken}，写入请求头 X-XSRF-TOKEN
  * 发帖:   POST /api/posts     body = 平铺 JSON（表单全字段），返回 {id, url}
  * 分类:   GET /api/v2/blog-category-types/1/categories  -> [{categoryId,title,...}]
  * 图片:   三步上传
            1. POST /api/images/{categoryId}  {fileName,sizeInBytes,visible,title} -> uploadToken
            2. POST //upload.cnblogs.com/api/v1/gallery/images/?token=...  multipart image -> replyToken
            3. POST /api/images/save/?token={replyToken} 同 body -> 完成（成功后返回图片对象）
  * 删除:   DELETE /api/posts/{id}

依赖: pip install requests browser_cookie3
用法示例:
  python cnblogs_post.py "C:/Users/Administrator/Desktop/topost2/xxx.md"
  python cnblogs_post.py file.md --cate "ApacheCN" --tags a,b -b chrome --publish
  python cnblogs_post.py file.md --images       # 上传 md 里相对路径引用的本地图片
"""
import re
import os
import sys
import json
import argparse
import datetime as _dt
import traceback
from os import path
from urllib.parse import urljoin
from BookerDownloadTool.util import cookie_dict_to_str
from BookerDownloadTool.ext_cookie import extract_cookies_multi_browsers
from BookerMarkdownTool.util import get_md_title

import requests

config = {
    'api_base': 'https://i.cnblogs.com',
    'upload_base': 'https://upload.cnblogs.com',
    'post_type': 1,                       # 1=blogPost 2=article 32=news 128=diary
    'editor_id': 'cnblogs-markdown-6',    # 编辑器标识
    'post_url': '/api/posts',
    'xsrf_url': '/api/xsrf',
    'category_url': '/api/v2/blog-category-types/{type}/categories',
    'image_url': '/api/images/{categoryId}',          # save 时尾部拼 /save/?token=...
    'image_save_url': '/api/images/{categoryId}/save/?token={token}',
    'timeout': 30,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
}

RE_TITLE = re.compile(r'^#+\s+(.+?)$', re.M)
RE_IMG = re.compile(r'!\[([^\]]*)\]\((?!https?://|data:)([^)\s]+)(?:\s+"[^"]*")?\)')


class CnblogsError(Exception):
    pass


# ---------------------------------------------------------------------------
# 登录态 / 会话
# ---------------------------------------------------------------------------

def make_session(cookies: dict) -> requests.Session:
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        'User-Agent': config['user_agent'],
        'Referer': urljoin(config['api_base'], '/posts/edit'),
        'Accept': 'application/json, text/plain, */*',
    })
    # 刷新防伪 token
    r = s.get(urljoin(config['api_base'], config['xsrf_url']), timeout=config['timeout'])
    r.raise_for_status()
    tok = r.json().get('requestToken')
    if not tok:
        raise CnblogsError('获取 XSRF token 失败: ' + r.text[:300])
    s.headers['X-XSRF-TOKEN'] = tok
    return s


# ---------------------------------------------------------------------------
# Markdown 解析
# ---------------------------------------------------------------------------

def parse_md(fname):
    """返回 (title, body)。标题取第一个 # 行，正文为去掉标题行后的其余内容。"""
    with open(fname, encoding='utf-8') as f:
        text = f.read()
    title, span = get_md_title(text)
    if title is None:
        title = path.splitext(path.basename(fname))[0]
        body = text
    else:
        body = text[span[1]:].lstrip('\n')
        if body.startswith('\n'):
            body = body[1:]
    return title, body.strip()


def upload_local_images(s, fname, body, category_id=0, visible=True):
    """把 body 中相对路径引用的本地图片上传到 cnblogs 图床，URL 就地替换。

    图片引用形如 ![](img/xxx.png)，相对 md 文件所在目录。
    """
    base_dir = path.dirname(path.abspath(fname))

    def repl(m):
        alt, rel = m.group(1), m.group(2)
        img_path = path.join(base_dir, rel)
        if not path.isfile(img_path):
            print(f'[图片] 跳过(文件不存在): {rel}')
            return m.group(0)
        fname_ = path.basename(rel)
        size = path.getsize(img_path)
        try:
            r = s.post(urljoin(config['api_base'], config['image_url'].format(categoryId=category_id)),
                       json={'fileName': fname_, 'sizeInBytes': size, 'visible': visible, 'title': alt or fname_},
                       timeout=config['timeout'])
            r.raise_for_status()
            upload_token = r.json().get('uploadToken')
            if not upload_token:
                raise CnblogsError(f'申请上传 token 失败: {r.text[:300]}')
            # 上传二进制
            with open(img_path, 'rb') as f:
                up = s.post(config['upload_base'] + '/api/v1/gallery/images/?token=' + upload_token,
                            files={'image': (fname_, f, 'application/octet-stream')},
                            timeout=config['timeout'])
            up.raise_for_status()
            reply_token = (up.json().get('replyToken')) or (up.json().get('ReplyToken'))
            # 确认保存
            sv = s.post(urljoin(config['api_base'], config['image_save_url'].format(categoryId=category_id, token=reply_token)),
                       json={'fileName': fname_, 'sizeInBytes': size, 'visible': visible, 'title': alt or fname_},
                       timeout=config['timeout'])
            sv.raise_for_status()
            img = sv.json()
            url = img.get('url') or img.get('fullUrl') or img.get('imageUrl') or ''
            print(f'[图片] {rel} -> {url}')
            return f'![{alt}]({url})'
        except Exception as e:
            print(f'[图片] 上传失败 {rel}: {e}')
            return m.group(0)

    return RE_IMG.sub(repl, body)


# ---------------------------------------------------------------------------
# 数据查询
# ---------------------------------------------------------------------------
def list_categories(s, post_type=1):
    """返回 [(categoryId, title)]，可按名字匹配。"""
    r = s.get(urljoin(config['api_base'], config['category_url'].format(type=post_type)),
              timeout=config['timeout'])
    r.raise_for_status()
    cats = r.json().get('categories') or []
    return [(c['categoryId'], c['title']) for c in cats]


def resolve_category_ids(s, names, post_type=1):
    """把分类名列表转成 categoryId 列表；未知名字直接忽略并提醒。"""
    name_set = set(x.strip() for x in names if x.strip())
    if not name_set:
        return []
    cats = list_categories(s, post_type)
    id_map = {title.strip(): cid for cid, title in cats}
    out, missing, dup_titles = [], set(), set()
    for name in name_set:
        if name in id_map:
            if id_map[name] in out:
                dup_titles.add(name)
            else:
                out.append(id_map[name])
        else:
            missing.add(name)
    if missing:
        print(f'[分类] 未找到: {missing}（可选: ' + ', '.join(t for _, t in cats[:15]) + ' ...）')
    if dup_titles:
        print(f'[分类] 重名分类仅取第一个: {dup_titles}')
    return out


# ---------------------------------------------------------------------------
# 发帖
# ---------------------------------------------------------------------------
def build_payload(title, body, category_ids=None, tags=None, publish=False,
                  entry_name='', description='', featured_image=''):
    now = _dt.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    is_published = bool(publish)
    return {
        'title': title,
        'postBody': body,
        'entryName': entry_name,
        'description': description,
        'featuredImage': featured_image,
        'isMarkdown': True,
        'isDraft': not is_published,          # 草稿状态
        'isPublished': is_published,          # 是否发布（公开）
        'datePublished': now,                 # 必须为有效 DateTime，不能为 null
        'publishAt': None,                    # 定时发布，默认不启用
        'categoryIds': category_ids or [],
        'tags': list(tags or []),
        'allowComments': True,
        'displayOnHomePage': True,            # 博客首页展示
        'removeScript': True,                 # 过滤脚本，防 XSS
        'isOnlyForRegisterUser': False,
        'isContributeToImpressiveBugActivity': False,
    }


def post(s, title, body, category_ids=None, tags=None, publish=False, **kw):
    payload = build_payload(title, body, category_ids, tags, publish, **kw)
    r = s.post(urljoin(config['api_base'], config['post_url']),
               data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
               headers={'Content-Type': 'application/json'},
               timeout=config['timeout'])
    if r.status_code == 200:
        data = r.json()
        return data.get('id'), data.get('url'), payload
    # 400 时把服务端错误提示带出来
    try:
        errs = r.json().get('errors', [])
    except Exception:
        errs = [r.text[:300]]
    raise CnblogsError(f'发布失败 HTTP {r.status_code}: {"; ".join(str(e) for e in errs)}')


def delete_post(s, post_id):
    r = s.delete(urljoin(config['api_base'], config['post_url']) + f'/{post_id}', timeout=config['timeout'])
    if r.status_code not in (200, 204):
        try:
            errs = r.json().get('errors', [])
        except Exception:
            errs = [r.text[:200]]
        raise CnblogsError(f'删除失败 HTTP {r.status_code}: {errs}')
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description='博客园 cnblogs 自动发帖（requests 直连 /api/posts，cookie 取自本地浏览器）')
    p.add_argument('fname', nargs='?', help='Markdown 文件或目录路径（缺省则仅打印各分类，供 --cate 参考）')
    p.add_argument('-b', '--browser', default='firefox', choices=['firefox', 'chrome', 'edge'],
                   help='用哪个浏览器读 cookie（需在其中登录过博客园）')
    p.add_argument('-c', '--cate', action='append', default=[], help='分类名，可多次指定')
    p.add_argument('-t', '--tags', default='', help='标签，逗号分隔，如 "a,b"')
    p.add_argument('--no-publish', action='store_true', help='不直接发布（存草稿）')
    p.add_argument('--entry-name', default='', help='友好地址名（字母数字-_~，不能全数字）')
    p.add_argument('--summary', default='', help='摘要描述（默认空，由博客园自动截取）')
    p.add_argument('--featured-image', default='', help='摘要图 URL')
    p.add_argument('--images', action='store_true', help='上传 md 中相对路径引用的本地图片并替换 URL')
    p.add_argument('--title', default=None, help='覆盖标题（默认取 md 第一个 # 行）')
    p.add_argument('--dry-run', action='store_true', help='只打印将提交的 payload，不发帖')
    # p.add_argument('--delete', type=int, default=None, metavar='POST_ID', help='删除指定 id 的文章（测试清理用）')
    return p.parse_args(argv)

def post_one(args, s):
    title, body = parse_md(args.fname)
    if args.title:
        title = args.title
    if args.images:
        body = upload_local_images(s, args.fname, body)

    category_ids = resolve_category_ids(s, args.cate)
    tags = [x.strip() for x in args.tags.split(',') if x.strip()]

    payload = build_payload(title, body, category_ids, tags, not args.no_publish,
                            entry_name=args.entry_name, description=args.summary,
                            featured_image=args.featured_image)
    print(f'[Info] 标题: {title}')
    print(f'[Info] 分类: {category_ids}  标签: {tags}  发布: {not args.no_publish}  正文: {len(body)} 字符')
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    post_id, url, _ = post(s, title, body, category_ids, tags, not args.no_publish,
                           entry_name=args.entry_name, description=args.summary,
                           featured_image=args.featured_image)
    status = '已发布' if not args.no_publish else '草稿'
    print(f'[OK] {status}: id={post_id}  url={url}')

def main(argv=None):
    args = parse_args(argv)

    s = make_session(extract_cookies_multi_browsers('cnblogs.com'))

    '''
    if args.delete is not None:
        delete_post(s, args.delete)
        print(f'[OK] 已删除文章 id={args.delete}')
        return
    '''
    
    if not args.fname:
        cats = list_categories(s)
        print('可用分类:')
        for cid, title in cats:
            print(f'  {cid}\t{title}')
        return

    fnames = [args.fname] if path.isfile(args.fname) else [
        path.join(args.fname, f) 
        for f in os.listdir(args.fname)
        if f.endswith('.md')
    ]

    for f in fnames:
        args.fname = f
        try:
            post_one(args, s)
            os.remove(f)
        except KeyboardInterrupt:
            raise
        except CnblogsError as e:
            print(f'[错误] {e}', file=sys.stderr)
            if '已存在' in str(e):
                os.remove(f)
        except:
            traceback.print_exc()


if __name__ == '__main__':
    main()
