# -*- coding: utf-8 -*-
"""一键把服务端 + 公网隧道一起起来，并打印可以直接发给老师的地址。

为什么要有这个脚本：手动起一次要开两个窗口、等隧道打印地址、再把地址和口令抄下来，
每次重启地址还会变。这里把这几步合成一条命令，并且**先验证地址真的通了再打印**，
避免拿着一个还没生效的地址去发人。

它做的事：
  1. 检查 8000 端口上是否已有服务在跑，有就复用，不重复启动；
  2. 找不到 cloudflared 就自动下载到一个用户级目录（不进仓库，仓库保持干净）；
  3. 起隧道，从输出里解析出 https 地址；
  4. 轮询该地址的 /api/v1/health，通了才算成功；
  5. 打印学生端 / 管理端地址与管理员口令（口令从 backend/.env 读，不写死在代码里）；
  6. Ctrl+C 时收尾：隧道一定关掉，服务端只在"是本脚本起的"时候才关。

用法：
    python tools/share.py                 # 起服务 + 起隧道
    python tools/share.py --tunnel-only   # 服务已在跑，只起隧道
    python tools/share.py --no-tunnel     # 只起服务（不给别人看时用）
    python tools/share.py --port 8080
"""
import argparse
import io
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kepu_env                                        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
# cloudflared 是 50 MB 级的单文件，放用户目录而不是仓库，免得把仓库搞脏
TOOL_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                        "kepu-tools")
CF_EXE = os.path.join(TOOL_DIR, "cloudflared.exe")
CF_URL = ("https://github.com/cloudflare/cloudflared/releases/latest/download/"
          "cloudflared-windows-amd64.exe")
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def say(msg=""):
    print(msg, flush=True)


def rule(title=""):
    say("")
    say("=" * 66)
    if title:
        say("  " + title)
        say("=" * 66)


def find_python():
    """环境变量指定的解释器优先，否则用当前这个解释器。"""
    got = os.environ.get("KEPU_PYTHON") or os.environ.get("PYTHON")
    if got and (os.path.isabs(got) and os.path.exists(got) or not os.path.isabs(got)):
        return got
    return sys.executable or "python"


def pythonpath():
    """把仓库自带的依赖目录（backend/deps）挂上，这样不用 pip install 也能跑。"""
    deps = os.path.join(BACKEND, "deps")
    parts = [p for p in (deps if os.path.isdir(deps) else None,
                         os.environ.get("PYTHONPATH")) if p]
    return os.pathsep.join(parts)


def server_alive(port, timeout=3):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/v1/health" % port,
                                    timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def port_busy(port):
    """端口被占但没有健康响应（可能是别的东西占了）。"""
    import socket
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def ensure_cloudflared():
    got = os.environ.get("CLOUDFLARED")
    if got and os.path.exists(got):
        return got
    if os.path.exists(CF_EXE):
        return CF_EXE
    say("没有找到 cloudflared，正在自动下载（约 52 MB，只需一次）…")
    os.makedirs(TOOL_DIR, exist_ok=True)
    try:
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(CF_URL, headers={"User-Agent": "kepu-share"})
        with urllib.request.urlopen(req, timeout=180, context=ctx) as r, \
                open(CF_EXE, "wb") as fh:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            last_pct = -1
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    # 只在百分比变化时刷新，否则日志里会刷出几百行
                    if pct != last_pct:
                        last_pct = pct
                        print("\r  已下载 %3d%%（%.1f / %.1f MB）"
                              % (pct, done / 1048576, total / 1048576), end="", flush=True)
        say("")
        say("下载完成：%s" % CF_EXE)
        return CF_EXE
    except Exception as exc:
        if os.path.exists(CF_EXE):
            os.remove(CF_EXE)
        say("自动下载失败：%s" % exc)
        say("请手动下载 cloudflared-windows-amd64.exe 放到：%s" % CF_EXE)
        say("或用环境变量 CLOUDFLARED 指定它的完整路径。")
        return None


