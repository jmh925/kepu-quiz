# -*- coding: utf-8 -*-
"""管理端路由：账号与鉴权、运行看板、用户管理、题库维护、闯关记录、操作日志。

鉴权方式：请求头 X-Admin-Token，取值可以是登录接口签发的 JWT，
也可以是 .env 中配置的固定 ADMIN_TOKEN（便于自动化测试与本地调试）。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from . import admin_db
from .schemas import AdminLoginRequest, QuestionPoolRequest

router = APIRouter(prefix="/api/v1/admin")


def require_admin(x_admin_token: Optional[str] = Header(None)):
    """管理端鉴权依赖：校验失败统一返回 4011。"""
    admin = admin_db.verify_admin_token(x_admin_token)
    if not admin:
        raise AdminAuthError()
    return admin


class AdminAuthError(Exception):
    """未通过管理端鉴权。"""


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


def fail(code, message, status=400):
    return JSONResponse(status_code=status,
                        content={"code": code, "message": message, "data": None})


@router.post("/login")
async def admin_login(req: AdminLoginRequest):
    token, info = admin_db.admin_login(req.username, req.password)
    if not token:
        return fail(4011, info, 401)
    return ok({"token": token, "admin": info})


@router.get("/me")
async def admin_me(admin=Depends(require_admin)):
    return ok(admin)


@router.get("/dashboard")
async def admin_dashboard(admin=Depends(require_admin)):
    return ok(admin_db.dashboard())


@router.get("/trend")
async def admin_trend(days: int = 7, admin=Depends(require_admin)):
    return ok({"days": days, "points": admin_db.trend(days)})


@router.get("/users")
async def admin_users(keyword: Optional[str] = None, page: int = 1, size: int = 20,
                      admin=Depends(require_admin)):
    return ok(admin_db.list_users(keyword, page, size))


@router.post("/users/{user_id}/status")
async def admin_user_status(user_id: int, status: int = 1, admin=Depends(require_admin)):
    if not admin_db.set_user_status(user_id, status, admin["username"]):
        return fail(4000, "用户不存在", 404)
    return ok({"user_id": user_id, "status": status})


@router.get("/questions")
async def admin_questions(theme: Optional[str] = None, grade: Optional[str] = None,
                          keyword: Optional[str] = None, page: int = 1, size: int = 20,
                          admin=Depends(require_admin)):
    return ok(admin_db.list_pool(theme, grade, keyword, page, size))


@router.get("/questions/themes")
async def admin_themes(admin=Depends(require_admin)):
    return ok({"themes": admin_db.pool_themes()})


@router.post("/questions")
async def admin_question_create(req: QuestionPoolRequest, admin=Depends(require_admin)):
    qid, err = admin_db.create_pool_question(req.model_dump(exclude_none=True), admin["username"])
    if err:
        return fail(4000, err)
    return ok({"id": qid})


@router.put("/questions/{qid}")
async def admin_question_update(qid: int, req: QuestionPoolRequest,
                                admin=Depends(require_admin)):
    # exclude_unset：只更新请求里真正出现的字段，
    # 否则模型默认值（theme/grade/difficulty）会把已有记录改回默认值。
    payload = req.model_dump(exclude_unset=True, exclude_none=True)
    ok_flag, err = admin_db.update_pool_question(qid, payload, admin["username"])
    if not ok_flag:
        return fail(4000, err, 404 if "不存在" in (err or "") else 400)
    return ok({"id": qid})


@router.delete("/questions/{qid}")
async def admin_question_delete(qid: int, admin=Depends(require_admin)):
    if not admin_db.delete_pool_question(qid, admin["username"]):
        return fail(4000, "题目不存在", 404)
    return ok({"deleted": qid})


@router.get("/sessions")
async def admin_sessions(page: int = 1, size: int = 20, grade: Optional[str] = None,
                         source: Optional[str] = None, admin=Depends(require_admin)):
    return ok(admin_db.list_sessions(page, size, grade, source))


@router.get("/logs")
async def admin_logs(limit: int = 50, admin=Depends(require_admin)):
    return ok({"logs": admin_db.list_logs(limit)})
