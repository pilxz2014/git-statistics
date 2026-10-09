#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 提交统计 —— 采集脚本（M1）

用法示例：
    python collect.py D:/my/project                    # 统计当前分支
    python collect.py D:/my/project --branch develop   # 统计指定分支
    python collect.py D:/my/project --list-branches    # 仅列出本地分支名(JSON)
    python collect.py D:/my/project -o out.json        # 指定输出路径

仅依赖 Python 标准库（subprocess / json / re / argparse / datetime），跨平台。
输出 commits.json，结构见 docs/需求文档.md §5：

    repo { name, path, generatedAt }
    analyzedBranch            # 本次被统计的（单个）分支
    branches []               # 仓库分支清单（轻量参考：名称/是否当前/提交数/最后提交/领先落后）
    authors []                # 去重后的作者列表
    commits []                # 该分支上的全部提交（含 add/delete、files、file_ext、type）

说明：
- 统计只针对「一个分支」（默认当前分支），避免全分支慢扫。
- 分支清单用轻量命令采集（for-each-ref + rev-list --count + left-right count），
  不做逐提交的 numstat 重扫。
- TODO(M2)：报告端按日期分桶时，需按提交的本地时区（when 字段带偏移）折日，
  避免 UTC 日界与本地日界不一致导致跨天错位。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

# 通过 git 的 %x1f 生成分隔符；HEADER_MARK 只传 ASCII，避免 Windows 命令行携带控制字符
HEADER_MARK = "__C__"
SEP = "\x1f"
FMT = HEADER_MARK + "%x1f" + "%x1f".join(["%H", "%an", "%ae", "%aI", "%s", "%P"])

# 与报告模板的提交类型集合对齐
CANONICAL_TYPES = ("feat", "fix", "refactor", "docs", "perf", "test", "chore", "style", "other")

_CONV_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?!?:")


def force_utf8_streams():
    """尽量让 stdout/stderr 以 UTF-8 输出，避免 Windows 管道下中文乱码。

    pythonw（无控制台）下 sys.stdout/stderr 可能为 None，先兜底成丢弃流，
    避免 print(..., file=sys.stderr) 抛 TypeError 导致静默崩溃。
    """
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


_WINDOWS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_git(args, repo):
    """执行 git 命令，返回 (returncode, stdout_text, stderr_text)。"""
    proc = subprocess.run(
        ["git", "-C", repo] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_WINDOWS_NO_WINDOW,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, out, err


def is_git_repo(repo):
    """兼容普通仓库（.git 目录）与 worktree / 子模块（.git 文件）。"""
    return os.path.exists(os.path.join(repo, ".git"))


def current_branch(repo):
    rc, out, _ = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    if rc != 0:
        return None
    name = out.strip()
    return name if name and name != "HEAD" else None  # 分离 HEAD -> None


def list_branch_names(repo):
    rc, out, _ = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], repo)
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def branch_refs(repo, current):
    """分支清单参考信息：名称 / 是否当前 / 提交数 / 最后提交 / 领先落后（相对 main|master）。"""
    names = list_branch_names(repo)
    base = next((n for n in ("main", "master") if n in names), None)

    refs = []
    for name in names:
        item = {"name": name, "current": name == current, "last": None,
                "commits": 0, "ahead": None, "behind": None}

        rc, last, _ = run_git(["log", "-1", "--format=%cs", name], repo)  # %cs = 提交日期 YYYY-MM-DD
        if rc == 0 and last.strip():
            item["last"] = last.strip()

        rc, cnt, _ = run_git(["rev-list", "--count", name], repo)
        if rc == 0:
            item["commits"] = int(cnt.strip() or 0)

        if base:
            if name == base:
                item["ahead"] = item["behind"] = 0
            else:
                # git rev-list --left-right --count base...name
                #   左列 = 仅 base 有的提交数（即 name 落后 base）
                #   右列 = 仅 name 有的提交数（即 name 领先 base）
                rc, ab, _ = run_git(["rev-list", "--left-right", "--count", "%s...%s" % (base, name)], repo)
                if rc == 0:
                    parts = ab.split()
                    if len(parts) == 2:
                        try:
                            item["behind"] = int(parts[0])
                            item["ahead"] = int(parts[1])
                        except ValueError:
                            pass
        refs.append(item)
    return refs


def ext_of(path):
    """从路径提取扩展名；忽略隐藏文件（如 .gitignore）的『伪扩展』。"""
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:  # 无点，或点为开头（隐藏文件）
        return ""
    return "." + name[dot + 1:].lower()


def clean_path(p):
    """处理 numstat 里的重命名路径（形如 old => new）。"""
    p = p.strip()
    if " => " in p:
        p = p.split(" => ", 1)[1]
    elif p.startswith("=> "):
        p = p[3:]
    return p


def parse_num(s):
    """numstat 的增/删列；二进制文件显示为 '-'，按 0 计。"""
    s = s.strip()
    if s == "-":
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


