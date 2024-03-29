from EpubCrawler.config import config
from pyquery import PyQuery as pq


def get_article(html, url):
    rt = pq(html)
    if config['remove']:
        rt(config['remove']).remove()
    el_pics = rt('picture')
    for el in el_pics:
        el = pq(el)
        el_src = el.find('source').eq(0)
        if len(el_src) == 0: continue
        src = el_src.attr('srcset').split(', ')[-1].split(' ')[0]
        el_img = pq('<img/>')
        el_img.attr('src', src)
        el.replace_with(el_img)
        
    el_title = rt(config['title']).eq(0)
    title = el_title.text().strip()
    el_title.remove()
    cont = f'<blockquote>原文：<a href="{url}">{url}</a></blockquote>' + \
           rt(config['content']).html()
    return {
        'title': title,
        'content': cont,
    }