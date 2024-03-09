import os
import subprocess as subp

def exec(cmd):
    print(cmd)
    subp.Popen(cmd, shell=True).communicate()


li = [
["图解 AI 数学基础（ShowMeAI）.epub", 'math'],
["图解数据分析（ShowMeAI）.epub", 'da'],
["图解机器学习算法（ShowMeAI）.epub", 'ml'],
["斯坦福 CS224N NLP 课程详解（ShowMeAI）.epub", 'cs224n'],
["斯坦福 CS231n 全套笔记（ShowMeAI）.epub", 'cs231n'],
["机器学习实战（ShowMeAI）.epub", 'mlia'],
]


for fname, docname in li:
    exec(['epub-tool', 'ext-chs', fname, '-l1', '-p', docname + '_'])
    exec(['md-tool', 'tomd', '.'])
    exec(['md-tool', 'fmt', 'zh', '.'])
    exec(['powershell.exe', 'mkdir', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    exec(['mv', '*.md', f'd:/docs/showmeai-tut-zh/docs/{docname}'])
    exec(['rm', '*.html'])
    exec(['7z', 'x', fname, '-otmp'])
    # exec(['powershell.exe', 'mv', 'tmp/OEBPS/images/*', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    # exec(['powershell.exe', 'mv', 'tmp/images/*', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/Images/*', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    exec(['rm', '-r', 'tmp'])
    exec(['rm', fname])