def start_server(port):
    py = find_python()
    env = dict(os.environ)
    pp = pythonpath()
    if pp:
        env["PYTHONPATH"] = pp
    # 新开一个窗口：服务端日志看得见，也不会和本脚本的输出搅在一起。
    # 刻意不加 --reload：reload 会再拉一个子进程，Ctrl+C 收尾时容易留下孤儿进程。
    creation = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    proc = subprocess.Popen(
        [py, "-X", "utf8", "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND, env=env, creationflags=creation)
    say("服务端已在新窗口启动（PID %d）" % proc.pid)
    return proc


def wait_server(port, seconds=30):
    for _ in range(seconds * 2):
        if server_alive(port):
            return True
        time.sleep(0.5)
    return False


def kill_stale_cloudflared():
    """起新隧道之前，先把残留的 cloudflared 进程清掉。

    这一步不是可有可无的：实测踩过坑——同时残留几个隧道进程时，新建的隧道会
    表现为「进程说连接已注册，但访问时 TLS 握手就被断」
    （SSL: UNEXPECTED_EOF_WHILE_READING），而且连续换好几个地址都一样，
    很容易误判成"网络不支持隧道"。把残留清干净、只留一个，第一次就通。
    本脚本异常退出（比如窗口被直接关掉）时最容易留下残留，所以每次启动都清一次。
    """
    if os.name != "nt":
        return
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq cloudflared.exe", "/NH"],
                             capture_output=True, text=True, timeout=15).stdout or ""
        if "cloudflared.exe" not in out:
            return
        say("发现残留的隧道进程，先清理掉，避免它们互相干扰…")
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, timeout=15)
        time.sleep(2)
    except Exception:
        pass


