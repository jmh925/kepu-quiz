# -*- coding: utf-8 -*-
"""学生端路由层：参数解析、鉴权、统一响应封装（13 个接口，对应论文表 4-11）。

统一约定：
- 前缀 /api/v1；
- 响应体 {code, message, data}，code=0 为成功；
- 鉴权头 Authorization: Bearer <token>；未登录时以游客身份可用（user_id 为 None）。
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import JSONResponse

from . import grades
from . import services
from .config import settings
from .schemas import (
    AnswerSubmitRequest, LoginRequest, QuizGenerateRequest,
    ReportGenerateRequest, WrongItemRequest, WrongPracticeRequest,
)

router = APIRouter(prefix="/api/v1")

ALLOWED_EXT = (".txt", ".md", ".markdown", ".csv", ".pdf", ".docx")


def get_optional_user(authorization: Optional[str] = Header(None)):
    """可选鉴权：带合法 Token 时解析出 user_id，否则返回 None（游客）。"""
    if authorization and authorization.startswith("Bearer "):
        payload = services.decode_token(authorization[7:])
        if payload:
            return payload.get("uid")
    return None


def ok(data=None, message="ok"):
    return {"code": 0, "message": message, "data": data}


def fail(code, message, status=400):
    return JSONResponse(status_code=status,
                        content={"code": code, "message": message, "data": None})


# 1. 健康检查
@router.get("/health")
async def health():
    return ok({"status": "up", "llm_configured": bool(settings.deepseek_api_key),
               "model": settings.deepseek_model})


# 2. 学段选项
@router.get("/grades")
async def grade_options():
    return ok({"grades": grades.list_grades(), "default": grades.DEFAULT_GRADE})


# 3. 出题（含可选检索增强）
@router.post("/quiz/generate")
async def quiz_generate(req: QuizGenerateRequest,
                        user_id: Optional[int] = Depends(get_optional_user)):
    passed, code, reason = services.check_topic(req.topic)
    if not passed:
        return fail(code, reason)
    result = services.generate_quiz(req.topic.strip(), req.count, user_id,
                                    req.doc_id, req.grade)
    return ok(result)


# 4. 判题与结算
@router.post("/quiz/submit")
async def quiz_submit(req: AnswerSubmitRequest,
                      user_id: Optional[int] = Depends(get_optional_user)):
    result = services.submit_answer(req.quiz_id, req.answers, user_id, req.duration_ms)
    if result is None:
        return fail(4000, "没有找到这次闯关记录，请重新出题", 404)
    return ok(result)


# 5. 复盘报告
@router.post("/report/generate")
async def report_generate(req: ReportGenerateRequest,
                          user_id: Optional[int] = Depends(get_optional_user)):
    result = services.generate_report(req.quiz_id, user_id)
    if result is None:
        return fail(4000, "还没有提交答案，先完成闯关吧", 404)
    return ok(result)


# 6. 登录
@router.post("/user/login")
async def user_login(req: LoginRequest):
    return ok(services.login(req.code, req.nickname, req.grade))


# 7. 个人中心
@router.get("/user/profile")
async def user_profile(user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "请先登录", 401)
    result = services.get_profile(user_id)
    if result is None:
        return fail(4010, "账号不存在", 401)
    return ok(result)


# 8. 知识库上传
@router.post("/knowledge/documents")
async def kb_upload(file: UploadFile = File(...),
                    user_id: Optional[int] = Depends(get_optional_user)):
    filename = file.filename or "未命名.txt"
    if not filename.lower().endswith(ALLOWED_EXT):
        return fail(4001, "暂时只支持 txt / md / pdf / docx 这几种资料")
    try:
        content = await file.read()
    except Exception as exc:
        return fail(4001, "文件读取失败：%s" % exc)
    if len(content) > settings.max_upload_bytes:
        return fail(4000, "文件有点大，请上传 %d MB 以内的资料"
                    % (settings.max_upload_bytes // 1024 // 1024))
    text = _extract_text(filename, content)
    if not text.strip():
        return fail(4001, "这份资料暂时读不懂，先试试 txt 或 md 文本文件吧")
    result = services.add_document(filename, text, user_id, size_bytes=len(content))
    return ok(result)


# 9. 知识库列表
@router.get("/knowledge/documents")
async def kb_list(user_id: Optional[int] = Depends(get_optional_user)):
    return ok({"documents": services.list_documents(user_id)})


# 10. 知识库删除
@router.delete("/knowledge/documents/{doc_id}")
async def kb_delete(doc_id: str):
    services.delete_document(doc_id)
    return ok({"deleted": doc_id})


# 11. 错题本总览
@router.get("/wrong/questions")
async def wrong_list(user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能把错题存下来哦", 401)
    return ok(services.get_wrong_summary(user_id))


# 12. 只练错题
@router.post("/wrong/practice")
async def wrong_practice(req: WrongPracticeRequest,
                         user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能把错题存下来哦", 401)
    result = services.practice_wrong(user_id, req.count, req.grade)
    if result is None:
        return fail(4003, "错题本还是空的，先去闯一关吧", 404)
    return ok(result)


# 13. 清空错题本
@router.delete("/wrong/questions")
async def wrong_clear(user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能把错题存下来哦", 401)
    services.clear_wrong(user_id)
    return ok({"cleared": True})


# 14. 修改单条错题（错题本里的「改」）
@router.put("/wrong/questions")
async def wrong_update(req: WrongItemRequest,
                       user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能修改错题哦", 401)
    if not req.stem:
        return fail(4000, "请说明要改哪一道错题")
    payload = req.model_dump(exclude_none=True)
    payload.pop("stem", None)
    if req.new_stem:
        payload["stem"] = req.new_stem
    result, err = services.update_wrong_item(user_id, req.stem, payload)
    if err:
        return fail(4003 if "不在错题本" in err else 4000, err, 404 if "不在错题本" in err else 400)
    return ok(result)


# 15. 删除单条错题（错题本里的「删」）
# 提供两种调用方式：路径里带题干，或用请求体传（题干是长中文时推荐后者，
# 免得依赖 URL 百分号编码的长度与转义细节）。
@router.delete("/wrong/questions/item")
async def wrong_delete_by_body(req: WrongItemRequest,
                               user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能修改错题哦", 401)
    if not req.stem:
        return fail(4000, "请说明要删哪一道错题")
    if not services.delete_wrong_item(user_id, req.stem):
        return fail(4003, "这道错题不在错题本里", 404)
    return ok({"deleted": req.stem})


@router.delete("/wrong/questions/{stem}")
async def wrong_delete(stem: str, user_id: Optional[int] = Depends(get_optional_user)):
    if user_id is None:
        return fail(4010, "登录后才能修改错题哦", 401)
    if not services.delete_wrong_item(user_id, stem):
        return fail(4003, "这道错题不在错题本里", 404)
    return ok({"deleted": stem})


# ---------------- 文档文本提取 ----------------
def _extract_text(filename: str, content: bytes) -> str:
    """按扩展名解析文档文本；复杂格式降级为纯文本提取。

    txt / md / csv 直接解码；pdf 依赖 pypdf、docx 依赖 docx2txt（可选依赖）。
    缺少可选依赖时对应分支返回空串，上层给出「读不懂」的友好提示，
    而不是抛 500 —— 这是面向小规模部署的可靠性取舍。
    """
    name = filename.lower()
    if name.endswith((".txt", ".md", ".markdown", ".csv")):
        for enc in ("utf-8", "gbk", "utf-16"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        return _extract_pdf(content)
    if name.endswith(".docx"):
        return _extract_docx(content)
    return content.decode("utf-8", errors="ignore")


def _extract_pdf(content: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def _extract_docx(content: bytes) -> str:
    try:
        import io
        import docx2txt
        return docx2txt.process(io.BytesIO(content))
    except Exception:
        return ""
