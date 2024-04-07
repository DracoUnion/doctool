import fitz
from pyquery import PyQuery as pq
import base64
import os
from os import path
import sys
import re
import cv2
import numpy as np

def is_pure_color(img):
    img = np.frombuffer(img, np.uint8)
    img = cv2.imdecode(img, cv2.IMREAD_GRAYSCALE)
    return (img == 0).mean() > 0.99 or (img == 255).mean() > 0.99

def merge_paras(rt):
    el_paras = rt('p')
    for el in el_paras:
        el = pq(el)
        text = el.text().strip()
        if len(text) >= 35 and not re.search(r'[。：；！？]$', text):
            el.attr('data-merge', 'true')
        
    for el in reversed(el_paras):
        el = pq(el)
        if el.attr('data-merge') and el.next().is_('p'):
            el.text(el.text() + el.next().text())
            el.next().remove()

def pdf2html(pdf_fname):
    name = path.basename(pdf_fname[:-4])
    doc = fitz.open(pdf_fname)
    html = []
    for pg in doc:
        html.append(pg.get_text('html'))
    html = '\n'.join(html)
    imgs = {}
    rt = pq(html)
    el_imgs = rt('img')
    l = len(str(len(el_imgs)))
    for i, el in enumerate(el_imgs, 1):
        print(f'page: {i}')
        el = pq(el)
        data = el.attr('src')
        if not data.startswith('data:'):
            continue
        data = re.sub(r'data:image/\w+;base64,', '', data)
        data = data.replace('\n', '')
        data = base64.b64decode(data)
        if is_pure_color(data):
            el.remove()
            continue
        img_name = name + '_' + str(i).zfill(l) + '.png'
        imgs[img_name] = data
        el.attr('src', 'img/' + img_name)
    merge_paras(rt)
    html_fname = pdf_fname[:-4] + '.html'
    html  = str(rt)
    html = re.sub(r'style=".*?"', '', html)
    open(html_fname, 'w', encoding='utf8').write(html)
    img_dir = path.join(path.dirname(pdf_fname),  'img')
    if not path.isdir(img_dir):
        os.makedirs(img_dir)
    for name, img in imgs.items():
        print(f'img: {name}')
        img_fname = path.join(img_dir, name)
        open(img_fname, 'wb').write(img)


def main():
    pdf_fname = sys.argv[1]
    pdf2html(pdf_fname)

if __name__ == '__main__': main()
        