def start_tunnel(port):
    """起隧道并解析出地址。

    输出读取放在单独的线程里、结果丢进队列：直接在主线程 readline() 的话，
    cloudflared 安静一段时间就会把主线程堵死，Ctrl+C 也反应不过来。
    """
    exe = ensure_cloudflared()
    if not exe:
        return None, None, None, None
    say("正在建立隧道…")
    kill_stale_cloudflared()
    log = os.path.join(TOOL_DIR, "cloudflared.log")
    fh = open(log, "w", encoding="utf-8", errors="replace")
    # 刻意不加 --protocol：默认的 QUIC 实测更快（约 1.3 秒首包）。
    # 注意一个踩过的坑：曾经出现过「隧道进程显示已注册连接，但访问时 TLS 握手就被断
    # （SSL: UNEXPECTED_EOF_WHILE_READING）」，连换几个地址都一样。当时以为是协议问题，
    # 其实真正的原因是**同时残留着好几个隧道进程**在互相干扰；把残留进程清干净、
    # 只起一个之后，第一次就通了。所以关键在 kill_stale_cloudflared()，不在协议。
    proc = subprocess.Popen([exe, "tunnel", "--url", "http://127.0.0.1:%d" % port,
                             "--no-autoupdate"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    lines = queue.Queue()

    def pump():
        try:
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass
        lines.put(None)          # 结束标记

    threading.Thread(target=pump, daemon=True).start()

    url = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            if proc.poll() is not None:
                break
            continue
        if line is None:
            break
        fh.write(line)
        fh.flush()
        found = URL_RE.search(line)
        if found and not url:
            url = found.group(0)
            break
    return proc, url, fh, lines


def wait_public(url, seconds=45):
    """隧道地址要等 Cloudflare 侧生效，这里轮询到真的能返回 200 为止。"""
    target = url.rstrip("/") + "/api/v1/health"
    deadline = time.time() + seconds
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with urllib.request.urlopen(target, timeout=15) as r:
                if r.status == 200:
                    say("")
                    return True, attempt
        except Exception:
            pass
        print("\r  等待公网地址生效…（第 %d 次）" % attempt, end="", flush=True)
        time.sleep(3)
    say("")
    return False, attempt


def kill_quietly(proc, fh=None):
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    if fh:
        try:
            fh.close()
        except Exception:
            pass


def open_tunnel(port, attempts=3):
    """建隧道并确认公网真的能通；不通就换一个地址重来。

    为什么要重试：cloudflared 的免账号快速隧道**不保证可用性**（Cloudflare 自己
    在启动横幅里就写了）。实测会遇到这种情况——隧道进程显示已注册连接，但
    Cloudflare 边缘还没给这个主机名配好证书，访问直接 TLS 握手就断
    （SSL: UNEXPECTED_EOF_WHILE_READING），而且等下去也不一定自己好。
    与其把一个打不开的地址发给老师，不如换一个主机名重试。
    """
    for i in range(1, attempts + 1):
        if i > 1:
            say("换一个地址重试（第 %d / %d 次）…" % (i, attempts))
            time.sleep(3)
        proc, url, fh, lines = start_tunnel(port)
        if not url:
            kill_quietly(proc, fh)
            continue
        say("隧道地址：%s" % url)
        ok, _ = wait_public(url)
        if ok:
            return proc, url, fh, lines
        say("这个地址在 Cloudflare 边缘没起来，弃用。")
        kill_quietly(proc, fh)
        time.sleep(2)
    return None, None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    ap.add_argument("--tunnel-only", action="store_true", help="服务已在跑，只起隧道")
    ap.add_argument("--no-tunnel", action="store_true", help="只起服务，不建隧道")
    args = ap.parse_args()

    rule("科普闯关系统 · 一键对外演示")
    say("仓库：%s" % ROOT)
    say("")

    admin_user, admin_pwd = kepu_env.admin_credentials()
    rotated = bool(kepu_env.read_env().get("ADMIN_PASSWORD"))
    if not rotated:
        say("  ！ backend/.env 不存在 —— 现在用的是 config.py 里的默认口令，")
        say("    而那个口令写在公开仓库里。对外演示前请先跑：")
        say("        python tools/gen_secrets.py    然后重新运行本脚本")
        say("")

    server_proc = None
    if not args.tunnel_only:
        alive = server_alive(args.port)
        if alive:
            say("端口 %d 上已经有服务在跑，直接复用。" % args.port)
        elif port_busy(args.port):
            say("端口 %d 被别的程序占用了。换一个：python tools/share.py --port 8080"
                % args.port)
            return 2
        else:
            server_proc = start_server(args.port)
            if not wait_server(args.port):
                say("服务端起不来，请看新开的那个窗口里的报错。")
                return 3
        say("服务端就绪：http://127.0.0.1:%d/api/v1/health" % args.port)

    tunnel_proc = None
    public = None
    fh = None
    lines = None
    try:
        if not args.no_tunnel:
            tunnel_proc, public, fh, lines = open_tunnel(args.port)
            if not public:
                say("")
                say("试了 3 个地址都没能在 Cloudflare 边缘起来。这通常是本机网络对")
                say("Cloudflare 隧道不友好（比如公司网络限制了 UDP/QUIC 出站）。可以：")
                say("  1. 稍后重跑本脚本；")
                say("  2. 用 --no-tunnel 只在本机演示；")
                say("  3. 换用 ngrok 等其它隧道工具（同样需要命令行）。")
                say("cloudflared 的日志在：%s" % os.path.join(TOOL_DIR, "cloudflared.log"))
                return 4

        rule("把下面这些发给老师")
        if public:
            say("")
            say("  学生端   %s/app/" % public)
            say("  管理端   %s/admin/" % public)
            say("")
            say("  管理员账号：%s" % admin_user)
            say("  管理端口令：%s" % admin_pwd)
            say("")
        say("  本机也可以继续用 http://127.0.0.1:%d/app/" % args.port)
        if public:
            say("")
            say("  注意：这个地址是临时的 —— 关掉本窗口、或者电脑休眠，它立刻失效；")
            say("        下次重开还会换一个新的，所以要重发一次。")
        rule()
        say("按 Ctrl+C 结束。")
        say("")

        # 隧道输出继续转存到日志；主循环只做非阻塞轮询，保证 Ctrl+C 随时有反应
        while True:
            if tunnel_proc is not None:
                try:
                    while True:
                        line = lines.get_nowait()
                        if line is None:
                            tunnel_proc = None
                            break
                        if fh:
                            fh.write(line)
                            fh.flush()
                except queue.Empty:
                    pass
                if tunnel_proc is not None and tunnel_proc.poll() is not None:
                    tunnel_proc = None
                if tunnel_proc is None:
                    say("隧道进程已退出。")
                    break
            elif server_proc is not None and server_proc.poll() is not None:
                say("服务端进程已退出。")
                break
            time.sleep(0.4)
    except KeyboardInterrupt:
        say("")
        say("正在收尾…")
    finally:
        if tunnel_proc is not None and tunnel_proc.poll() is None:
            tunnel_proc.terminate()
            say("隧道已关闭。")
        if server_proc is not None and server_proc.poll() is None:
            server_proc.terminate()
            say("服务端已关闭（它本来就是这个脚本起的）。")
        elif not args.tunnel_only:
            say("服务端保持运行（不是本脚本起的，或已在别的窗口）。")
        if fh:
            fh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
