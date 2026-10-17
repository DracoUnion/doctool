# -*- coding: utf-8 -*-
"""将给定目录中的易语言(EPL)源码转换成 Python 的 agent。

用法示例::

    python e2py.py D:\\src\\my_epl_program -k <key> -H <base_url> -m <model>

输入目录中的 ``.e`` / ``.ec`` 等易语言源码会被翻译为 ``.py``，
输出到输入目录同级 ``{目录名}_py`` 目录下，保持相对目录结构不变。

复用 ``D:\\src\\BookerGptTool\\BookerGptTool\\openai.py`` 完成所有 LLM 调用
（``set_openai_props`` / ``ask_chatgpt_retry``）。

流程::

  1. 遍历输入目录，收集易语言源文件（文本模式），跳过二进制/编译态文件。
  2. 对每个文件: 读取 → 按 ``.子程序`` 边界分块(大文件) → LLM 逐块翻译 →
     拼接 → ``compile()`` 语法检查 → 有错则修复循环。
  3. 结果写入 ``{目录名}_py``，并按源码 md5 缓存，重复运行直接跳过。
"""

import re
import os
import sys
import time
import argparse
import logging
from os import path

# ---- 复用 BookerGptTool 的 openai.py / util.py ----
_BGT_ROOT = path.abspath(
    path.join(path.dirname(path.abspath(__file__)), '..', 'BookerGptTool'))
sys.path.insert(0, _BGT_ROOT)

from BookerGptTool.openai import (  # noqa: E402
    set_openai_props,
    ask_chatgpt_retry,
    NO_THINK_EXTRA_BODY,
)
from BookerGptTool.util import (  # noqa: E402
    render_prompt,
    read_text,
    write_text,
    md5,
    extname,
)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s][%(name)s][%(levelname)s] %(message)s')
logger = logging.getLogger('e2py')

DEFAULT_EXTS = 'e,ec,epr,ecode,txt,xml'

# --------------------------------------------------------------------------
# 提示词
# --------------------------------------------------------------------------

CONVERT_PMT = '''
你是精通易语言与 Python 的程序员。请把下面给出的易语言源码完整、忠实地
翻译成 Python 3 代码，并保持全部业务逻辑一致。

## 易语言语法映射 (只作参考，请按要求输出)
- 程序集/子程序/参数/局部变量/全局变量 声明:
  .子程序 -> def 函数，函数名保留原编号或子程序名；
  .参数 / .局部变量 / .程序集变量 / .全局变量 -> 对应 Python 变量定义。
- 类型映射: 整数型/长整数型 -> int，文本型 -> str，逻辑型 -> bool，
  字节集 -> bytes，小数型/双精度小数型 -> float，日期时间型 -> datetime。
- 常用命令近似等价 (无法一一对应时保留调用意图并加注释):
  输出调试文本(内容) -> print(内容)；
  信息框(内容, 提示) -> print 或注释替代；
  到整数(x) / 到文本(x) / 到数值(x) -> int(x) / str(x) / float(x)；
  取文本长度(x) -> len(x)；
  计次循环首(总数, 变量) -> for 变量 in range(总数)；
  变量循环首(初值, 终值, 步长, 变量) -> for 变量 in range(初值, 终值+方向, 步长)；
  循环判断首/循环判断尾 -> while True 循环，按原逻辑设置循环条件与 break；
  判断循环首(条件)/判断循环尾 -> while 条件:；
  如果(条件)/否则/结束如果 -> if/else；
  判断开始/判断(值)/分支/结束判断 -> if/elif/else 或 match；
  返回(x) -> return x；跳出循环 -> break；到循环尾 -> continue。
- GUI 控件(窗口/按钮/编辑框/标签/组合框等)一律用 PyQt6 实现：
  窗口 -> QMainWindow / QWidget，按钮 -> QPushButton，编辑框 -> QLineEdit /
  QTextEdit，标签 -> QLabel，组合框 -> QComboBox，分组框 -> QGroupBox，
  时钟 -> QTimer；控件事件 -> 对应信号槽(如 clicked、currentTextChanged)。
  无法逐一对号入座时保留控件与事件语义，用 PyQt6 近似实现，必要处加注释说明
  原控件名。
- 反编译特征名(来自 e-packager 等工具)：形如 控件._LibXType13MemY 的成员访问
  表示取该控件的内容/当前文本（如 组合框1._Lib0Type13Mem9 即组合框当前选中项
  文本），用对应 PyQt6 API(如 QComboBox.currentText())替代，并在注释中标注原名称；
  #_LibXConstY / 其它 #常量 是常量引用，按语义替换为实际值或命名常量。
- 外部模块/支持库类(如 内存_驱动读写1类)的 读整数型(进程, 地址) / 写整数型
  (进程, 地址, 值) 表示对目标进程内存的读写，用 ctypes(ReadProcessMemory/
  WriteProcessMemory)或自定义辅助函数近似实现，注释中说明原调用；
  进程取ID(进程名) -> 按进程名取 PID；监视热键(&子程序, 热键) -> 注册全局
  热键回调；十六到十("ABC") -> int("ABC", 16)。

## 要求
1. 只输出 Python 3 代码，不要输出解释文字，不要用 markdown 代码块围栏。
2. 完整保留注释与函数结构；含易语言命令但无法对应处，输出近似实现并加注释
   注明原命令。
3. 输出放在 [content] 与 [/content] 两个标记之间。

{header_hint}

<待翻译源码>
{src}
'''

