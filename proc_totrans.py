import os
import subprocess as subp

def exec(cmd):
    print(cmd)
    subp.Popen(cmd, shell=True).communicate()

'''
["jqui-api-doc.epub", 'jqui'],
["JSLite 中文文档.epub", 'jslite'],
["koa 中文文档.epub", 'koa'],
["Lodash 中文文档 4.5.epub", 'lodash45'],
["Meteor 中文文档.epub", 'meteor'],
["nodejs-api-doc-in-chinese.epub", 'node'],
["nwjs-doc.epub", 'nwjs'],
["orm2-doc-zh-cn.epub", 'orm2'],
["Sails.js 官方文档.epub", 'sails'],
["Sea.js 中文文档.epub", 'sea'],
["zeptojs-api-doc.epub", 'zepto'],
'''

li = [
["Abstract Interpretation.epub", 'abs-interp'],
["An Introduction to Elm.epub", 'intro-elm'],
["C++ Best Practices.epub", 'cpp-bst-prac'],
["calculus with applications (MIT 18.013A).epub", 'mit-18013a'],
["Computer Science Field Guide.epub", 'cs-fld-gd'],
["CS for All.epub", 'cs4a'],
["Data Structures and Functional Programming Lecture Notes (Cornell CS3110).epub", 'crnl-cs3110'],
["Databricks Spark Reference Applications.epub", 'dtbr-spark-ref-app'],
["Distributed Systems Engineering Lecture notes (MIT 6.824).epub", 'mit-6824'],
["DOM Enlightenment.epub", 'dom-enlit'],
["Functional Programming Lecture Notes (Chicago CS223).epub", 'chcg-cs223'],
["Functional Systems In Haskell Lecture Notes(Stanford CS240h).epub", 'stf-cs240h'],
["Graduate Computer Graphics (NYU CSCI-GA.2270-001).epub", 'nyu-cs2270'],
["How to Design Programs, Second Edition.epub", 'howto-dsn-prog-2e'],
["Implementing a language with LLVM.epub", 'impl-lang-llvm'],
["Java for small teams.epub", 'java-sml-tm'],
["Operating Systems Lecture Notes (Stanford CS140).epub", 'stf-cs140'],
["Programming and Programming Languages (Brown Univ).epub", 'brown-prog-lang'],
["Programming Languages Application and Interpretation.epub", 'prog-lang-app-interp'],
["Programming Languages Lecture Notes (NEU CS4400).epub", 'neu-cs4400'],
["Programming Practice Tutorials (KAIST CS109).epub", 'kaist-cs109'],
["Real-Time Programming Lecture Notes (Waterloo CS452).epub", 'wtl-cs452'],
["Serving Machine Learning Models.epub", 'sv-ml-mdl'],
["Software Construction Lecture Notes (MIT 6.005).epub", 'mit-6005'],
["Software Design and Implementation Lecture Notes (Washington CSE331).epub", 'wsht-cse331'],
["Software Engineering for Internet Applications.epub", 'swe-inet-app`'],
["Software Foundations.epub", 'sw-fund'],
["SQL for Web Nerds.epub", 'sql-web-nerd'],
["The Art of Data Science.epub", 'art-ds'],
["The Scheme Programming Language 4e.epub", 'schm-pl-4e'],
["Tiny Python & ES6 Notebook.epub", 'tiny-py-es6-nb'],
["UCB CS61AS SICP with Racket.epub", 'ucb-cs61as'],
]

repo = 'flygon-totrans-201404'

exec(['powershell.exe', 'mkdir', f'd:/docs/{repo}/totrans'])
for fname, docname in li:
    exec(['epub-tool', 'ext-chs', fname, '-l1', '-p', docname + '_'])
    exec(['md-tool', 'tomd', '.'])
    exec(['md-tool', 'ext-pre', '.'])
    exec(['md-tool', 'mk-totrans', '.'])
    # exec(['md-tool', 'fmt', 'zh', '.'])
    exec(['powershell.exe', 'mkdir', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['mv', '*.json', f'd:/docs/{repo}/totrans'])
    exec(['mv', '*.yaml', f'd:/docs/{repo}/totrans'])
    exec(['rm', '*.html'])
    exec(['rm', '*.md'])
    exec(['7z', 'x', fname, '-otmp'])
    # exec(['powershell.exe', 'mv', 'tmp/OEBPS/images/*', f'd:/docs/{repo}/docs/{docname}/img'])
    # exec(['powershell.exe', 'mv', 'tmp/images/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/Images/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/images/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/img/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/assets/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/graphics/*', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/*.png', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/*.jpg', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/OEBPS/*.gif', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/*.gif', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/*.jpg', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['powershell.exe', 'mv', 'tmp/*.png', f'd:/docs/{repo}/docs/{docname}/img'])
    exec(['rm', '-r', 'tmp'])
    exec(['rm', fname])