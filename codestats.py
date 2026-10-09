#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 提交统计 —— 附带：代码详情统计（独立菜单项）

统计「当前工程」的代码构成：总文件数 / 总行数 / 代码行(非空) / 空行，
按扩展名、按目录、最大的文件、以及全量文件明细。

与 git 提交统计【分开】触发的理由：它要遍历工作区并逐文件数行，通常更耗时，
合并到 git 统计会拖慢「提交统计」的响应。

用法：
    python codestats.py <项目目录> [-o codestats.json] [-q]

文件清单获取方式（本工具不要求目录是 Git 仓库）：
- Git 仓库：用 `git ls-files --cached --others --exclude-standard`，精确尊重 .gitignore；
- 普通目录：遍历文件系统，跳过 node_modules / dist / .venv / .git 等常见目录。

仅依赖标准库。
"""

import argparse
import io
import json
import os
import subprocess
import sys
from datetime import datetime

_WINDOWS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 常见资源/二进制/生成物：计入文件数，但不数行
SKIP_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".pdf",
    ".zip", ".gz", ".tgz", ".tar", ".rar", ".7z", ".xz", ".bz2",
    ".exe", ".dll", ".so", ".dylib", ".class", ".jar", ".war", ".a", ".o",
    ".pyc", ".pyo", ".pyd", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flac", ".wav", ".ogg",
    ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt",
    ".bin", ".dat", ".map", ".lock",
}
SKIP_BASENAME = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "LICENSE", "LICENSE.txt", "LICENSE.md", "LICENSE-MIT",
}


def force_utf8_streams():
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


COMMON_SKIP_DIRS = {
    ".git", "node_modules", "bower_components", "vendor", "dist", "build", "target",
    "out", "bin", "obj", ".venv", "venv", "env", "__pycache__", ".idea", ".vscode",
    ".next", ".nuxt", "coverage", ".tox", ".mypy_cache", ".pytest_cache", ".cache",
    ".gradle", ".svn", ".hg", "Pods",
}


def list_project_files(repo):
    # 优先 git ls-files（精确尊重 .gitignore）；非 git 目录 / 列不出可用文件时退回文件系统遍历
    rels = []
    if os.path.exists(os.path.join(repo, ".git")):
        r = subprocess.run(
            # core.quotepath=false：中文等非 ASCII 路径不被转义，否则会读不到这些文件
            ["git", "-C", repo, "-c", "core.quotepath=false",
             "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_WINDOWS_NO_WINDOW,
        )
        if r.returncode == 0:
            rels = [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]
            # 防御：所列路径若在磁盘上大多不存在（编码/转义差异），弃用 git 结果改用遍历
            if rels and not any(os.path.exists(os.path.join(repo, x)) for x in rels[:20]):
                rels = []
    if rels:
        return rels
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in COMMON_SKIP_DIRS]
        for fn in files:
            full = os.path.join(root, fn)
            out.append(os.path.relpath(full, repo).replace("\\", "/"))
    return out


def is_binary(data):
    return b"\x00" in data[:8000]


def count_lines(data):
    if not data:
        return 0, 0
    lines = data.decode("utf-8", "replace").splitlines()
    total = len(lines)
    blank = sum(1 for ln in lines if not ln.strip())
    return total, blank


def analyze(repo, progress=None):
    rels = list_project_files(repo)
    if rels is None:
        return None
    total = len(rels)
    files = []
    by_ext = {}
    by_dir = {}
    n_files = n_lines = n_code = n_blank = 0

    for i, rel in enumerate(rels):
        if progress:
            progress(i, total)
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):  # 跳过子模块(gitlink)等非普通文件
            continue
        name = os.path.basename(rel)
        ext = os.path.splitext(name)[1].lower() or "(无扩展)"
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue

        if ext in SKIP_EXT or name in SKIP_BASENAME or is_binary(data):
            binary = True
            lines = blank = 0
        else:
            binary = False
            lines, blank = count_lines(data)
        code = lines - blank

        n_files += 1
        n_lines += lines
        n_code += code
        n_blank += blank
        files.append({"path": rel, "ext": ext, "lines": lines, "code": code, "blank": blank, "binary": binary})

        e = by_ext.get(ext)
        if e is None:
            e = by_ext[ext] = {"ext": ext, "files": 0, "lines": 0, "code": 0, "blank": 0, "binary": 0}
        e["files"] += 1
        e["lines"] += lines
        e["code"] += code
        e["blank"] += blank
        if binary:
            e["binary"] += 1

        d = os.path.dirname(rel) or "(根目录)"
        dd = by_dir.get(d)
        if dd is None:
            dd = by_dir[d] = {"dir": d, "files": 0, "lines": 0}
        dd["files"] += 1
        dd["lines"] += lines

    if progress:
        progress(total, total)

    return {
        "summary": {
            "files": n_files,
            "lines": n_lines,
            "code": n_code,
            "blank": n_blank,
            "exts": len(by_ext),
            "avg": (n_lines // n_files) if n_files else 0,
        },
        "byExt": sorted(by_ext.values(), key=lambda x: -x["lines"]),
        "byDir": sorted(by_dir.values(), key=lambda x: -x["lines"])[:30],
        "largest": sorted(files, key=lambda x: -x["lines"])[:20],
        "files": files,
    }


def make_progress():
    st = {"last": -1}

    def cb(done, total):
        if done - st["last"] >= 500:
            sys.stderr.write("  已统计 %d / %d 个文件…\n" % (done, total))
            sys.stderr.flush()
            st["last"] = done

    return cb


def main(argv=None):
    force_utf8_streams()
    ap = argparse.ArgumentParser(description="代码详情统计（输出 codestats.json）")
    ap.add_argument("repo", help="项目目录（含 .git）")
    ap.add_argument("--output", "-o", help="输出 JSON 路径（默认 ./codestats.json）")
    ap.add_argument("--quiet", "-q", action="store_true", help="不打印进度")
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(repo):
        sys.stderr.write("错误：目录不存在：%s\n" % repo)
        return 1

    if not args.quiet:
        sys.stderr.write("目录：%s\n正在统计代码详情…\n" % repo)

    result = analyze(repo, progress=None if args.quiet else make_progress())
    if result is None:
        sys.stderr.write("错误：统计失败（无法读取目录）\n")
        return 1

    result["repo"] = {
        "name": os.path.basename(repo.rstrip("/\\")) or "repository",
        "path": repo,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    out = os.path.abspath(args.output or "codestats.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        sys.stderr.write("已输出：%s\n" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())