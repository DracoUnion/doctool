
import requests
from pyquery import PyQuery as pq
from urllib.parse import urljoin

config = {
    'name': 'runoob',
    'url': 'https://www.runoob.com/',
    'doc': '.codelist>h2, .codelist>a',
    'chapter': '#leftcolumn>h2, #leftcolumn>a',
    

}

def main():
    ofile = open(config['name'] + '.txt', 'w', encoding='utf8')
    html = requests.get(config['url']).text
    rt = pq(html)
    el_docs = rt.find(config['doc'])
    for el in el_docs:
        el = pq(el)
        if not el.attr('href'):
            txt = el.text().strip()
            print(txt)
            ofile.write(txt + '\n')
            continue
        url = el.attr('href')
        url = urljoin(config['url'], url)
        print(url)
        html = requests.get(url).text
        doc_rt = pq(html)
        el_chs =  doc_rt.find(config['chapter'])
        for elsub in el_chs:
            elsub = pq(elsub)
            if not elsub.attr('href'):
                txt = elsub.text().strip()
                print(txt)
                ofile.write(txt + '\n')
            else:
                suburl = elsub.attr('href')
                suburl = urljoin(url, suburl)
                print(suburl)
                ofile.write(suburl + '\n')
                
    print('done...')
    
if __name__ == '__main__': main()
            