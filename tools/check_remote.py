# -*- coding: utf-8 -*-
"""核对 GitHub 上的 main 分支与本地 HEAD 是否完全一致。

为什么要单独写这个：这台机器到 github.com:443 的 git 协议不通（推送走
tools/push_via_api.py 的 REST API），所以本地 origin/main 引用永远是旧的，
`git log origin/main..HEAD` 会骗人。唯一可靠的核对办法是把本地
`git ls-tree -r HEAD` 的 blob 哈希和远程 Git Tree API 的哈希逐条比对。

用法：python tools/check_remote.py
"""
import base64
import io
import json
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import os                                                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_REPO = "jmh925/kepu-quiz"
BRANCH = "main"
API = "https://api.github.com"


def git(*args):
    out = subprocess.run(["git", "-c", "core.quotepath=false"] + list(args),
                         cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace"))
    return out.stdout.decode("utf-8", "replace")


def token():
    proc = subprocess.run(["git", "-c", "credential.helper=manager", "credential", "fill"],
                          cwd=ROOT, input=b"protocol=https\nhost=github.com\n\n",
                          capture_output=True)
    user = pw = ""
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("username="):
            user = line[9:]
        elif line.startswith("password="):
            pw = line[9:]
    if not pw:
        raise RuntimeError("没有拿到 GitHub 凭证")
    return user, pw


def call(path, auth=None):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "kepu-remote-check")
    if auth:
        raw = ("%s:%s" % auth).encode("utf-8")
        req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API %s 返回 %s：%s" % (path, exc.code, exc.read()[:200]))


def local_tree():
    """{路径: blob sha}，取自本地 HEAD。"""
    out = {}
    for line in git("ls-tree", "-r", "HEAD").splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        mode, typ, sha = meta.split()
        if typ == "blob":
            out[path] = sha
    return out


def remote_tree(auth):
    head = call("/repos/%s/commits/%s" % (OWNER_REPO, BRANCH), auth)
    sha = head["sha"]
    tree = call("/repos/%s/git/trees/%s?recursive=1" % (OWNER_REPO, head["commit"]["tree"]["sha"]),
                auth)
    out = {}
    for e in tree.get("tree", []):
        if e["type"] == "blob":
            out[e["path"]] = e["sha"]
    if tree.get("truncated"):
        print("！远程树被截断，比对结果不完整")
    return sha, head["commit"]["message"].splitlines()[0], out


def main():
    auth = token()
    local = local_tree()
    sha, msg, remote = remote_tree(auth)
    print("远程 main  = %s" % sha[:10])
    print("远程提交信息 = %s" % msg)
    print("本地 HEAD  = %s" % git("rev-parse", "HEAD").strip()[:10])
    print("本地文件 %d 个 / 远程文件 %d 个" % (len(local), len(remote)))

    missing = sorted(set(local) - set(remote))
    extra = sorted(set(remote) - set(local))
    differ = sorted(p for p in set(local) & set(remote) if local[p] != remote[p])

    for label, items in (("远程缺失", missing), ("远程多出", extra), ("内容不一致", differ)):
        if items:
            print("\n%s（%d）：" % (label, len(items)))
            for p in items[:30]:
                print("   " + p)
            if len(items) > 30:
                print("   …… 还有 %d 个" % (len(items) - 30))

    if not (missing or extra or differ):
        print("\n[OK] 远程 main 与本地 HEAD 完全一致。")
        return 0
    print("\n[FAIL] 远程与本地不一致，请重新运行 tools/push_via_api.py --all。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
