from BookerPubTool.util import *
from BookerPubTool.git import *
from BookerPubTool.kan_util import *
from os import path
import os
import shutil
import tempfile
import uuid
import subprocess as subp
import argparse

def gh_repo_info(token, un, repo):
    hdrs = dft_hdrs | {
        'Authorization': f'Bearer {token}'
    }
    url = f'https://gitee.com/api/v5/repos/{un}/{repo}'
    j = request_retry('GET', url, headers=hdrs, retry=10000).json()
    if 'message' in j:
        return {'code': 1, 'message': j['message']}
    else:
        return {'code': 0, 'message': '', 'data': j}

def gh_repo_create(token, un, repo, desc='', org=False):
    hdrs = dft_hdrs | {
        'Authorization': f'Bearer {token}'
    }
    url = (
        f'https://gitee.com/api/v5/users/{un}/repos' 
        if not org 
        else  f'https://gitee.com/api/v5/orgs/{un}/repos'
    )
    data = {'name': repo, 'description': desc}
    j = request_retry('POST', url, json=data, headers=hdrs, retry=10000).json()
    if 'message' in j:
        return {'code': 1, 'message': j['message']}
    else:
        return {'code': 0, 'message': ''}



def pub_gitee(args):
    args.dir = path.abspath(args.dir)
    if not path.isdir(args.dir):
        print('请提供文档目录！')
        return
    docrt = os.listdir(args.dir)
    if 'SUMMARY.md' not in docrt or \
       'README.md' not in docrt:
        print('请提供文档目录！')
        return


    doc_id = path.basename(args.dir)
    print(f'创建仓库 {args.un}/{doc_id}')
    r = gh_repo_info(args.token, args.un, doc_id)
    if r['code'] == 0 and not args.force:
        print(f'{args.un}/{doc_id} 已存在')
        return
    if r['code'] != 0:
        readme = open(path.join(args.dir, 'README.md'), encoding='utf8').read()
        title, _ = get_md_title(readme)
        title = title or doc_id
        r = gh_repo_create(args.token, args.un, doc_id, title, args.orgs)
        if r['code'] != 0:
            print(f'{doc_id} 创建失败：{r["message"]}')
            return

    doc_dir = path.join(tempfile.gettempdir(), uuid.uuid4().hex)
    print(f'创建目录 {doc_dir}')
    shutil.copytree(args.dir, doc_dir)

    exec_cmd('git init', cwd=doc_dir)
    config_username_email(doc_dir, args.un, f'{args.un}@kancloud.cn')
    exec_cmd('git add -A', cwd=doc_dir)
    exec_cmd('git commit -m init', cwd=doc_dir)
    remote_url = (
        f'https://{args.token}@gitee.com/{args.un}/{doc_id}' 
        if not args.ssh
        else f'git@gitee.com:{args.un}/{doc_id}'
    )
    set_remote(doc_dir, 'origin', remote_url)
    exec_cmd('git push origin master -f', cwd=doc_dir)


    shutil.rmtree(doc_dir, True)


def main():
    parser = argparse.ArgumentParser(prog="BookerPubTool", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.set_defaults(func=lambda x: parser.print_help())
    parser.add_argument("dir", help="dir")
    parser.add_argument("-t", "--token", default=os.environ.get('GT_TOKEN', ''), help="gitee token")
    parser.add_argument("-u", "--un", default='wizardforcel', help="gitee username")
    parser.add_argument("-o", "--orgs", action='store_true', help="whether orgs")
    parser.add_argument("-s", "--ssh", action='store_true', help="whether to use ssh")
    parser.add_argument("-f", "--force", action='store_true', help="whether to force create")

    args = parser.parse_args()
    pub_gitee(args)

if __name__ == '__main__': main()