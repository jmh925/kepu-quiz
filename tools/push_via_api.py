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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--since", help="只上传该提交之后变化的文件（默认与远程最新提交比较）。"
                                   "不传则全量上传——文件多时会慢很多")
    ap.add_argument("--all", action="store_true", help="强制全量上传")
    args = ap.parse_args()

    branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
    head = git("rev-parse", "HEAD").decode().strip()
    files = [f for f in git("ls-files").decode("utf-8").split("\n") if f]

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
    say("待上传提交数：%d" % max(1, len(chunks)))
    say("提交信息首行：%s" % subject.split("\n")[0][:70])
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

    # 只上传变化的文件。
    # 为什么重要：API 方式每个文件都要单独发一次请求，全量重传 138 个文件
    # 会非常慢（这也是之前「感觉卡住了」的原因）。GitHub 的 tree API 支持
    # base_tree：未列出的文件自动沿用上一棵树，所以只传差异即可。
    since = args.since
    if args.all:
        changed = files
    else:
        base = since or remote_head
        try:
            # 用 -z 取以 NUL 分隔的原始字节，再按 utf-8 解码：
            # 不能用默认输出——中文文件名会被转义成 "\351\246\226" 这种八进制，
            # 既对不上真实路径，也会让解码抛异常。
            raw = git("diff", "--name-only", "-z", base, head)
            changed = [p for p in raw.decode("utf-8").split("\0") if p]
            tracked = set(files)
            changed = [f for f in changed if f in tracked]
        except Exception as exc:
            say("（差异计算失败，回退为全量上传：%s）" % exc)
            changed = files
    say("需要上传的文件：%d / %d（其余沿用远程已有内容）" % (len(changed), len(files)))
    if not changed:
        say("没有文件变化，只更新提交信息")
    if args.dry_run:
        for f in changed[:20]:
            say("   " + f)
        return 0

    # 1) 逐个文件建 blob
    tree = []
    for i, rel in enumerate(changed, 1):
        path = os.path.join(ROOT, rel)
        with open(path, "rb") as fh:
            content = fh.read()
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
