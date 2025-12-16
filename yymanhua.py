import os
from os import path
import shutil
import requests
import numpy as np
import cv2
from pyquery import PyQuery as pq
from imgyaso import pngquant_bts, \
    adathres_bts, grid_bts, noise_bts, trunc_bts, noisebw_bts
import execjs
import traceback
import sys
import re
import tempfile
import json
import uuid
from img2jb2pdf import img2jb2pdf
import subprocess as subp
from concurrent.futures import ThreadPoolExecutor
from BookerDownloadTool.util import *
import argparse
from img2pdf import convert as img2pdf

ch_pool = None
img_pool = None
exi_list = set()
    
def highlight(img):
    is_bytes = isinstance(img, bytes)
    if is_bytes:
        img = np.frombuffer(img, np.uint8)
        img = cv2.imdecode(img, cv2.IMREAD_GRAYSCALE)
    img[img >= 250] = 255
    img[img <= 5] = 0
    if is_bytes:
        img = cv2.imencode(
            '.png', img, 
            [cv2.IMWRITE_PNG_BILEVEL, 1]
        )[1]
        img = bytes(img)
    return img

def load_exi_list(args):
    global exi_list
    if not exi_list and args.exi_list and path.exists(args.exi_list):
        exi_list = set(json.loads(open(args.exi_list, encoding='utf-8').read()))

def get_info(html):
    root = pq(html)
    title = root('p.detail-info-title').text()
    author = root('.detail-info-tip>span:first-of-type>a').text().strip().replace(' ', '、')
    el_links = root('a.detail-list-form-item')
    toc = []
    for i in range(len(el_links)):
        toc.append('https://yymanhua.com' + el_links.eq(i).attr('href'))
    return {
        'title': filter_gbk(fname_escape(title)), 
        'author': filter_gbk(fname_escape(author)), 
        'toc': toc,
    }
    
def get_article(html):
    root = pq(html)
    title = root('.reader-title a:nth-of-type(2)').text().strip()
    ch = root('.reader-title a:nth-of-type(3)').text().strip()
    cid = re.search('YYMANHUA_CID=(\d+)', html).group(1)
    mid = re.search('YYMANHUA_MID=(\d+)', html).group(1)
    sign = re.search('YYMANHUA_VIEWSIGN="(\w+)"', html).group(1)
    dt = re.search('YYMANHUA_VIEWSIGN_DT="(.+?)"', html).group(1)
    total = re.search('YYMANHUA_IMAGE_COUNT=(\d+)', html).group(1)
    total = int(total)

    hdrs = default_hdrs | {
        'Referer': 'https://yymanhua.com/',
    }
    pics = []
    while len(pics) < total:
        pg = len(pics) + 1
        sc = request_retry(
            'GET', 
            f'https://yymanhua.com/m{cid}/chapterimage.ashx?cid={cid}&page={pg}&key=&_cid={cid}&_mid={mid}&_dt={dt}&_sign={sign}',
            headers=hdrs,
        ).text
        # sc = root('script:not([src])').eq(1).html()
        pics_ = execjs.eval(sc)
        pics += pics_
        # pics = list(map(lambda s: 'http://images.idmzj.com/' + s, pics))
    return {'title': fname_escape(title), 'ch': fname_escape(ch), 'pics': pics}
    
        
def process_img(img):
    return grid_bts(anime4k_auto(img))
    
def tr_download_dmzj_img(url, imgs, k):
    print(f'pic: {url}')
    hdrs = default_hdrs | {
        'Referer': 'https://yymanhua.com/',
    }
    img = request_retry('GET', url, headers=hdrs).content
    img = process_img(img)
    imgs[k] = img
    
def download_dmzj_ch_safe(url, info, odir):
    try: download_dmzj_ch(url, info, odir)
    except Exception as ex: traceback.print_exc()
    
