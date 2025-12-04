from pyquery import PyQuery as pq
import requests

cookie = open('gh_cookie.txt', encoding='utf8').read()
dft_hdrs = {
    'Cookie': cookie
}

def get_tokrn(html):
    return pq(html).find('input[name="invitee_id"]').attr('value')

def get_iid(html):
    return pq(html).find('input[name="authenticity_token"]').attr('value')

def main():
    li = open('github_top50_fans.txt', encoding='utf8').read().split('\n')
    li = [n for n in li if n]
    for name in li:
        print(name)
        html = requests.get('https://github.com/orgs/OpenDocCN/people', headers=dft_hdrs).text
        tk = get_tokrn(html)
        r = requests.post('https://github.com/orgs/OpenDocCN/invitations/member_adder_add',
            data={
                'authenticity_token': tk,
                'identifier': name,
            },
            headers=dft_hdrs
        )
        if r.status_code != 302:
            print(f"{name} 未找到：HTTP {r.status_code}")
            continue

        html = requests.get(f'https://github.com/orgs/OpenDocCN/invitations/{name}/edit', headers=dft_hdrs).text
        tk = get_tokrn(html)
        iid = get_iid(html)
        r = requests.post(
            'https://github.com/orgs/OpenDocCN/invitations',
            data={
                'authenticity_token': tk,
                'role': 'direct_member',
                'invitee_id': iid,
            },
            headers=dft_hdrs,
        )
        if r.status_code != 302:
            print(f'{name} 邀请失败：HTTP {r.status_code}')
        else:
            print(f'{name} 邀请成功！')

if __name__ == '__main__': main()