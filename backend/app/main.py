# -*- coding: utf-8 -*-
"""应用入口：装配路由、统一异常处理、CORS、静态管理端。

启动方式（两种都行）：
    scripts\\run_server.cmd                 # 推荐的 Windows 一键启动
    python -m uvicorn app.main:app --reload # 在 backend/ 目录下手动启动

接口文档：http://127.0.0.1:8000/docs
管理端：  http://127.0.0.1:8000/admin/
"""
import mimetypes
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import admin as admin_module
from . import admin_db
from . import database as db
from . import routers
from .config import BASE_DIR, settings

# ------------------------------------------------------------------
# 静态资源的 MIME 类型必须显式注册。
#
# 为什么：Python 3.13 起 mimetypes 收紧了内置映射表，不再认识 .css / .js，
# StaticFiles 会把它们猜成 application/x-css、application/x-js；
# 而浏览器对样式表与脚本是**严格检查 MIME** 的，类型不对就整段丢弃——
# 表现是「页面没有样式、脚本不执行、按钮点了没反应」，
# 从外观上极容易被误判成「前端没渲染」，实际是响应头的问题。
# 这个坑踩过一次（网页版上线后打不开），务必保留这段。
# ------------------------------------------------------------------
for _ext, _type in (
    (".css", "text/css"),
    (".js", "text/javascript"),
    (".mjs", "text/javascript"),
    (".json", "application/json"),
    (".svg", "image/svg+xml"),
    (".woff2", "font/woff2"),
    (".map", "application/json"),
):
    mimetypes.add_type(_type, _ext)


class TypedStaticFiles(StaticFiles):
    """静态文件：显式给出常见前端资源的 MIME，避免运行环境差异导致整页失效。"""

    _EXTRA = {
        ".css": "text/css",
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".html": "text/html",
    }

    def guess_type(self, path):
        ext = os.path.splitext(str(path))[1].lower()
        if ext in self._EXTRA:
            return self._EXTRA[ext]
        return super().guess_type(path)

app = FastAPI(
    title="科普知识闯关小程序 · 服务端",
    description="中小学生科普知识闯关小程序的设计与实现 —— 后端接口文档",
    version="1.0.0",
)

# 跨域：联调阶段放开，生产环境应改为小程序合法域名白名单
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routers.router)
app.include_router(admin_module.router)


# ---------------- 统一异常处理 ----------------
@app.exception_handler(admin_module.AdminAuthError)
async def _admin_auth_error(request: Request, exc: Exception):
    """管理端未通过鉴权。"""
    return JSONResponse(status_code=401,
                        content={"code": 4011, "message": "管理端登录已失效，请重新登录", "data": None})


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: Exception):
    """入参校验失败统一归为 4000，不暴露框架内部细节。"""
    return JSONResponse(status_code=400,
                        content={"code": 4000, "message": "参数格式不正确，请检查后重试", "data": None})


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    """兜底异常：对外只给统一提示，细节留给服务端日志。"""
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500,
                        content={"code": 5000, "message": "服务器开小差了，请稍后再试", "data": None})


@app.on_event("startup")
def _startup():
    """启动时建表、补齐默认管理员，保证「拉下来就能跑」。"""
    db.get_conn()
    created = admin_db.ensure_default_admin()
    if created:
        print("[startup] 已创建默认管理员账号：%s" % settings.admin_username)
    print("[startup] 数据库：%s" % settings.db_path)
    print("[startup] 大模型：%s" % ("已配置 DeepSeek Key" if settings.deepseek_api_key
                                   else "未配置 Key，出题自动降级内置题库"))


@app.get("/")
def index():
    """根路径直接跳到学生端网页版，方便演示时只记一个地址。"""
    from fastapi.responses import RedirectResponse
    if os.path.isdir(_web_dir):
        return RedirectResponse(url="/app/")
    return {
        "code": 0, "message": "ok",
        "data": {
            "service": "科普闯关系统 · 服务端",
            "version": app.version,
            "docs": "/docs",
            "admin": "/admin/",
            "api_prefix": "/api/v1",
        },
    }


# ---------------- 学生端网页版 ----------------
# 网页版是「开箱可演示」的主力入口：后端一启动，打开 / 就能直接用，
# 不需要小程序开发者工具，也不依赖任何构建步骤。
_web_dir = os.path.join(os.path.dirname(BASE_DIR), "web")
if os.path.isdir(_web_dir):
    app.mount("/app", TypedStaticFiles(directory=_web_dir, html=True), name="web")

# ---------------- 管理端静态页面 ----------------
_admin_dir = os.path.join(os.path.dirname(BASE_DIR), "admin")
if os.path.isdir(_admin_dir):
    app.mount("/admin", TypedStaticFiles(directory=_admin_dir, html=True), name="admin")
