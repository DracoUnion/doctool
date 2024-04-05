import os
import subprocess as subp

def exec(cmd):
    print(cmd)
    subp.Popen(cmd, shell=True).communicate()


li = [
["懒人赚钱周报 20221113~20230207.epub", '20230207'],
["懒人赚钱周报 20230328-20230404.epub", '20230328'],
["懒人赚钱周报 20230411~20230418.epub", '20230418'],
["懒人赚钱周报 20230510~20230516.epub", '20230516'],
["懒人赚钱周报 20230523~20230613.epub", '20230613'],
["懒人赚钱周报 20230620~20230627.epub", '20230627'],
["懒人赚钱周报 20230704-20230711.epub", '20230711'],
["懒人赚钱周报 20230718~20230801.epub", '20230801'],
["懒人赚钱周报20230808.epub", '20230808'],
["懒人赚钱周报20230815.epub", '20230815'],
["懒人赚钱周报20230822.epub", '20230822'],
["懒人赚钱周报20230829.epub", '20230829'],
["懒人赚钱周报20230905.epub", '20230905'],
["懒人赚钱周报20230912.epub", '20230912'],
["懒人赚钱周报20230920.epub", '20230920'],
["懒人赚钱周报20230926.epub", '20230926'],
["懒人赚钱周报20231017.epub", '20231017'],
["懒人赚钱周报20231031.epub", '20231031'],
["懒人赚钱周报20231107.epub", '20231107'],
["懒人赚钱周报20231114.epub", '20231114'],
["懒人赚钱周报20231121.epub", '20231121'],
["懒人赚钱周报20231128.epub", '20231128'],
["懒人赚钱周报20231205.epub", '20231205'],
["懒人赚钱周报20231212.epub", '20231212'],
["懒人赚钱周报20231219.epub", '20231219'],
["懒人赚钱周报20231226.epub", '20231226'],
]

d = 'flygon-zhuanqian-zhoubao'
for fname, docname in li:
    exec(['epub-tool', 'ext-chs', fname, '-l1', '-p', docname + '_'])
    exec(['md-tool', 'tomd', '.'])
    exec(['md-tool', 'fmt', 'zh', '.'])
    exec(['powershell.exe', 'mkdir', f'd:/docs/{d}/docs/{docname}/img'])
    exec(['mv', '*.md', f'd:/docs/{d}/docs/{docname}'])
    exec(['rm', '*.html'])
    exec(['7z', 'x', fname, '-otmp'])
    # exec(['powershell.exe', 'mv', 'tmp/OEBPS/images/*', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    # exec(['powershell.exe', 'mv', 'tmp/images/*', f'd:/docs/showmeai-tut-zh/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/Images/*', f'd:/docs/{d}/docs/{docname}/img'])
    exec(['rm', '-r', 'tmp'])
    exec(['rm', fname])