CHUNK_PMT = '''
以下是同一易语言程序的公共头部(版本/程序集/全局变量说明，仅作上下文参考，
不要重复输出)。随后是要翻译的一段子程序代码。请把该段翻译成 Python 3，
要求同上: 只输出 [content]...[/content] 中的 Python 代码。

<公共头部>
{header}

<待翻译源码段 {idx}/{total}>
{src}
'''

REPAIR_PMT = '''
下面这段由易语言翻译得到的 Python 代码编译报错。请修复错误使其能通过
编译，保持原有逻辑不变。只输出修复后的完整 Python 代码，放在
[content] 与 [/content] 标记之间，不要输出解释文字。

<错误信息>
{err}

<代码>
{code}
'''

# 易语言窗口布局 XML -> PyQt6 布局代码
XML_PMT = '''
下面是一段易语言窗口布局 XML（已去除扩展属性二进制数据），定义了窗口及其中
控件。请把它转成等价的 PyQt6 窗口布局代码，控件结构一一对应。

规则:
- 窗口 / 分组框(容器) / 标签 / 按钮 / 编辑框 / 组合框 / 单选框 / 复选框 /
  列表框 / 图片框 / 时钟 等控件名按 XML 里的名称(名称属性)作为变量名。
- 一律使用 PyQt6: 窗口 -> QMainWindow / QWidget，分组框 -> QGroupBox，
  标签 -> QLabel，按钮 -> QPushButton，编辑框 -> QLineEdit / QTextEdit，
  组合框 -> QComboBox，时钟 -> QTimer；控件事件用信号槽连接(如
  currentTextChanged、clicked、timeout)，事件逻辑可以留空或加 TODO 注释。
- 用绝对布局(QWidget.setGeometry / move + resize)按 XML 里的
  左边/顶边/宽度/高度(px) 摆放控件；组合框项目可由代码自由补充，
  若 XML 里没有明确项目则以注释 TODO 标记。
- 只输出构建整个窗口界面的 PyQt6 代码（不包含业务逻辑），可输出一个
  class MainWindow(QMainWindow) 并带 build_ui() 方法；放在
  [content] 与 [/content] 之间，不要输出解释文字。

<窗口XML>
{src}
'''

XML_BLOB_ATTR_RE = re.compile(r'\s+(扩展属性数据|鼠标指针|样式|参照)="[^"]{64,}"')


def has_code_feature(s: str) -> bool:
    """判断文本是否含可编译的代码特征（用于拒绝纯分析文本）。"""
    if not s:
        return False
    if '[content]' in s or '```' in s:
        return True
    return any(
        re.match(r'^\s*(def|class|import|from|async\s+def)\b', ln)
        for ln in s.splitlines()
    )


def ext_py(s: str) -> str:
    """从 LLM 回复中提取 Python 代码。优先取 [content] 标记，其次取首个
    def/class/import 起的连续代码段；均无则取整段。"""
    m = re.search(r'\[content\]([\s\S]*?)\[/content\]', s)
    if m:
        return m.group(1).strip()
    m = re.search(r'```python\s*([\s\S]*?)```', s, flags=re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'```\s*([\s\S]*?)```', s)
    if m:
        return m.group(1).strip()
    # 取首个 def/class/import 行到文本结尾，跳过前面的分析文字
    lines = s.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r'^\s*(def|class|import|from|async\s+def)\b', ln.strip()):
            return '\n'.join(lines[i:]).strip()
    return s.strip()