def classify(subject, is_merge):
    """把提交归类到规范类型集合（Conventional Commits 优先，关键词兜底）。"""
    s = subject.strip()
    if is_merge:
        return "other"
    m = _CONV_RE.match(s)
    if m:
        t = m.group("type").lower()
        if t in ("feat", "fix", "docs", "style", "refactor", "perf", "test", "chore"):
            return t
        if t in ("build", "ci"):
            return "chore"
        if t == "revert":
            return "other"
    low = s.lower()
    if re.search(r"\b(fix|bug|修复|hotfix)\b", low):
        return "fix"
    if re.search(r"\b(docs|doc|readme|文档)\b", low):
        return "docs"
    if re.search(r"\btest", low):
        return "test"
    if re.search(r"\b(perf|性能|优化)\b", low):
        return "perf"
    if re.search(r"\b(refactor|重构)\b", low):
        return "refactor"
    if re.search(r"\b(style|格式|样式)\b", low):
        return "style"
    if re.search(r"\b(chore|依赖|构建|配置)\b", low):
        return "chore"
    return "other"


def collect_commits(repo, branch, progress=None):
    """流式解析 git log --numstat，返回该分支所有提交。"""
    cmd = [
        "git", "-C", repo, "-c", "core.quotepath=false",
        "log", branch,
        "--date=iso-strict",
        "--numstat",
        "--pretty=format:" + FMT,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_WINDOWS_NO_WINDOW)

    commits = []
    cur = None

    def _commit():
        if cur is None:
            return
        cur["type"] = classify(cur["subject"], cur["is_merge"])
        full = cur.pop("_hash_full")
        cur["hash"] = full[:7]
        cur["file_ext"] = sorted(cur["file_ext"])
        del cur["is_merge"]
        commits.append(cur)

    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith(HEADER_MARK):
            _commit()
            parts = line[len(HEADER_MARK):].split(SEP)[1:]  # 去掉首个空段
            if len(parts) < 5:
                cur = None
                continue
            parents = parts[5].split() if len(parts) > 5 else []
            cur = {
                "_hash_full": parts[0],
                "author": parts[1],
                "email": parts[2],
                "when": parts[3],
                "subject": parts[4],
                "is_merge": len(parents) >= 2,
                "additions": 0,
                "deletions": 0,
                "files": [],
                "file_ext": set(),
            }
        elif line.strip() and cur is not None:
            cols = line.split("\t", 2)
            if len(cols) != 3:
                continue
            add_s, del_s, path = cols
            path = clean_path(path)
            cur["additions"] += parse_num(add_s)
            cur["deletions"] += parse_num(del_s)
            if path:
                cur["files"].append(path)
                ext = ext_of(path)
                if ext:
                    cur["file_ext"].add(ext)
        if progress:
            progress(len(commits))

    _commit()
    proc.stdout.close()
    proc.wait()

    err = proc.stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        sys.stderr.write(err)
    return commits


def make_progress():
    state = {"last": 0}

    def cb(n):
        if n - state["last"] >= 2000:
            sys.stderr.write("  已解析 %d 条提交…\n" % n)
            sys.stderr.flush()
            state["last"] = n

    return cb


def main(argv=None):
    ap = argparse.ArgumentParser(description="Git 提交统计采集脚本（输出 commits.json）")
    ap.add_argument("repo", help="Git 仓库目录（含 .git）")
    ap.add_argument("--branch", help="要统计的分支（默认当前分支）")
    ap.add_argument("--list-branches", action="store_true", help="仅列出本地分支名(JSON)后退出")
    ap.add_argument("--output", "-o", help="输出 JSON 路径（默认 ./commits.json）")
    ap.add_argument("--quiet", "-q", action="store_true", help="不打印进度")
    args = ap.parse_args(argv)
    force_utf8_streams()

    repo = os.path.abspath(args.repo)
    if not is_git_repo(repo):
        sys.stderr.write("错误：%s 不是 Git 仓库（未找到 .git）\n" % repo)
        return 1

    if args.list_branches:
        print(json.dumps(list_branch_names(repo), ensure_ascii=False))
        return 0

    cur = current_branch(repo)
    branch = args.branch or cur
    if not branch:
        sys.stderr.write("错误：无法确定当前分支（可能是分离 HEAD），请用 --branch 指定\n")
        return 1

    rc, _, err = run_git(["rev-parse", "--verify", branch], repo)
    if rc != 0:
        sys.stderr.write("错误：分支 %s 不存在\n%s" % (branch, err))
        return 1

    if not args.quiet:
        sys.stderr.write("仓库：%s\n统计分支：%s\n正在采集提交…\n" % (repo, branch))

    commits = collect_commits(repo, branch, progress=None if args.quiet else make_progress())

    if not args.quiet:
        sys.stderr.write("共 %d 条提交，正在汇总分支清单…\n" % len(commits))
    refs = branch_refs(repo, branch)

    data = {
        "repo": {
            "name": os.path.basename(repo.rstrip("/\\")) or "repository",
            "path": repo,
            "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "analyzedBranch": branch,
        "branches": refs,
        "authors": sorted({c["author"] for c in commits}),
        "commits": commits,
    }

    out = os.path.abspath(args.output or "commits.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if not args.quiet:
        sys.stderr.write("已输出：%s\n" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())