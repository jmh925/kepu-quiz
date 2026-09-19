# -*- coding: utf-8 -*-
"""Pydantic 请求 / 响应模型。

统一响应体为 {code, message, data}：code 为 0 表示成功，非 0 为业务错误码
（见论文表 4-11）。Pydantic v2 负责入参类型校验，校验失败由全局异常处理器
统一转换成 4000，避免直接把框架堆栈暴露给客户端。
"""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


# ---------------- 学生端 ----------------
class QuizGenerateRequest(BaseModel):
    topic: str = Field(..., description="学习主题（一句话）")
    count: Optional[int] = Field(None, description="题目数量，按学段自动收敛")
    doc_id: Optional[str] = Field(None, description="知识库文档 ID（检索增强出题）")
    grade: Optional[str] = Field(None, description="学段：primary_low / primary_high / junior")


class Question(BaseModel):
    id: int
    type: str = "single"
    stem: str
    options: List[str] = []
    answer: int
    analysis: str = ""
    knowledge_point: str = ""


class AnswerSubmitRequest(BaseModel):
    quiz_id: str
    answers: List[int] = Field(default_factory=list, description="按题序的选项下标，未作答记 -1")
    duration_ms: int = Field(0, description="本次闯关耗时（毫秒），用于统计")


class ReportGenerateRequest(BaseModel):
    quiz_id: str


class LoginRequest(BaseModel):
    """登录：网页版用「账号 + 口令」，小程序端用微信 code。两者都允许。"""
    username: Optional[str] = Field(None, description="登录名（网页版）")
    password: Optional[str] = Field(None, description="口令（网页版）")
    code: Optional[str] = Field(None, description="微信登录 code（小程序端，未接入时为本地账号）")
    nickname: Optional[str] = Field("小科学家", description="昵称（仅注册/首次登录用）")
    grade: Optional[str] = Field(None, description="常用学段")


class RegisterRequest(BaseModel):
    username: str = Field(..., description="登录名：3~20 位字母、数字或下划线")
    password: str = Field(..., description="口令：6~32 位")
    nickname: Optional[str] = Field(None, description="昵称，留空则用登录名")
    grade: Optional[str] = Field(None, description="学段")


class MergeGuestRequest(BaseModel):
    guest_token: Optional[str] = Field(None, description="游客期间的 Token，用于把那段数据并过来")


class WrongPracticeRequest(BaseModel):
    count: int = Field(8, description="只练错题的题目数量")
    grade: Optional[str] = Field(None, description="学段")


class WrongItemRequest(BaseModel):
    """修改错题本里的单条错题（只提交要改的字段）。"""
    stem: Optional[str] = Field(None, description="题干（同时作为定位依据）")
    new_stem: Optional[str] = Field(None, description="改后的题干")
    options: Optional[List[str]] = Field(None, description="选项列表")
    answer: Optional[int] = Field(None, description="正确答案下标（0 起）")
    analysis: Optional[str] = Field(None, description="解析")
    knowledge_point: Optional[str] = Field(None, description="知识点")
    wrong_count: Optional[int] = Field(None, description="累计答错次数")
    user_answer: Optional[int] = Field(None, description="最近一次所选下标")


# ---------------- 管理端 ----------------
class AdminLoginRequest(BaseModel):
    username: str
    password: str


class QuestionPoolRequest(BaseModel):
    theme: Optional[str] = Field("通用", description="主题分类：天文 / 地理 / 生物 …")
    grade: Optional[str] = Field("primary_high", description="适用学段")
    stem: Optional[str] = Field(None, description="题干")
    options: Optional[List[str]] = Field(None, description="选项列表")
    answer: Optional[int] = Field(None, description="正确选项下标（0 起）")
    analysis: Optional[str] = Field(None, description="解析")
    knowledge_point: Optional[str] = Field(None, description="知识点")
    difficulty: Optional[int] = Field(2, description="难度 1 易 / 2 中 / 3 难")
    enabled: Optional[int] = Field(1, description="是否启用")
