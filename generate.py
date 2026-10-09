#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 提交统计 —— 报告生成器（M2）

用法：
    python generate.py commits.json                  # 默认输出同目录 git-stats-report.html
    python generate.py commits.json -o report.html

读取 collect.py 生成的 commits.json，注入 report/template.html，
并把本地 ECharts（report/echarts.min.js，若存在）内联进去，产出
单个自包含、可离线双击打开的 HTML。

仅依赖标准库。若 report/echarts.min.js 缺失，则回退为 CDN 引用（需联网）。
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "report", "template.html")
ECHARTS = os.path.join(HERE, "report", "echarts.min.js")

CDN_FALLBACK = (
    '<script src="https://cdn.staticfile.org/echarts/5.4.3/echarts.min.js"></script>\n'
    '<script>if(!window.echarts){document.write(\'<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"><\\/script>\');}</script>'
)


def force_utf8_streams():
    import io
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 Git 提交统计报告（自包含 HTML）")
    ap.add_argument("json", help="commits.json 路径（collect.py 的输出）")
    ap.add_argument("--output", "-o", help="输出 HTML 路径（默认与 json 同目录 git-stats-report.html）")
    ap.add_argument("--template", help="模板路径（默认 report/template.html）")
    args = ap.parse_args(argv)
    force_utf8_streams()

    jpath = os.path.abspath(args.json)
    if not os.path.isfile(jpath):
        sys.stderr.write("错误：找不到 %s\n" % jpath)
        return 1
    with open(jpath, encoding="utf-8") as f:
        data = json.load(f)

    tpl = os.path.abspath(args.template) if args.template else TEMPLATE
    if not os.path.isfile(tpl):
        sys.stderr.write("错误：缺少模板 %s\n" % tpl)
        return 1
    html = read(tpl)

    if "__DATA_JSON__" not in html or "<!-- __ECHARTS__ -->" not in html:
        sys.stderr.write("错误：模板占位符缺失（__DATA_JSON__ / __ECHARTS__）\n")
        return 1

    # 注入数据：把 < 转义，防止提交信息里出现 </script> 而提前闭合
    data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = html.replace("__DATA_JSON__", data_json)

    # 注入 ECharts：优先本地内联（离线可用）
    if os.path.isfile(ECHARTS):
        js = read(ECHARTS).replace("</script", "<\\/script")
        html = html.replace("<!-- __ECHARTS__ -->", "<script>\n" + js + "\n</script>")
    else:
        sys.stderr.write("提示：未找到 report/echarts.min.js，回退为 CDN 引用（需联网）\n")
        html = html.replace("<!-- __ECHARTS__ -->", CDN_FALLBACK)

    out = os.path.abspath(args.output or os.path.join(os.path.dirname(jpath), "git-stats-report.html"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    sys.stderr.write("已生成报告：%s\n" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())