def repl_ins(text: str):
    """把 <|x|> 指令符号改写为 </x/>，与 openai.py 的 repl_ins_token 一致，
    避免模型把提示词里的占位符误当指令。"""
    repl = lambda s: re.sub(r'<\|([\w\-\.]+)\|>', r'</\1/>', s)
    return [{'role': 'user', 'content': repl(text)}]


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

class E2PyAgent:
    """易语言 -> Python 转换 agent，封装文件发现、分块、翻译、校验。"""

    def __init__(self, args):
        self.args = args
        self.model = args.model
        self.src_path = path.abspath(args.fname)
        self.in_dir = (
            self.src_path if path.isdir(self.src_path)
            else path.dirname(self.src_path)
        )
        base = path.basename(self.in_dir).rstrip('/\\') or 'epl'
        self.out_dir = path.join(path.dirname(self.in_dir), base + '_py')
        self.cache_dir = path.join(self.out_dir, '.cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        set_openai_props(self.args)

    # ---- 文件发现 / IO ----

    def list_src_files(self) -> list:
        if path.isfile(self.src_path):
            return [self.src_path]
        exts = {e.strip().lower() for e in self.args.ext.split(',') if e.strip()}
        fnames = []
        for root, dirs, fs in os.walk(self.src_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in fs:
                if extname(f).lower() in exts:
                    fnames.append(path.join(root, f))
        return sorted(fnames)

    def rel_of(self, fname: str) -> str:
        return path.relpath(fname, self.in_dir)

    def out_fname(self, rel: str) -> str:
        stem, _ = path.splitext(rel)
        return path.join(self.out_dir, stem + '.py')

    @staticmethod
    def read_e_source(fname: str):
        """按易语言常见编码读取源码；二进制/编译态文件返回 None。"""
        data = open(fname, 'rb').read()
        if not data:
            return ''
        if b'\x00' in data[:4096]:
            return None
        for enc in ('utf-8-sig', 'gbk', 'utf-16'):
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, ValueError):
                continue
        return data.decode('utf-8', 'ignore')

    # ---- 分块 ----

    @staticmethod
    def split_e_source(text: str, max_chars: int):
        """取出公共头部，按 .子程序 边界把源码分成若干块。"""
        lines = text.split('\n')
        cut = None
        for i, ln in enumerate(lines):
            if re.match(r'^\s*\.子程序\b', ln):
                cut = i
                break
        if cut is None:  # 没有 .子程序（窗口 XML、纯声明页），整段都当主体
            header, body = '', lines
        else:
            header = '\n'.join(lines[:cut]).strip()
            body = lines[cut:]
        chunks, cur, n = [], [], 0
        for ln in body:
            cur.append(ln)
            n += len(ln) + 1
            if n >= max_chars and re.match(r'^\s*\.子程序\b', ln):
                chunks.append('\n'.join(cur))
                cur, n = [], 0
        if cur:
            chunks.append('\n'.join(cur))
        return header, (chunks or [''])

    # ---- LLM 调用 ----

    def pace(self):
        """调用前的限流退避：共享/本地服务常限流(429)，串行时摊开请求。"""
        d = getattr(self.args, 'delay', 0) or 0
        if d:
            time.sleep(d)

    def _ask(self, ques: str):
        """绕过 ask_chatgpt_retry（它会在 content=None 时抛错），直接用底层
        client 调用，并在 content 为空时回退到 reasoning_content（推理模型
        常把代码放在 reasoning_content 里）。带指数退避重试与限流退避。"""
        import random
        import openai as oa
        last_ex = None
        client = oa.OpenAI(
            base_url=oa.base_url,
            api_key=oa.api_key,
            default_headers={'User-Agent': oa.user_agent},
            timeout=oa.timeout,
        )
        for i in range(self.args.retry):
            self.pace()
            try:
                extra_body = {}
                if isinstance(self.args.extra_body, str):
                    import json as _json
                    try:
                        extra_body = _json.loads(self.args.extra_body)
                    except Exception:
                        pass
                elif self.args.extra_body:
                    extra_body = dict(self.args.extra_body)
                if oa.no_think:
                    extra_body.update(NO_THINK_EXTRA_BODY)
                res = client.chat.completions.create(
                    messages=repl_ins(ques),
                    model=self.model,
                    temperature=self.args.temp,
                    top_p=self.args.top_p,
                    frequency_penalty=self.args.frequency_penalty,
                    presence_penalty=self.args.presence_penalty,
                    max_tokens=self.args.max_tokens,
                    extra_body=extra_body,
                )
                msg = res.choices[0].message
                cont_raw = msg.content or ''
                reasoning = getattr(msg, 'reasoning_content', None) or ''
                if isinstance(cont_raw, list):  # 少见：多段 content
                    cont_raw = ''.join(
                        p.get('text', '') for p in cont_raw if isinstance(p, dict))
                if isinstance(reasoning, list):
                    reasoning = ''.join(
                        p.get('text', '') for p in reasoning if isinstance(p, dict))
                # 优先 content；content 无代码时再看 reasoning_content 里有没有代码
                cont = cont_raw.strip()
                if not has_code_feature(cont):
                    if has_code_feature(reasoning):
                        cont = reasoning
                    else:
                        # 两者都无代码特征（纯思考/空回复），视为失败重试
                        raise ValueError(
                            '回复中无代码 (content 与 reasoning_content 均非代码)')
                out = ext_py(cont)
                if not out:
                    raise ValueError('提取到的代码为空（可能只输出空 [content] 标签）')
                return out
            except KeyboardInterrupt:
                raise
            except Exception as ex:
                last_ex = ex
                backoff = min(2.0 * (2 ** min(i, 6)), 120)
                logger.warning('[重试 %d/%d] %s，%.0fs 后重试',
                               i + 1, self.args.retry, ex, backoff)
                time.sleep(backoff + random.random())
        raise last_ex

    def gen_python(self, header: str, chunk: str, idx: int, total: int) -> str:
        # 分块结果缓存：命中直接返回，断点续跑时避免重转已完成的块
        cache_key = path.join(
            self.cache_dir,
            'chunk_' + md5(f'{header}\n{idx}/{total}\n{chunk}') + '.py')
        if path.isfile(cache_key) and not self.args.force:
            code = read_text(cache_key)
            if code:
                return code
        if total > 1:
            # 多块时一律当作“段”翻译，避免模型重复输出公共头部
            ques = render_prompt(
                CHUNK_PMT, header=header or '（无）', src=chunk,
                idx=str(idx), total=str(total))
        else:
            ques = render_prompt(CONVERT_PMT, src=chunk, header_hint='')
        code = self._ask(ques)
        write_text(cache_key, code)
        return code

    def gen_window_layout(self, src: str) -> str:
        """窗口 XML 布局 -> PyQt6 布局代码（先去掉 base64 扩展属性）。"""
        src = XML_BLOB_ATTR_RE.sub('', src)
        ques = render_prompt(XML_PMT, src=src)
        return self._ask(ques)

    def repair_python(self, code: str, err: str) -> str:
        ques = render_prompt(REPAIR_PMT, code=code, err=err)
        return self._ask(ques)

    # ---- 校验 / 修复 ----

    @staticmethod
    def syntax_err(code: str):
        try:
            compile(code, '<e2py>', 'exec')
            return None
        except SyntaxError as ex:
            return f'第 {ex.lineno} 行: {ex.msg}'

    def verify_repair(self, code: str, rel: str) -> str:
        for _ in range(self.args.repair_rounds):
            err = self.syntax_err(code)
            if not err:
                return code
            logger.warning('[修复] %s: %s', rel, err)
            try:
                code = self.repair_python(code, err)
            except Exception as ex:
                logger.error('[修复失败] %s: %s', rel, ex)
                break
        return code

    # ---- 主流程 ----

    def convert_file(self, fname: str) -> str:
        rel = self.rel_of(fname)
        ofname = self.out_fname(rel)
        src = self.read_e_source(fname)
        if src is None:
            return 'skip-binary'
        if not src.strip():
            return 'skip-empty'

        cache_key = path.join(self.cache_dir, md5(src) + '.py')
        if path.isfile(cache_key) and not self.args.force:
            code = read_text(cache_key)
            if code:  # 空缓存视为无效，重转
                write_text(ofname, code)
                return 'cached'

        if extname(fname).lower() == 'xml':
            code = self.gen_window_layout(src)
        else:
            header, chunks = self.split_e_source(src, self.args.chunk_size)
            parts = []
            for i, ch in enumerate(chunks, 1):
                parts.append(self.gen_python(header, ch, i, len(chunks)))
            code = '\n\n'.join(parts)

        if self.args.verify:
            code = self.verify_repair(code, rel)

        if not code.strip():
            logger.error('[空结果] %s: 模型输出为空，跳过写入', rel)
            return 'skip-empty'
        write_text(cache_key, code)
        write_text(ofname, code)
        return 'ok'

    def run(self):
        logger.info('源目录: %s', self.in_dir)
        logger.info('输出目录: %s', self.out_dir)
        fnames = self.list_src_files()
        if not fnames:
            logger.warning('未发现可转换的易语言源码文件 (扩展名: %s)',
                           self.args.ext)
            return
        if self.args.list:
            for f in fnames:
                print(self.rel_of(f))
            return
        summary = {'ok': 0, 'cached': 0, 'skip-binary': 0, 'skip-empty': 0}
        for f in fnames:
            status = self.convert_file(f)
            summary[status] = summary.get(status, 0) + 1
            logger.info('[%s] %s', status, self.rel_of(f))
        logger.info('完成: %s', summary)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog='e2py',
        description='将易语言源码目录转换为 Python，输出到 {目录名}_py')
    p.add_argument('fname', help='易语言源码目录（或单个 .e 文件）')
    p.add_argument('-m', '--model',
                   default=os.environ.get('OPENAI_CHAT_MODEL')
                   or os.environ.get('OPENAI_MODEL') or 'gpt-4o',
                   help='模型名称')
    p.add_argument('-k', '--key',
                   default=os.environ.get('OPENAI_API_KEY'),
                   help='OpenAI API Key')
    p.add_argument('-H', '--host',
                   default=os.environ.get('OPENAI_BASE_URL'),
                   help='API base url')
    p.add_argument('-r', '--retry', type=int, default=100, help='重试次数')
    p.add_argument('-tm', '--temp', type=float, default=0.2, help='温度')
    p.add_argument('-tp', '--top-p', type=float, default=None, help='top-p')
    p.add_argument('-fp', '--frequency-penalty', type=float, default=None,
                   help='频率惩罚')
    p.add_argument('-pp', '--presence-penalty', type=float, default=None,
                   help='存在惩罚')
    p.add_argument('-mt', '--max-tokens', type=int, default=12000,
                   help='最大 token 数（默认 12000，避免推理模型输出被截断）')
    p.add_argument('-ua', '--user-agent',
                   default='claude-cli/2.1.41 (external, cli)',
                   help='HTTP User-Agent')
    p.add_argument('-st', '--stream', action='store_true', help='流式输出')
    p.add_argument('-eb', '--extra-body', default=None, help='额外请求体')
    p.add_argument('-ct', '--conn-timeout', type=int, default=60,
                   help='连接超时秒数')
    p.add_argument('-rt', '--read-timeout', type=int, default=120,
                   help='读取超时秒数')
    p.add_argument('-rr', '--repetition-regex', default='', help='重复检测正则')
    p.add_argument('-nt', '--no-think', action='store_true', help='关闭思考模式')
    p.add_argument('-x', '--ext', default=DEFAULT_EXTS,
                   help='要转换的文件扩展名(逗号分隔)，默认 %(default)s')
    p.add_argument('-c', '--chunk-size', type=int, default=12000,
                   help='分块大小(字符数)，超限将在 .子程序 边界切分')
    p.add_argument('--repair-rounds', type=int, default=3,
                   help='语法修复最大轮数')
    p.add_argument('--delay', type=float, default=2.0,
                   help='每次 LLM 调用前的等待秒数(限流退避，默认 2s)')
    p.add_argument('--no-verify', dest='verify', action='store_false',
                   default=True, help='跳过 compile 语法检查与修复')
    p.add_argument('--force', action='store_true', help='忽略缓存重新转换')
    p.add_argument('--list', action='store_true', help='只列出待转换文件，不调用 LLM')
    return p


def main():
    # Windows 控制台常为 GBK，统一以 UTF-8 输出，避免中文日志乱码
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    args = build_parser().parse_args()
    if not args.key:
        logger.error('缺少 API Key，请通过 -k 或环境变量 OPENAI_API_KEY 提供')
        sys.exit(1)
    E2PyAgent(args).run()


if __name__ == '__main__':
    main()