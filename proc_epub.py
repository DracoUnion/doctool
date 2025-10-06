import os
import subprocess as subp

def exec(cmd):
    print(cmd)
    subp.Popen(cmd, shell=True).communicate()


li = [
['懒人赚钱周报（单篇合集版）_20250101_20250131.epub', '202501'],
['懒人赚钱周报（单篇合集版）_20250201_20250228.epub', '202502'],
['懒人赚钱周报（单篇合集版）_20250301_20250331.epub', '202503'],
['懒人赚钱周报（单篇合集版）_20250401_20250430.epub', '202504'],
['懒人赚钱周报（单篇合集版）_20250501_20250531.epub', '202505'],
['懒人赚钱周报（单篇合集版）_20250601_20250630.epub', '202506'],
['懒人赚钱周报（单篇合集版）_20250701_20250731.epub', '202507'],
['懒人赚钱周报（单篇合集版）_20250801_20250831.epub', '202508'],
['懒人赚钱周报（单篇合集版）_20250901_20250930.epub', '202509']
]

d = 'flygon-zhuanqian-zhoubao-2025'
for fname, docname in li:
    exec(['epub-tool', 'ext-htmls', fname, '-p', docname + '_'])
    exec(['md-tool', 'tomd', '.'])
    exec(['md-tool', 'fmt', 'zh', '.'])
    exec(['powershell.exe', 'mkdir', f'd:/docs/{d}/docs/{docname}/img'])
    exec(['mv', '*.md', f'd:/docs/{d}/docs/{docname}'])
    exec(['rm', '*.html'])
    exec(['epub-tool', 'ext-pics', fname, '-o', f'd:/docs/{d}/docs/{docname}/img'])
    exec(['rm', fname])