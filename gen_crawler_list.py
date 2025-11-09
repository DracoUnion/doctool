import json
import requests
from pyquery import PyQuery as pq
from urllib.parse import urljoin
import subprocess as subp

config = {
    'name': '菜鸟教程（runoob）',
    'url': 'https://www.runoob.com/',
    'doc': '.codelist>h2, .codelist>a',
    'chapter': '#leftcolumn>h2, #leftcolumn>a',
    'docName': 'body > div.container.main > div > div.runoob-col-md2 > div > div.tab > span',
	"title": "#content>h1",
	"content": "#content",
	"remove": "script, ins, iframe",
	"optiMode": "quant",

}

def main():
    ofile = open(config['name'] + '.txt', 'w', encoding='utf8')
    html = requests.get(config['url']).text
    rt = pq(html)
    el_docs = rt.find(config['doc'])
    for el in el_docs:
        el = pq(el)
        if not el.attr('href'):
            '''
            txt = el.text().strip()
            print(txt)
            ofile.write(txt + '\n')
            '''
            continue
        url = el.attr('href')
        url = urljoin(config['url'], url)
        print(url)
        html = requests.get(url).text
        doc_rt = pq(html)
        doc_name = doc_rt.find(config['docName']).text().strip()

        cralwer_cfg = {
            'name': config['name'] + doc_name,
            'url': url,
            'title': config['title'],
            'content': config['content'],
            'remove': config['remove'],
            'optiMode': config['optiMode'],
            'link': config['chapter'],
            'textThreads': 4,
            'imgThreads': 4,
        }
        open('config_.json', 'w', encoding='utf8').write(json.dumps(cralwer_cfg))
        subp.run(['crawl-epub', 'config_.json'])
                
    print('done...')
    
if __name__ == '__main__': main()
            