from BookerEpubTool.util import *
import sys
import os
from os import path
from pyquery import PyQuery as pq
from BookerMarkdownTool.tomd import tomd
from BookerMarkdownTool.util import *
import re


def main():
    dir = sys.argv[1]
    odir = sys.argv[2]
    if not path.isdir(odir + '/img'):
        os.makedirs(odir + '/img')
    epubs = [f for f in os.listdir(dir) if f.endswith('.epub')]
    for f in epubs:
        print(f)
        f = path.join(dir, f)
        fdict = read_zip(f)
        html_dict = {path.basename(f):data for f, data in fdict.items() if f.endswith('.html') }
        img_dict = {path.basename(f):data for f, data in fdict.items() if is_pic(f) }
        for f, html in html_dict.items():
            print(f)
            html = html.decode('utf8', 'ignore')
            html = rm_xml_header(html)
            rt = pq(html)
            title = rt('h1').eq(0).text().strip()
            if not re.search(r'CVE-\d+-\d+', title, flags=re.I):
                continue
            print(title)
            imgs = [
                pq(el).attr('src')
                for el in rt('img')
            ]
            imgs = [path.basename(i) for i in imgs if i.startswith('../Images')]
            md = tomd(html)
            md_fname = path.join(
                odir, re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '-', title) + '.md'
            )
            open(md_fname, 'w', encoding='utf8').write(md)
            for i in imgs:
                print(i)
                img_fname = path.join(
                    odir, 'img', i
                )
                open(img_fname, 'wb').write(img_dict.get(i, b''))



if __name__ == '__main__': main()