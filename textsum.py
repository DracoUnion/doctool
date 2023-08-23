import re
from pyquery import PyQuery as pq
from transformers import AutoTokenizer, AutoModel

tokenizer = None
model = None

def load_model(args):
    global tokenizer
    global model
    
    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    model = AutoModel.from_pretrained("args.model_path, trust_remote_code=True)
    if args.gpu: model = model.cuda()
    model = model.eval()

def main(args):
    # `args.fname`：`str`，分号分隔的文件名
    # `args.model_path`：`str`，模型名称或者路径
    # `args.gpu`：`bool`，是否使用 GPU
    # `args.prompt`：`str`，文本总结提示词
    # `args.chunk_max`：`int`，文本块最大长度
    # `args.res_max`：`int`，文本总结最大长度
    # `args.overlap`：`int`，文本块重叠长度
    load_model()
    fnames = args.fname.split(';')
    for f in fnames:
        proc_one_file(f, args)
    
def group_chunks(lines, args):
    chunk_max, overlap = args.chunk_max,  args.overlap
    step = chunk_max - overlap
    text = '\n'.join(lines)
    res = []
    for i in range(0, len(text), step):
        res.append(text[i:i+step])
    for i in range(1, len(res)):
        res[i] = res[i - 1][-overlap:] + res[i]
    return res
            
    
def get_html_lines(html):
    rt = pq(html)
    elems = rt('p, h1, h2, h3, h4, h5, h6, li, td, th, blockquote')
    res = []
    for el in elems:
        el = pq(el)
        if el.find('p'): continue
        el.find('ol, ul').remove()
        res.append((el.text() or '').strip())
    return res
    
def summarize(text, prompt):
    return model.chat(tokenizer, prompt + text, [])[0]
    
def proc_one_file(fname, args):
    
    if fname.endswith('.txt'):
        lines = open(fname, encoding='utf8').read().split('\n')
    elif fname.endswith('.html'):
        html = open(fname, encoding='utf8').read()
        lines = get_html_lines(html)
    else:
        raise ValueError(f'文件 [{fname}] 必须是 TXT/HTML')
    
    lines = [l for l in lines if l.strip()]
    chunks = group_chunks(lines, args)
    
    while True:
        total = sum(len(c) for c in chunks)
        if total <= args.res_max: break
        chunks = group_chunks([summarize(c, args.prompt) for c in chunks], args)
        
    res = '\n\n'.join(chunks)
    print(res)
    ofname = re.sub(r'\.\w+$', '', fname) + '_res.txt'
    open(ofname, 'w', encoding='utf8').write(res)
    