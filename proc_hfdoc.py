from pyquery import PyQuery as pq
import os
from os import path
import sys

def proc_html(html):
    rt = pq(html)
    rt('.docstring svg').remove()
    
    el_titles = rt('''
        .docstring h3>span, 
        .docstring h4>span, 
        .docstring li strong:first-of-type
    ''')
    for el in el_titles:
        el = pq(el)
        el_code = pq('<code></code>')
        el_code.text(el.text())
        el.replace_with(el_code)
        
    el_pres = rt('.docstring p.font-mono')
    for el in el_pres:
        el = pq(el)
        el_pre = pq('<pre></pre>')
        el_pre.text(el.text())
        el.replace_with(el_pre)
        
    return str(rt)
        
def proc_file(fname):
    if not fname.endswith('.html'):
        return
    print(fname)
    html = open(fname, encoding='utf8').read()
    html = proc_html(html)
    open(fname, 'w', encoding='utf8').write(html)
    
def proc_dir(dir):
    fnames = os.listdir(dir)
    for f in fnames:
        f = path.join(dir, f)
        proc_file(f)
        
def main():
    fname = sys.argv[1]
    if path.isfile(fname):
        proc_file(fname)
    else:
        proc_dir(fname)
        
if __name__ == '__main__': main()
        