def download_dmzj_ch(url, info, odir):
    print(f'ch: {url}')
    html = request_retry('GET', url, headers=dmzj_hdrs).text
    art = get_article(html)
    if not art['pics']:
        print('找不到页面')
        return
        
    name = f"{art['title']} - {info['author']} - {art['ch']}"
    ofname = f'{odir}/{name}.pdf'
    if name in exi_list or path.exists(ofname):
        print('文件已存在')
        return
    safe_mkdir(odir)
    
    imgs = {}
    hdls = []
    for i, img_url in enumerate(art['pics']):
        hdl = img_pool.submit(tr_download_dmzj_img, img_url, imgs, f'{i}.png')
        hdls.append(hdl)
    for h in hdls:
        h.result()
       
    img_list = [
        imgs.get(f'{i}.png', b'')
        for i in range(len(imgs))
    ]
    # pdf = img2jb2pdf(img_list)
    pdf = img2pdf(img_list)
    open(ofname, 'wb').write(pdf)
    
def init_pools(args):
    global ch_pool
    global img_pool
    if ch_pool is None:
        ch_pool = ThreadPoolExecutor(args.ch_threads)
    if img_pool is None:
        img_pool = ThreadPoolExecutor(args.img_threads)
    
def download_dmzj(args, block=True):
    id = args.id
    init_pools(args) 
    load_exi_list(args)
    url = f'https://yymanhua.com/{id}/'
    html = request_retry('GET', url, headers=dmzj_hdrs).text
    info = get_info(html)
    print(info['title'], info['author'])
    
    if len(info['toc']) == 0:
        print('已下架')
        return []
        
    hdls = []
    for url in info['toc']:
        hdl = ch_pool.submit(download_dmzj_ch_safe, url, info, args.out)
        hdls.append(hdl)
    if block:
        for h in hdls: h.result()
        hdls = []
    return hdls
    
        
def download_dmzj_safe(id, block=True):
    try: 
        return download_dmzj(id, block)
    except Exception as ex: 
        traceback.print_exc()
        return []
        
def batch_dmzj(args):
    fname = args.fname
    init_pools(args)
    load_exi_list(args)
    lines = open(fname, encoding='utf-8').read().split('\n')
    lines = filter(None, map(lambda x: x.strip(), lines))
    hdls = []
    for id in lines:
        args.id = id
        part = download_dmzj_safe(args, False)
        hdls += part
    for h in hdls: h.result()
        
def fetch_dmzj(args):
    fname, st, ed = args.fname, args.start, args.end
    f = open(fname, 'a')
    
    i = 1
    for i in range(st, ed):
        print(f'page: {i}')
        url = f'https://yymanhua.com/manga-list-0-0-2-p{i}/'
        res = request_retry('GET', url, headers=default_hdrs).text
        # j = json.loads(res[2:-2])
        rt = pq(res)
        el_links = rt('h2.title>a')
        ids = [pq(el).attr('href').replace('/', '') for el in el_links]
        if not ids: break
        for id in ids:
            print(id)
            f.write(id + '\n')
            f.flush()
        
    f.close()
        
def main():
    parser = argparse.ArgumentParser(prog="BookerPubTool", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.set_defaults(func=lambda x: parser.print_help())
    subparsers = parser.add_subparsers()
    dl_parser = subparsers.add_parser("download")
    dl_parser.add_argument("id")
    dl_parser.add_argument("-ct", '--ch-threads', type=int, default=4)
    dl_parser.add_argument("-it", '--img-threads', type=int, default=4)
    dl_parser.add_argument("-l", '--exi-list', type=str, default=None)
    dl_parser.add_argument("-o", '--out', type=str, default='.')
    dl_parser.set_defaults(func=download_dmzj)

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("fname")
    fetch_parser.add_argument("-s", '--start', type=int, default=1)
    fetch_parser.add_argument("-e", '--end', type=int, default=1_000_000)
    fetch_parser.set_defaults(func=fetch_dmzj)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("fname")
    batch_parser.add_argument("-ct", '--ch-threads', type=int, default=4)
    batch_parser.add_argument("-it", '--img-threads', type=int, default=4)
    batch_parser.add_argument("-l", '--exi-list', type=str, default=None)
    batch_parser.add_argument("-o", '--out', type=str, default='.')
    batch_parser.set_defaults(func=batch_dmzj)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__': main()