from BookerEpubTool.util import *
from BookerMarkdownTool.tomd import tomd
import argparse
from pyquery import PyQuery as pq

def get_title(html):
    if isinstance(html, bytes):
        html = html.decode('utf8', 'ignore')
    html = rm_xml_header(html)
    title = (pq(html).find('h1').eq(0).html() or '').strip()
    print(title)
    return title

def epub2md(args):
    if not args.fname.endswith('.epub'):
        raise ValueError('请提供 EPUB 文件')
    fdict = read_zip(args.fname)
    # _, ncx = read_opf_ncx(fdict)
    htmls = [
        cont.decode('utf8', 'ignore')
        for name, cont in fdict.items()
        if name.endswith('.html') and
           get_title(cont) != '-'
    ]

    for html in htmls:
        md = tomd(html)
        m = re.search(r'ID：(\d+)', md)
        if not m: continue
        id_ = m.group(1).zfill(9)
        print(id_)
        ofname = path.join(args.dir, f'{id_}.md')
        open(ofname, 'w', encoding='utf8').write(md)

def main():
    parser = argparse.ArgumentParser('soepub2md')
    parser.add_argument('fname', help='epub fname')
    parser.add_argument('-d', '--dir', default='.', help='output dir')
    args = parser.parse_args()
    epub2md(args)

if __name__ == '__main__': main()
