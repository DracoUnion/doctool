import copy
import argparse
from os import path
from EpubCrawler.util import request_retry
from pyquery import PyQuery as pq
from BookerMarkdownTool.tomd import tomd
from html import escape as html_escape
from concurrent.futures import ThreadPoolExecutor
import traceback

def get_article(html, base):
    rt = pq(html)
    id = base.split('/')[-1]
    title = rt('.fs-headline1').eq(0).text().strip()
    ques_cont = rt('.question .js-post-body').html()
    ques_vote = rt('.question .js-vote-count').text().strip()
    tags = [pq(el).text().strip() for el in rt('.question a.post-tag')]
    tags = ', '.join(tags)
    ques_time = rt('#question-header~div time').text().strip()
    el_answers = rt('.answer')
    answers = [
        {
            'cont': pq(el).find('.js-post-body').html(),
            'vote': pq(el).find('.js-vote-count').text().strip(),
            'time': pq(el).find('.user-action-time').text().strip().split(' ')[1],
        
        }
        for el in el_answers
    ]
    
    cont = f'''
        <blockquote>
        <p>ID：{id}</p>
        <p>赞同：{ques_vote}</p>
        <p>时间：{ques_time}</p>
        <p>标签：{tags}</p>
        </blockquote>
        {ques_cont}
    ''' + '\n'.join([
        f'''
            <hr />
            <h2>回答 #{i}</h2>
            <blockquote>
            <p>赞同：{ans["vote"]}</p>
            <p>时间：{ans["time"]}</p>
            </blockquote>
            {ans["cont"]}
        '''
        for i, ans in enumerate(answers, 1)
    ])
    
    return {
        'title': title,
        'content': cont,
    }

def tr_download_one_safe(*args, **kw):
    try:
        tr_download_one(*args, **kw)
    except:
        traceback.print_exc()

def tr_download_one(qid, art_, retry):
    print(f'qid: {qid}')
    url = f'https://www.stackoverflow.org.cn/questions/{qid}'
    r = request_retry('GET', url, retry=retry)
    if r.status_code == 404:
        print(f'{qid} 不存在')
        return
    art = get_article(r.text, url)
    if art['title'] == '-':
        print(f'{qid} 不存在')
        return
    art_.update(art)
    print(f'{qid} 下载成功')

def download_batch(st, ed, dir, trnum, retry):
    ofname = path.join(dir, f'{st:09d}-{ed:09d}.md')
    if path.isfile(ofname):
        print(f'{ofname} 已存在')
        return
    pool = ThreadPoolExecutor(trnum)
    hdls = []
    articles = []
    for i in range(st, ed + 1):
        art = {}
        articles.append(art)
        h = pool.submit(tr_download_one_safe, i, art, retry)
        hdls.append(h)
        if len(hdls) >= trnum:
            for h in hdls: h.result()
            hdls.clear()
            
    for h in hdls: h.result()
    htmls = [
        '<h1>' + html_escape(a['title']) + '</h1>' + a['content']
        for a in articles if a
    ]
    
    
    html = ''.join(htmls)
    md = f'# StackOverflow 问答 {st:09d}-{ed:09d}\n\n' + tomd(html)
    print(ofname)
    open(ofname, 'w', encoding='utf8').write(md)
    
    



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', type=int, default=0, help='starting id')
    parser.add_argument('-e', '--end', type=int, default=0, help='ending id')
    parser.add_argument('-b', '--size', type=int, default=1000, help='batch size')
    parser.add_argument('-d', '--dir', default='.', help='output dir')
    parser.add_argument('-t', '--threads', type=int, default=8, help='thread num')
    parser.add_argument('-r', '--retry', type=int, default=100000, help='retry')
    args = parser.parse_args()

    st = args.start // args.size * args.size
    ed = args.end // args.size * args.size + args.size - 1
    for i in range(st, ed + 1, args.size):
        download_batch(i, i + args.size - 1, args.dir, args.threads, args.retry)

if __name__ == '__main__': main()
