from BookerEpubTool.util import *
from BookerMarkdownTool.tomd import tomd
import argparse
from pyquery import PyQuery as pq
from concurrent.futures import ThreadPoolExecutor
# from concurrent.futures import ProcessPoolExecutor
import time
import os

def epub2md(args):
    if not args.fname.endswith('.epub'):
        raise ValueError('请提供 EPUB 文件')
        
    ofname = path.join(args.dir, args.fname[:-5] + '.md')
    if path.isfile(ofname):
        print(f'{args.fname} 已转换')
        return
    fdict = read_zip(args.fname)
    # _, ncx = read_opf_ncx(fdict)
    htmls = [
        cont.decode('utf8', 'ignore')
        for name, cont in fdict.items()
        if name.endswith('.html')
    ]

    html = ''.join(htmls).replace('../Images', 'img')
    md = tomd(html)
    open(ofname, 'w', encoding='utf8').write(md)

    pics = {
        path.basename(name):cont
        for name, cont in fdict.items()
        if is_pic(name)
    }
    img_dir = path.join(path.dirname(ofname), 'img')
    if not path.isdir(img_dir): os.makedirs(img_dir) 
    for name, data in pics.items():
        img_fname = path.join(img_dir, name)
        open(img_fname, 'wb').write(data)
    

def main():
    parser = argparse.ArgumentParser('soepub2md')
    parser.add_argument('fname', help='epub fname')
    parser.add_argument('-d', '--dir', default='.', help='output dir')
    parser.add_argument('-t', '--threads', type=int, default=16, help='thread num')
    args = parser.parse_args()
    epub2md(args)

if __name__ == '__main__': main()
