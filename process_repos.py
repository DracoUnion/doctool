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
        fname = 'README.md'
        if fname not in rt: continue
        cont = read_file('opendoccn', repo, fname)
        print(cont)
        if not re.search(r'^# ApacheCN', cont, flags=re.M): continue
        new_cont = re.sub(r'^# ApacheCN\s*', '# 飞龙的', cont, flags=re.M)
        r = update_file(
            'opendoccn', repo, fname, new_cont, get_blob_sha(cont))
        if r['code'] == 0:
            print(f'{repo} 修改成功')
        else:
            msg = r['msg']
            print(f'{repo} 修改失败：{msg}')
        # return
            
if __name__ == '__main__': main()
            