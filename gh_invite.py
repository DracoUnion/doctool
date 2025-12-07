from pyquery import PyQuery as pq
import requests
from BookerDownloadTool.util import request_retry
import os

dft_hdrs = {
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Authorization': 'Bearer ' + os.environ['GHP_TOKEN'],
    'X-GitHub-Api-Version': '2022-11-28',
}

def main():
    li = open('github_top50_fans.txt', encoding='utf8').read().split('\n')
    li = [n for n in li if n]
    for name in li:
        print(name)
        j = request_retry(
            'GET', 
            f'https://api.github.com/users/{name}', 
            headers=dft_hdrs,
            retry=10000,
        ).json()
        if 'message' in j:
            print(f'{name} 邀请失败：{j["message"]}')
            continue
        uid = j['id']
        print(uid)
        j = request_retry('POST', 'https://api.github.com/orgs/opendoccn/invitations',
            json={
                'invitee_id': uid,
            },
            headers=dft_hdrs,
            retry=10000,
        ).json()
        if 'message' in j:
            print(f'{name} 邀请失败：{j["message"]}')
        else:
            print(f'{name} 邀请成功！')

if __name__ == '__main__': main()