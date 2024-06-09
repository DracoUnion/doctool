from EpubCrawler.util import request_retry
import json
from os  import path
import base64
import os
import hashlib
import re

GHP_TOKEN = os.environ.get('GHP_TOKEN', '')
headers = {
    'Authorization': f'Bearer {GHP_TOKEN}'
}

def get_blob_sha(cont):
    cont = cont.encode('utf8')
    cont = b'blob %d\0' % len(cont) + cont
    return hashlib.sha1(cont).hexdigest()

def list_dir(ns, repo, path):
    url = f'https://api.github.com/repos/{ns}/{repo}/contents/{path}'
    r = request_retry('GET', url, headers=headers)
    if r.status_code != 200: return []
    j = r.json()
    return [it['name'] for it in j]
    
def read_file(ns, repo, path):
    url = f'https://api.github.com/repos/{ns}/{repo}/contents/{path}'
    r = request_retry('GET', url, headers=headers)
    if r.status_code != 200: return ''
    j = r.json()
    return base64.b64decode(j['content'].encode('utf8')).decode('utf8')
    
def list_org_repos(ns):
    res = []
    for i in range(1, 1_000_000):
        url = f'https://api.github.com/orgs/{ns}/repos?per_page=100&page={i}'
        r = request_retry('GET', url, headers=headers)
        if r.status_code != 200: break
        j = r.json()
        if len(j) == 0: break
        res += [it['name'] for it in j]
    return res
    
def update_file(ns, repo, path, cont, old_sha):
    url = f'https://api.github.com/repos/{ns}/{repo}/contents/{path}'
    data = {
        'message': f'update {path}',
        'content': base64.b64encode(cont.encode('utf8')).decode('utf8'),
        'sha': old_sha,
    }
    r = request_retry('PUT', url, json=data, headers=headers)
    if r.status_code // 100 == 2:
        return {'code': 0, 'msg': ''}
    else:
        return {'code': r.status_code, 'msg': r.text}

def update_cname(repo, rt):
    fname = 'CNAME'
    if fname not in rt: return
    cont = read_file('opendoccn', repo, fname)
    print(cont)
    if 'apachecn.org' not in cont: return
    new_cont = cont.replace('apachecn.org', 'flygon.net')
    r = update_file(
        'opendoccn', repo, fname, new_cont, get_blob_sha(cont))
    if r['code'] == 0:
        print(f'{repo} {fname} 修改成功')
    else:
        msg = r['msg']
        print(f'{repo} {fname} 修改失败：{msg}')

def update_index(repo, rt):
    fname = 'index.html'
    if fname not in rt: return
    cont = read_file('opendoccn', repo, fname)
    print(cont)
    new_cont = cont
    if 'docsify-apachecn-footer' in new_cont:
        new_cont = new_cont.replace('<script src="asset/docsify-apachecn-footer.js"></script>', '')
    if 'apachecn/' in new_cont:
        new_cont = new_cont.replace('apachecn/', 'opendoccn/')
    if 'apachecn-' in new_cont:
        new_cont = new_cont.replace('apachecn-', 'flygon-')
    if 'ApacheCN ' in new_cont:
        new_cont = new_cont.replace('ApacheCN ', '飞龙的')
    if re.search(r'(?<!// )alias: \{', new_cont):
        new_cont = re.sub(r'alias: \{[\s\S]*?\},', '', new_cont)
    if 'relativePath: ' not in new_cont:
        new_cont = re.sub(r'(\}\s+</script>)', '  relativePath: true,\n    ' + r'\1', new_cont)
    new_cont = re.sub(r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', new_cont)
    new_cont = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', new_cont)
    if cont != new_cont:
        r = update_file(
            'opendoccn', repo, fname, new_cont, get_blob_sha(cont))
        if r['code'] == 0:
            print(f'{repo} {fname} 修改成功')
        else:
            msg = r['msg']
            print(f'{repo} {fname} 修改失败：{msg}')


def update_readme(repo, rt):
    fname = 'README.md'
    if fname not in rt: return
    cont = read_file('opendoccn', repo, fname)
    print(cont)
    new_cont = cont
    if '赞助我们' in new_cont:
        new_cont = new_cont.replace(r'赞助我们', '赞助我').replace('http://data.apachecn.org/img/about/donate.jpg', 'https://img-blog.csdnimg.cn/20200112005920729.png')
        new_cont = re.sub(r'赞助我们', '赞助我', new_cont, flags=re.M)
    if '### PYPI'  in new_cont:
        new_cont = re.sub(r'### PYPI[\s\S]+?(?=^### )', '', new_cont, flags=re.M)
    if 'apachecn.org'  in new_cont:
        new_cont = new_cont.replace('apachecn.org', 'flygon.net')
    if 'apachecn-' in new_cont:
        new_cont = new_cont.replace('apachecn-', 'flygon-')
    if '# ApacheCN' in new_cont:
        new_cont = new_cont.replace('# ApacheCN', '# VKDoc')
    if '## 联系方式' in new_cont:
        new_cont = re.sub(r'## 联系方式[\s\S]+?(?=^## )', '', new_cont, flags=re.M)
    if '## 贡献指南' in new_cont:
        new_cont = re.sub(r'## 贡献指南[\s\S]+?(?=^## )', '', new_cont, flags=re.M)
    if '## 其它协议' in new_cont:
        new_cont = re.sub(r'## 其它协议[\s\S]+?(?=^## )', '', new_cont, flags=re.M)
    if '## 目录' in new_cont:
        new_cont = re.sub(r'## 目录[\s\S]+?(?=^## )', '', new_cont, flags=re.M)
    if '[ApacheCN ' in new_cont:
        new_cont = re.sub(r'^[\+\-\*]\s+\[ApacheCN.+?\]\(.+?\)\s*$\r?\n', '', new_cont, flags=re.M)
    if '（Gitee）' in new_cont:
        new_cont = re.sub(r'^[\+\-\*]\s+\[.+?（Gitee）\]\(.+?\)\s*$\r?\n', '', new_cont, flags=re.M)
    new_cont = re.sub(r'([\u4e00-\u9fff])([a-zA-Z0-9])', r'\1 \2', new_cont)
    new_cont = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fff])', r'\1 \2', new_cont)
    if cont != new_cont:
        r = update_file(
            'opendoccn', repo, fname, new_cont, get_blob_sha(cont))
        if r['code'] == 0:
            print(f'{repo} {fname} 修改成功')
        else:
            msg = r['msg']
            print(f'{repo} {fname} 修改失败：{msg}')

def main():
    repos_fname = 'repos.json'
    if path.isfile(repos_fname):
        repos = json.loads(open(repos_fname, encoding='utf8').read())
    else:
        repos = list_org_repos('opendoccn')
        open(repos_fname, 'w', encoding='utf8').write(json.dumps(repos))
        
    for repo in repos:
        print(repo)
        rt = list_dir('opendoccn', repo, '')
        update_readme(repo, rt)
        # update_cname(repo,rt)
        update_index(repo,rt)
        # return
            
if __name__ == '__main__': main()
            