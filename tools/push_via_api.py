# -*- coding: utf-8 -*-
"""用 GitHub REST API 把本地 HEAD 提交上传到仓库。

为什么需要它：本机网络下 `git push` 连不上 github.com:443（git 协议被挡），
但 GitHub 的 HTTPS API 是通的。这个脚本用 Git Data API 把本地 git 里的
文件与提交信息原样推上去，不依赖 git 协议。

用法：
    python tools/push_via_api.py            # 推送当前分支到 origin 同名分支
    python tools/push_via_api.py --dry-run  # 只打印将要上传的内容
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_REPO = "jmh925/kepu-quiz"
API = "https://api.github.com"

BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".docx", ".db", ".ico", ".zip"}


def say(msg):
    """立刻刷新的输出。

    为什么需要：这个脚本要走多次网络请求（取远程状态、逐个上传 blob），
    原先用 print 不带 flush，在网络慢时**屏幕上什么都不显示**，
    看起来就像「卡死了」，实际是在等。所以每一步都要立刻可见。
    """
    print(msg, flush=True)


def git(*args):
    # core.quotepath=false：否则含中文的文件名会被输出成带引号的八进制转义，无法直接当路径用
    cmd = ["git", "-c", "core.quotepath=false"] + list(args)
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError("git %s 失败：%s" % (" ".join(args), out.stderr.decode("utf-8", "replace")))
    return out.stdout


def token():
    """从本机 git 凭证管理器取 GitHub 令牌（不写进任何文件）。"""
    proc = subprocess.run(
        ["git", "-c", "credential.helper=manager", "credential", "fill"],
        cwd=ROOT, input=b"protocol=https\nhost=github.com\n\n", capture_output=True)
    text = proc.stdout.decode("utf-8", "replace")
    user = pw = ""
    for line in text.splitlines():
        if line.startswith("username="):
            user = line[9:]
        elif line.startswith("password="):
            pw = line[9:]
    if not user or not pw:
        raise RuntimeError("没有拿到 GitHub 凭证，请先在本机登录一次 GitHub")
    return user, pw


def call(method, path, body=None, auth=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "kepu-quiz-pusher")
    if auth:
        raw = ("%s:%s" % auth).encode("utf-8")
        req.add_header("Authorization", "Basic " + base64.b64encode(raw).decode())
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=20) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError("GitHub API %s %s 失败 [%s]：%s" % (method, path, exc.code, detail[:300]))


def local_blobs():
    """{路径: blob sha}，取自本地 HEAD（提交里的内容，不是工作区的字节）。"""
    out = {}
    raw = git("ls-tree", "-r", "-z", "HEAD")
    for item in raw.decode("utf-8").split("\0"):
        if not item.strip():
            continue
        meta, path = item.split("\t", 1)
        mode, typ, sha = meta.split()
        if typ == "blob":
            out[path] = sha
    return out


def remote_blobs(commit_sha, auth):
    """{路径: blob sha}，取自远程某次提交。"""
    tree_sha = call("GET", "/repos/%s/git/commits/%s" % (OWNER_REPO, commit_sha),
                    auth=auth)["tree"]["sha"]
    tree = call("GET", "/repos/%s/git/trees/%s?recursive=1" % (OWNER_REPO, tree_sha), auth=auth)
    out = {}
    for e in tree.get("tree", []):
        if e["type"] == "blob":
            out[e["path"]] = e["sha"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", help="（保留参数，已不需要）旧做法是按某个本地提交算差异；"
                                   "现在直接和远程的树逐文件比 blob 哈希，比 --since 更准")
    ap.add_argument("--all", action="store_true", help="忽略哈希比对，强制全量上传")
    args = ap.parse_args()

    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    head = git("rev-parse", "HEAD").decode().strip()
    local = local_blobs()
    files = sorted(local)

    # 待上传的提交：API 方式一次只建一个提交对象，无法逐个还原多个本地提交，
    # 因此把「本地领先 origin/main 的那一串」的说明合并成一条，信息不丢。
    try:
        pending = git("log", "--pretty=%H%x1f%B%x1e", "origin/main..HEAD").decode("utf-8")
    except RuntimeError:
        pending = ""
    chunks = [c.strip() for c in pending.split("\x1e") if c.strip()]
    if len(chunks) > 1:
        subject = ("（本次通过 GitHub API 上传，合并以下 %d 个本地提交）\n\n" % len(chunks)) + \
                  "\n\n---\n\n".join(c.split("\x1f", 1)[-1] for c in chunks)
    elif chunks:
        subject = chunks[0].split("\x1f", 1)[-1]
    else:
        subject = git("log", "-1", "--pretty=%B").decode("utf-8").strip()

    say("分支：%s" % branch)
    say("本地提交：%s" % head[:10])
    say("文件数：%d" % len(files))
    if args.dry_run:
        for f in files[:15]:
            say("   " + f)
        return 0

    auth = token()
    repo = call("GET", "/repos/" + OWNER_REPO, auth=auth)
    remote_head = None
    try:
        ref = call("GET", "/repos/%s/git/ref/heads/%s" % (OWNER_REPO, branch), auth=auth)
        remote_head = ref["object"]["sha"]
    except RuntimeError:
        remote_head = None
    say("远程当前：%s" % (remote_head[:10] if remote_head else "（空）"))
    if remote_head == head:
        say("已经是同一个提交，无需上传")
        return 0

    # 决定要传哪些文件：直接拿本地 HEAD 的树和远程最新提交的树逐文件比 blob 哈希。
    # 为什么不按「本地提交之间的 diff」算：
    #   1) 这台机器 fetch 不通，origin/main 引用永远是旧的，diff 基点可能是几个提交
    #      之前的状态，会漏文件（远程曾因此和本地长期不一致）；
    #   2) 工作区换行符（CRLF）和提交里的字节不一样，按工作区文件上传会让远程
    #      的 blob 哈希对不上本地 HEAD，看起来永远「有 15 个文件不一致」。
    # 逐文件比哈希既准又省：一样的文件一个请求都不发。
    if remote_head:
        say("正在比对远程与本地 HEAD 的文件哈希…")
        remote = remote_blobs(remote_head, auth)
    else:
        remote = {}
    if args.all:
        changed = list(files)
        # 远程有、本地 HEAD 没有的路径要在新树里显式删除（base_tree 会保留未列出的路径）
        removed = sorted(set(remote) - set(local))
    elif remote:
        changed = sorted(p for p in files if remote.get(p) != local[p])
        removed = sorted(p for p in remote if p not in local)
    else:
        changed = list(files)
        removed = []
    say("需要上传的文件：%d / %d，需要在远程删除：%d" % (len(changed), len(files), len(removed)))
    for p in removed[:20]:
        say("   删除 " + p)
    if not changed and not removed:
        say("文件内容与远程完全一致，只更新提交信息")
    if args.dry_run:
        for f in changed[:20]:
            say("   " + f)
        return 0

    # 1) 逐个文件建 blob。
    # 内容取自提交里的 blob（git cat-file），不是工作区文件，这样远程那份就是
    # `git ls-tree -r HEAD` 所描述的内容，两边哈希可以对上。
    tree = []
    for i, rel in enumerate(changed, 1):
        content = git("cat-file", "blob", local[rel])
        ext = os.path.splitext(rel)[1].lower()
        if ext in BINARY_EXT:
            blob = call("POST", "/repos/%s/git/blobs" % OWNER_REPO, {
                "content": base64.b64encode(content).decode(),
                "encoding": "base64",
            }, auth=auth)
        else:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            blob = call("POST", "/repos/%s/git/blobs" % OWNER_REPO, {
                "content": text, "encoding": "utf-8",
            }, auth=auth)
        tree.append({"path": rel.replace("\\", "/"), "mode": "100644",
                     "type": "blob", "sha": blob["sha"]})
        if i % 10 == 0 or i == len(changed):
            say("  已上传 %d / %d 个文件" % (i, len(changed)))
    for rel in removed:
        # sha 置 null 即表示在该树里删掉这个路径
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})

    # 2) 建 tree / commit
    kwargs = {"tree": tree}
    if remote_head:
        kwargs["base_tree"] = call("GET", "/repos/%s/git/commits/%s" % (OWNER_REPO, remote_head),
                                   auth=auth)["tree"]["sha"]
    new_tree = call("POST", "/repos/%s/git/trees" % OWNER_REPO, kwargs, auth=auth)
    parents = [remote_head] if remote_head else []
    commit = call("POST", "/repos/%s/git/commits" % OWNER_REPO, {
        "message": subject, "tree": new_tree["sha"], "parents": parents,
    }, auth=auth)
    say("已创建提交：%s" % commit["sha"][:10])

    # 3) 更新分支引用
    if remote_head:
        call("PATCH", "/repos/%s/git/refs/heads/%s" % (OWNER_REPO, branch),
             {"sha": commit["sha"], "force": False}, auth=auth)
    else:
        call("POST", "/repos/%s/git/refs" % OWNER_REPO,
             {"ref": "refs/heads/" + branch, "sha": commit["sha"]}, auth=auth)
    say("已更新 %s 分支 → %s" % (branch, commit["sha"][:10]))
    say("仓库地址：https://github.com/%s" % OWNER_REPO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
