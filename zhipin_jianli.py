
import time
from BookerDownloadTool.util import camou_create_driver
import browser_cookie3 as bc3
import random

def ext_plrt_cookies(domain):
    cj = bc3.firefox(domain_name=domain)
    # 2. 转换为 Playwright 需要的字典列表
    plrt_cookies = []
    for cookie in cj:
        plrt_cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,          # 例如 ".example.com"
            "path": cookie.path or "/",
            # 可选：如果 cookie 有明确过期时间（非会话 cookie），转为 float
            "expires": -1,
            "httpOnly": cookie.has_nonstandard_attr("HttpOnly"), # 近似判断
            "secure": bool(cookie.secure),
        })
    print(plrt_cookies)
    return plrt_cookies

def main():
    cookies = ext_plrt_cookies('.zhipin.com')
    print(f'提取到 {len(cookies)} 个 Cookie')
    with camou_create_driver(True) as (br, ctx, page):
        ctx.add_cookies(cookies)
        page.goto("https://www.zhipin.com/web/geek/jobs?ka=header-jobs") 
        already = 0
        while True:
            jobs = page.locator('.job-info').all()
            if already == len(jobs): break
            for j in jobs[already:]:
                j.click(force=True)
                info = page.locator('.job-detail-info').inner_text().strip()
                print(info)
                chat_btn = page.locator('.op-btn-chat').first
                btn_text = chat_btn.inner_text().strip()
                if '立即沟通' not in btn_text: 
                    print('已沟通，跳过')
                    continue
                chat_btn.click(force=True)
                print('点击沟通按钮')
                stay_btn = page.locator('a.default-btn:nth-child(1)').first
                stay_btn.click(force=True)
                print('点击留在此页')
                time.sleep(1 + random.uniform(0, 1))
            
            already = len(jobs)
            print('滚动到底部')
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

if __name__ == '__main__': main()