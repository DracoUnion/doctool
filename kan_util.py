import requests
from typing import *

dft_hdrs = {
    'User-Agent': 'OpenDocCN',
}

def kan_exists(un: str, repo: str) -> bool:
    url = f'https://www.kancloud.cn/{un}/{repo}'
    return requests.get(url, headers=dft_hdrs).status_code != 404

def kan_release(un: str, repo: str, cookie: str) -> Dict[str, Any]:
    hdrs = dft_hdrs | {
        'Cookie': cookie,
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    url = f'https://www.kancloud.cn/book/{un}/{repo}/release'
    r = requests.post(url, data={}, headers=hdrs)
    if r.status_code in [200, 422]:
        return {'code': 0, 'message': ''}
    else:
        return {'code': 1, 'message': str(r.status_code)}

def kan_toggle(un, repo, cookie, field, on=True):
    hdrs = dft_hdrs | {
        'Cookie': cookie,
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'field': field,
        'on': 'on' if on else 'off',
    }
    url = f'https://www.kancloud.cn/book/{un}/{repo}/setting/toggle'
    r = requests.post(url, data=data, headers=hdrs)
    if r.status_code == 200:
        return {'code': 0, 'message': ''}
    else:
        return {'code': 1, 'message': str(r.status_code)}

def kan_create_repo(un, repo, cookie, title=None, desc=None, type='normal',  vis=True, extra=None):
    title = title or repo
    desc = desc or repo
    extra = extra or {}
    hdrs = dft_hdrs | {
        'Cookie': cookie,
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    data = {
        'type': type,
        'title': title,
        'name': repo,
        'description': desc,
        'visibility_level': '20' if vis else  '0',
        'namespace': un,
    }
    for k, v in extra.items():
        data['extra[' + k + ']'] = v
    url = 'https://www.kancloud.cn/new'
    r = requests.post(url, data=data, headers=hdrs)
    if r.status_code == 200:
        return {'code': 0, 'message': ''}
    else:
        return {'code': 1, 'message': str(r.status_code)}
