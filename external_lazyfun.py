from pyquery import PyQuery  as pq
import requests
import json

def text_blocks_to_html(blocks):
    html = ''
    for b in blocks:
        # print(b)
        seg = b[0]
        if len(b) != 1:
            tags = [it[0] for it in b[1]]
            for t in tags: seg = f'<{t}>{seg}</{t}>'
        html += seg
    return html
    
def img_blocks_to_html(blocks):
    # print('blocks: ', blocks)
    html = ''.join([f'<img src="{b[0]}" />' for b in blocks])
    return html

def prop_to_html(prop):
    if 'title' in prop:
        return text_blocks_to_html(prop['title'])
    elif 'source' in prop:
        return img_blocks_to_html(prop['source'])
    else:
        return ''

def get_article(html, base):
    rt = pq(html)
    j = json.loads(rt('#__NEXT_DATA__').text())
    title = j['props']['pageProps']['post']['title']
    block_map = j['props']['pageProps']['post']['blockMap']['block']
    page_block = {
        k:v for k, v in block_map.items() 
        if v['value']['type'] == 'page'
    }.values().__iter__().__next__()
    order = page_block['value']['content']
    # print(order)
    text_blocks = {
        k:v['value']['properties'] for k, v in block_map.items() 
        if 'properties' in v['value'] 
        and ('title' in v['value']['properties'] 
          or 'source' in v['value']['properties'])
    }
    text_blocks = {k:prop_to_html(v) for k, v in text_blocks.items()}
    paras = [text_blocks[uid] for uid in order if uid in text_blocks]
    # paras = sum(paras, [])
    cont = '\n'.join(f'<p>{p}</p>' for p in paras)
    credit = f'<blockquote>来源：<a href="{base}">{base}</a></blockquote>'
    return {'title': title, 'content': credit + cont}
    
if __name__ == '__main__':
    url = 'https://www.lazyblog.fun/article/23122701'
    html = requests.get(url).text
    art = get_article(html, url)
    print(art)