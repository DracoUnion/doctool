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


def download(args):
    ofname = path.join(args.dir, str(args.qid).zfill(9) + '.md')
    if path.isfile(ofname):
        print(f'{args.qid} 已下载')
        return
    print(f'qid: {args.qid}')
    url = f'https://www.stackoverflow.org.cn/questions/{args.qid}'
    r = request_retry('GET', url)
    if r.status_code == 404:
        print(f'{args.qid} 不存在')
        return
    art = get_article(r.text, url)
    if art['title'] == '-':
        print(f'{args.qid} 不存在')
        return
    title, cont = art['title'], art['content']
    html = f'<h1>{html_escape(title)}</h1>{cont}'
    md = tomd(html)
    open(ofname, 'w', encoding='utf8').write(md)
    print(f'{args.qid} 下载成功')

def download_safe(*args, **kw):
    try:
        download(*args, **kw)
    except:
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--start', type=int, default=0, help='starting id')
    parser.add_argument('-e', '--end', type=int, default=0, help='ending id')
    parser.add_argument('-d', '--dir', default='.', help='output dir')
    parser.add_argument('-t', '--threads', type=int, default=8, help='thread num')
    parser.add_argument('-r', '--retry', type=int, default=100000, help='retry')
    args = parser.parse_args()

    pool = ThreadPoolExecutor(args.threads)
    hdls = []
    for i in range(args.start, args.end + 1):
        args = copy.deepcopy(args)
        args.qid = i
        hdl = pool.submit(download_safe, args)
        hdls.append(hdl)
        if len(hdls) >= args.threads:
            for h in hdls: h.result()
            hdls.clear()
    for h in hdls:
        h.result()
        

if __name__ == '__main__': main()
