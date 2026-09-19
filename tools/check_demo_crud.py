# -*- coding: utf-8 -*-
"""演示页里的错题本增删改查（CRUD）端到端验证。

流程：答错题把错题造出来 → 进错题本 → 展开 → 改知识点/解析/正确答案 → 保存并核对 →
      删单条并核对数量 → 清理。
用法：先启动后端，再 python tools/check_demo_crud.py
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "demo", "shots")

from playwright.sync_api import sync_playwright      # noqa: E402

problems = []


def check(ok, msg):
    print(("[OK  ] " if ok else "[FAIL] ") + msg)
    if not ok:
        problems.append(msg)


CREATE_WRONG = """
async () => {
  // 直接用页面内的 api 造错题（比驱动整套答题界面稳定，且不影响要验证的 CRUD 本身）
  const api = window.__kepuModules['utils/request'];
  const gen = await api.post('/quiz/generate', { topic: '太阳系', grade: 'primary_high' });
  const answers = gen.questions.map(q => (q.answer + 1) % q.options.length);
  const sub = await api.post('/quiz/submit', { quiz_id: gen.quiz_id, answers: answers });
  return { added: sub.wrong_added, total: sub.wrong_total };
}
"""

OPEN_WRONG_PAGE = """
async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  window.__kepuDebug.router.replace('/pages/wrong/index');
  for (let i = 0; i < 40; i++) { await sleep(300); if (document.querySelector('#mp-view .card')) break; }
  await sleep(800);
  return {
    total: (document.querySelector('#mp-view .total-num') || {}).innerText,
    cards: document.querySelectorAll('#mp-view .card').length
  };
}
"""

RUN_CRUD = """
async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const out = {};
  const head = document.querySelector('#mp-view .item-head');
  out.headFound = !!head;
  if (!head) { out.error = '没有找到错题条目'; return out; }
  head.click();
  await sleep(500);

  const editBtn = document.querySelector('#mp-view .act-btn');
  out.editBtnFound = !!editBtn;
  if (!editBtn) { out.error = '展开后没有出现「改一改」按钮'; out.detail = document.querySelector('#mp-view .detail') ? 'detail 存在但无按钮' : 'detail 未展开'; return out; }
  editBtn.click();
  await sleep(500);

  out.formShown = !!document.querySelector('#mp-view .edit-box');
  // 题干与知识点是 input，解析是 textarea，都要算进来
  const inputs = document.querySelectorAll('#mp-view .edit-input, #mp-view .edit-textarea');
  out.editFieldCount = inputs.length;
  const chipOptions = document.querySelectorAll('#mp-view .chip-opt');
  out.chipCount = chipOptions.length;
  if (!out.formShown) { out.error = '编辑表单未出现'; return out; }

  const inst = window.__kepuDebug.instances['pages/wrong'];
  out.originalKnowledge = inst.data.questions[0].knowledgePoint;

  const kInput = inputs[1];
  kInput.focus();
  kInput.value = '改过的知识点';
  kInput.dispatchEvent(new Event('input', { bubbles: true }));
  await sleep(300);

  if (chipOptions.length) {
    chipOptions[chipOptions.length - 1].click();
    await sleep(300);
  }
  out.pickedAnswer = inst.data.editAnswer;

  const saveBtn = document.querySelector('#mp-view .edit-box .btn-primary');
  out.saveBtnFound = !!saveBtn;
  if (!saveBtn) { out.error = '没有找到保存按钮'; return out; }
  saveBtn.click();
  await sleep(2500);

  const after = window.__kepuDebug.instances['pages/wrong'];
  out.afterKnowledge = after.data.questions[0].knowledgePoint;
  out.stillEditing = after.data.editingIndex;
  return out;
}
"""

DELETE_ITEM = """
async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const inst = window.__kepuDebug.instances['pages/wrong'];
  const before = inst.data.total;
  const head = document.querySelector('#mp-view .item-head');
  if (!head) return { error: 'no item' };
  head.click();
  await sleep(400);
  const btns = document.querySelectorAll('#mp-view .act-btn');
  const delBtn = btns[1];
  delBtn.click();
  await sleep(400);
  const modalShown = document.getElementById('mp-modal').classList.contains('show');
  document.getElementById('mp-modal-ok').click();
  await sleep(2000);
  const after = window.__kepuDebug.instances['pages/wrong'];
  return { modalShown: modalShown, before: before, after: after.data.total };
}
"""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1180, "height": 900})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.goto("file:///" + os.path.join(ROOT, "demo", "index.html").replace("\\", "/"))
        pg.wait_for_timeout(1500)
        # 页面已自动静默登录并拿到 token

        # 清掉历史错题，保证从干净状态开始
        pg.evaluate("""async () => {
            const api = window.__kepuModules['utils/request'];
            try { await api.del('/wrong/questions'); } catch (e) {}
        }""")
        pg.wait_for_timeout(300)

        print("=== 1. 造错题（答错一套） ===")
        made = pg.evaluate(CREATE_WRONG)
        check(made.get("added") == 8, "新增：答错 8 题全部入库（wrong_added=%s）" % made.get("added"))

        print("=== 2. 打开错题本 ===")
        info = pg.evaluate(OPEN_WRONG_PAGE)
        check(str(info.get("total")) not in ("", "0", "None"),
              "查询：错题本已列出错题（总数=%s）" % info.get("total"))

        print("=== 3. 改一道错题 ===")
        try:
            res = pg.evaluate(RUN_CRUD)
        except Exception as exc:
            res = {}
            check(False, "编辑流程脚本异常：%s" % str(exc)[:200])
        if res.get("error"):
            check(False, "编辑流程未走通：%s（%s）" % (res["error"], res.get("detail", "")))
        check(res.get("headFound"), "错题条目可展开")
        check(res.get("formShown"), "点「改一改」后出现内联编辑表单")
        check(res.get("editFieldCount", 0) >= 3,
              "表单含题干/知识点/解析输入框（实际 %s 个）" % res.get("editFieldCount"))
        check(res.get("chipCount", 0) >= 2,
              "选项以胶囊呈现、可点选正确答案（实际 %s 个）" % res.get("chipCount"))
        check(res.get("afterKnowledge") == "改过的知识点",
              "改知识点已生效（%s → %s）" % (res.get("originalKnowledge"), res.get("afterKnowledge")))
        check(res.get("stillEditing") == -1, "保存后自动退出编辑态")
        pg.locator(".phone").screenshot(path=os.path.join(SHOTS, "10_错题本_编辑.png"))

        print("=== 4. 删一条错题 ===")
        RESULT = pg.evaluate(DELETE_ITEM)
        if RESULT.get("error"):
            check(False, "删除流程未走通：%s" % RESULT["error"])
        else:
            check(RESULT.get("modalShown"), "删除前弹出二次确认")
            check(RESULT.get("after") == RESULT.get("before") - 1,
                  "删除后总数 %s → %s" % (RESULT.get("before"), RESULT.get("after")))
        pg.locator(".phone").screenshot(path=os.path.join(SHOTS, "11_错题本_删除后.png"))

        real_errors = [e for e in errs if "favicon" not in e]
        check(not real_errors, "控制台无 JS 报错%s" % ("" if not real_errors else "：" + " | ".join(real_errors[:2])))

        b.close()

    print("\n未通过：%d 项" % len(problems))
    for x in problems:
        print("  - " + x)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
