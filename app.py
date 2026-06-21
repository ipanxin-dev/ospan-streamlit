from __future__ import annotations

import csv
import json
import random
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


LETTERS = ["F", "H", "J", "K", "L", "N", "P", "Q", "R", "S", "T", "Y"]
SET_SIZES = [3, 4, 5, 6, 7]
SETS_PER_SIZE = 3
DEFAULT_MATH_LIMIT_SEC = 6.0
DATA_DIR = Path(__file__).parent / "data"

TRIAL_COLUMNS = [
    "timestamp",
    "participant_name",
    "participant_id",
    "trial_index",
    "block_type",
    "condition",
    "set_id",
    "set_size",
    "item_index",
    "stimulus",
    "response",
    "correct_response",
    "accuracy",
    "rt_ms",
    "timed_out",
    "recall_target",
    "recall_response",
    "recall_correct_positions",
    "set_perfect",
    "math_limit_sec",
    "math_expression",
    "math_answer",
    "math_shown",
]

SUMMARY_COLUMNS = [
    "participant_name",
    "participant_id",
    "started_at",
    "finished_at",
    "ospan_score",
    "total_correct",
    "math_errors",
    "speed_errors",
    "accuracy_errors",
    "math_accuracy_percent",
    "duration_sec",
    "math_limit_sec",
    "trial_count",
]


st.set_page_config(
    page_title="中文 A-OSPAN",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def inject_style() -> None:
    st.markdown(
        """
        <style>
        .block-container { max-width: 880px; padding-top: 2.2rem; }
        h1, h2, h3 { letter-spacing: 0; }
        div.stButton > button {
            min-height: 44px;
            border-radius: 8px;
            font-weight: 650;
        }
        .stimulus-letter {
            font-size: 96px;
            font-weight: 800;
            text-align: center;
            padding: 44px 0 38px;
            line-height: 1;
        }
        .math-problem {
            font-size: 46px;
            font-weight: 750;
            text-align: center;
            padding: 42px 0 24px;
            line-height: 1.22;
        }
        .center-note {
            display: block;
            text-align: center;
            color: #4b5563;
            font-size: 18px;
            line-height: 1.6;
            min-height: 34px;
            padding: 8px 0 10px;
            margin: 0 0 18px;
            overflow: visible;
        }
        .metric-red {
            color: #dc2626;
            font-weight: 800;
            text-align: right;
            font-size: 18px;
        }
        .recall-box {
            font-size: 24px;
            font-weight: 750;
            min-height: 48px;
            padding: 10px 14px;
            border: 1px solid #d1d5db;
            border-radius: 8px;
            background: #f9fafb;
        }
        .small-muted { color: #6b7280; font-size: 14px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session() -> None:
    defaults = {
        "page": "intro",
        "events": [],
        "participant": {},
        "started_at": None,
        "saved_paths": None,
        "sync_status": None,
        "summary": None,
        "math_limit_sec": DEFAULT_MATH_LIMIT_SEC,
        "math_practice_rts": [],
        "math_practice_items": [],
        "math_practice_index": 0,
        "letter_practice_sets": [],
        "letter_practice_index": 0,
        "letter_item_index": 0,
        "integration_sets": [],
        "integration_set_index": 0,
        "integration_item_index": 0,
        "formal_sets": [],
        "formal_set_index": 0,
        "formal_item_index": 0,
        "current_math_item": None,
        "math_start": None,
        "judge_start": None,
        "pending_calc_ms": None,
        "current_letters": [],
        "recall_response": [],
        "letter_start": None,
        "recall_start": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_slug(text: str) -> str:
    text = text.strip() or "participant"
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text)
    return text[:60]


def generate_math_item() -> dict[str, Any]:
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    c = random.randint(1, 9)
    op = random.choice(["+", "-"])
    answer = a * b + c if op == "+" else a * b - c
    if answer < 0:
        op = "+"
        answer = a * b + c
    is_true = random.choice([True, False])
    if is_true:
        shown = answer
    else:
        delta = random.choice([-5, -4, -3, -2, -1, 1, 2, 3, 4, 5])
        shown = answer + delta
    return {
        "expression": f"({a} × {b}) {op} {c}",
        "answer": answer,
        "shown": shown,
        "is_true": is_true,
        "stimulus": f"{a}x{b}{op}{c}={shown}",
    }


def sample_letters(n: int) -> list[str]:
    return random.sample(LETTERS, n)


def build_experiment() -> None:
    st.session_state.events = []
    st.session_state.saved_paths = None
    st.session_state.sync_status = None
    st.session_state.summary = None
    st.session_state.math_practice_rts = []
    st.session_state.math_limit_sec = DEFAULT_MATH_LIMIT_SEC
    st.session_state.math_practice_items = [generate_math_item() for _ in range(8)]
    st.session_state.math_practice_index = 0
    st.session_state.letter_practice_sets = [
        {"set_id": "letter_practice_1", "set_size": 3, "letters": sample_letters(3)}
    ]
    st.session_state.letter_practice_index = 0
    st.session_state.integration_sets = [
        {
            "set_id": f"integration_practice_{i + 1}",
            "set_size": size,
            "letters": sample_letters(size),
            "math": [generate_math_item() for _ in range(size)],
        }
        for i, size in enumerate([2, 3])
    ]
    formal_sets: list[dict[str, Any]] = []
    for size in SET_SIZES:
        for rep in range(SETS_PER_SIZE):
            formal_sets.append(
                {
                    "set_id": f"formal_s{size}_{rep + 1}",
                    "set_size": size,
                    "letters": sample_letters(size),
                    "math": [generate_math_item() for _ in range(size)],
                }
            )
    random.shuffle(formal_sets)
    st.session_state.formal_sets = formal_sets
    st.session_state.formal_set_index = 0
    st.session_state.formal_item_index = 0
    st.session_state.letter_item_index = 0
    st.session_state.integration_set_index = 0
    st.session_state.integration_item_index = 0
    st.session_state.recall_response = []


def append_event(
    *,
    block_type: str,
    condition: str,
    stimulus: str,
    response: Any = "",
    correct_response: Any = "",
    accuracy: bool | None = None,
    rt_ms: int | None = None,
    timed_out: bool = False,
    set_id: str = "",
    set_size: int | None = None,
    item_index: int | None = None,
    recall_target: list[str] | None = None,
    recall_response: list[str] | None = None,
    recall_correct_positions: int | None = None,
    set_perfect: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    participant = st.session_state.participant
    event = {
        "timestamp": now_iso(),
        "participant_name": participant.get("name", ""),
        "participant_id": participant.get("student_id", ""),
        "trial_index": len(st.session_state.events) + 1,
        "block_type": block_type,
        "condition": condition,
        "set_id": set_id,
        "set_size": set_size,
        "item_index": item_index,
        "stimulus": stimulus,
        "response": json.dumps(response, ensure_ascii=False)
        if isinstance(response, (list, dict))
        else response,
        "correct_response": json.dumps(correct_response, ensure_ascii=False)
        if isinstance(correct_response, (list, dict))
        else correct_response,
        "accuracy": accuracy,
        "rt_ms": rt_ms,
        "timed_out": timed_out,
        "recall_target": json.dumps(recall_target or [], ensure_ascii=False),
        "recall_response": json.dumps(recall_response or [], ensure_ascii=False),
        "recall_correct_positions": recall_correct_positions,
        "set_perfect": set_perfect,
        "math_limit_sec": round(st.session_state.math_limit_sec, 3),
    }
    if extra:
        event.update(extra)
    st.session_state.events.append(event)


def elapsed_ms(start: float | None) -> int:
    if start is None:
        return 0
    return int(round((time.perf_counter() - start) * 1000))


def start_letter_set(block_type: str) -> None:
    if block_type == "letter_practice":
        current = st.session_state.letter_practice_sets[st.session_state.letter_practice_index]
        st.session_state.current_letters = current["letters"]
        st.session_state.letter_item_index = 0
        st.session_state.page = "letter_show"
    elif block_type == "integration_practice":
        st.session_state.integration_item_index = 0
        st.session_state.page = "integration_math"
    elif block_type == "formal":
        st.session_state.formal_item_index = 0
        st.session_state.page = "formal_math"
    st.session_state.recall_response = []


def get_active_set(block_type: str) -> dict[str, Any]:
    if block_type == "letter_practice":
        return st.session_state.letter_practice_sets[st.session_state.letter_practice_index]
    if block_type == "integration_practice":
        return st.session_state.integration_sets[st.session_state.integration_set_index]
    return st.session_state.formal_sets[st.session_state.formal_set_index]


def show_progress(block_type: str) -> None:
    if block_type == "formal":
        done = st.session_state.formal_set_index
        total = len(st.session_state.formal_sets)
        st.progress(done / total, text=f"正式实验进度：{done}/{total} 组")
    elif block_type == "integration_practice":
        done = st.session_state.integration_set_index
        total = len(st.session_state.integration_sets)
        st.progress(done / total, text=f"整合练习：{done}/{total} 组")


def start_math(block_type: str) -> None:
    current = get_active_set(block_type)
    idx = (
        st.session_state.integration_item_index
        if block_type == "integration_practice"
        else st.session_state.formal_item_index
    )
    st.session_state.current_math_item = current["math"][idx]
    st.session_state.math_start = time.perf_counter()
    st.session_state.pending_calc_ms = None


def start_practice_math() -> None:
    item = st.session_state.math_practice_items[st.session_state.math_practice_index]
    st.session_state.current_math_item = item
    st.session_state.math_start = time.perf_counter()
    st.session_state.pending_calc_ms = None
    st.session_state.page = "math_practice_problem"


def calculate_math_limit() -> float:
    rts = [rt / 1000 for rt in st.session_state.math_practice_rts if rt > 0]
    if not rts:
        return DEFAULT_MATH_LIMIT_SEC
    if len(rts) == 1:
        return max(2.5, rts[0] + 1.5)
    limit = statistics.mean(rts) + 2.5 * statistics.stdev(rts)
    return max(2.5, min(limit, 20.0))


def math_accuracy_percent() -> float:
    math_events = [
        e
        for e in st.session_state.events
        if e["condition"] == "math" and e["block_type"] == "formal"
    ]
    if not math_events:
        return 100.0
    correct = sum(1 for e in math_events if e["accuracy"] is True)
    return correct / len(math_events) * 100


def render_intro() -> None:
    st.title("中文 A-OSPAN")
    st.subheader("记忆与注意力任务")
    st.write("本任务用于测量您的记忆与注意力。您需要同时进行简单的数学判断，并记忆出现的字母顺序。")
    st.info("请按照要求完成任务，不要猜测正确答案。正式实验中数学正确率应保持在 85% 或以上。")
    name = st.text_input("姓名")
    student_id = st.text_input("学号")
    consent = st.checkbox("我已阅读任务说明，自愿参加，并同意本地记录本次实验数据。")
    if st.button("开始任务", use_container_width=True):
        if not name.strip() or not student_id.strip():
            st.error("请填写姓名和学号。")
            return
        if not consent:
            st.error("请勾选同意后继续。")
            return
        st.session_state.participant = {
            "name": name.strip(),
            "student_id": student_id.strip(),
        }
        st.session_state.started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
        build_experiment()
        st.session_state.page = "letter_practice_intro"
        st.rerun()


def render_letter_practice_intro() -> None:
    st.title("第一部分：字母记忆练习")
    st.write("屏幕会依次呈现字母。请记住它们出现的顺序，随后在 4×3 字母矩阵中按顺序点击回忆。")
    if st.button("开始字母练习", use_container_width=True):
        start_letter_set("letter_practice")
        st.rerun()


def render_letter_show(block_type: str) -> None:
    current = get_active_set(block_type)
    letters = current["letters"]
    idx = st.session_state.letter_item_index
    if st.session_state.letter_start is None:
        st.session_state.letter_start = time.perf_counter()
    st.markdown(f"<div class='center-note'>第 {idx + 1} / {len(letters)} 个字母</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='stimulus-letter'>{letters[idx]}</div>", unsafe_allow_html=True)
    if st.button("记住了，继续", use_container_width=True):
        append_event(
            block_type=block_type,
            condition="letter",
            set_id=current["set_id"],
            set_size=current["set_size"],
            item_index=idx + 1,
            stimulus=letters[idx],
            rt_ms=elapsed_ms(st.session_state.letter_start),
        )
        st.session_state.letter_start = None
        if idx + 1 >= len(letters):
            st.session_state.recall_response = []
            st.session_state.recall_start = time.perf_counter()
            st.session_state.page = f"{block_type}_recall"
        else:
            st.session_state.letter_item_index += 1
        st.rerun()


def render_math_problem(block_type: str) -> None:
    if st.session_state.current_math_item is None:
        if block_type == "math_practice":
            start_practice_math()
        else:
            start_math(block_type)
    item = st.session_state.current_math_item
    if block_type in {"integration_practice", "formal"}:
        show_progress(block_type)
    st.markdown("<div class='center-note'>请尽快计算，算好后点击继续。</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='math-problem'>{item['expression']} = ?</div>", unsafe_allow_html=True)
    if block_type != "math_practice":
        st.caption(f"本阶段数学时间上限：{st.session_state.math_limit_sec:.2f} 秒")
    if st.button("我算好了", use_container_width=True):
        calc_ms = elapsed_ms(st.session_state.math_start)
        if block_type != "math_practice" and calc_ms > st.session_state.math_limit_sec * 1000:
            record_math_response(block_type, response="TIMEOUT", calc_ms=calc_ms, timed_out=True)
            advance_after_math(block_type)
        else:
            st.session_state.pending_calc_ms = calc_ms
            st.session_state.judge_start = time.perf_counter()
            page_map = {
                "math_practice": "math_practice_judge",
                "integration_practice": "integration_judge",
                "formal": "formal_judge",
            }
            st.session_state.page = page_map[block_type]
        st.rerun()


def render_math_judge(block_type: str) -> None:
    item = st.session_state.current_math_item
    st.markdown("<div class='center-note'>判断下面的结果是否正确。</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='math-problem'>{item['expression']} = {item['shown']}</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        true_clicked = st.button("True / 正确", use_container_width=True)
    with col2:
        false_clicked = st.button("False / 错误", use_container_width=True)
    if true_clicked or false_clicked:
        response = true_clicked
        calc_ms = st.session_state.pending_calc_ms or 0
        judge_ms = elapsed_ms(st.session_state.judge_start)
        total_ms = calc_ms + judge_ms
        record_math_response(block_type, response=response, calc_ms=total_ms, timed_out=False)
        if block_type == "math_practice":
            st.session_state.math_practice_rts.append(calc_ms)
            st.session_state.math_practice_index += 1
            if st.session_state.math_practice_index >= len(st.session_state.math_practice_items):
                st.session_state.math_limit_sec = calculate_math_limit()
                st.session_state.page = "math_practice_done"
            else:
                st.session_state.current_math_item = None
                st.session_state.page = "math_practice_problem"
        else:
            advance_after_math(block_type)
        st.rerun()


def record_math_response(block_type: str, response: Any, calc_ms: int, timed_out: bool) -> None:
    item = st.session_state.current_math_item
    if timed_out:
        accuracy = False
    else:
        accuracy = bool(response) == bool(item["is_true"])
    if block_type == "math_practice":
        set_id = "math_practice"
        set_size = None
        item_index = st.session_state.math_practice_index + 1
    else:
        current = get_active_set(block_type)
        set_id = current["set_id"]
        set_size = current["set_size"]
        item_index = (
            st.session_state.integration_item_index + 1
            if block_type == "integration_practice"
            else st.session_state.formal_item_index + 1
        )
    append_event(
        block_type=block_type,
        condition="math",
        set_id=set_id,
        set_size=set_size,
        item_index=item_index,
        stimulus=f"{item['expression']} = {item['shown']}",
        response=response,
        correct_response=item["is_true"],
        accuracy=accuracy,
        rt_ms=calc_ms,
        timed_out=timed_out,
        extra={
            "math_expression": item["expression"],
            "math_answer": item["answer"],
            "math_shown": item["shown"],
        },
    )
    st.session_state.current_math_item = None
    st.session_state.math_start = None
    st.session_state.pending_calc_ms = None
    st.session_state.judge_start = None


def advance_after_math(block_type: str) -> None:
    if block_type == "integration_practice":
        st.session_state.page = "integration_letter"
        st.session_state.letter_start = None
    elif block_type == "formal":
        st.session_state.page = "formal_letter"
        st.session_state.letter_start = None


def render_integration_letter(block_type: str) -> None:
    current = get_active_set(block_type)
    idx = (
        st.session_state.integration_item_index
        if block_type == "integration_practice"
        else st.session_state.formal_item_index
    )
    letter = current["letters"][idx]
    if st.session_state.letter_start is None:
        st.session_state.letter_start = time.perf_counter()
    if block_type == "formal":
        left, right = st.columns([2, 1])
        with right:
            st.markdown(
                f"<div class='metric-red'>数学正确率：{math_accuracy_percent():.0f}%</div>",
                unsafe_allow_html=True,
            )
    st.markdown(f"<div class='center-note'>请记住第 {idx + 1} / {current['set_size']} 个字母。</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='stimulus-letter'>{letter}</div>", unsafe_allow_html=True)
    if st.button("继续", use_container_width=True):
        append_event(
            block_type=block_type,
            condition="letter",
            set_id=current["set_id"],
            set_size=current["set_size"],
            item_index=idx + 1,
            stimulus=letter,
            rt_ms=elapsed_ms(st.session_state.letter_start),
        )
        st.session_state.letter_start = None
        if idx + 1 >= current["set_size"]:
            st.session_state.recall_response = []
            st.session_state.recall_start = time.perf_counter()
            st.session_state.page = f"{block_type}_recall"
        else:
            if block_type == "integration_practice":
                st.session_state.integration_item_index += 1
                st.session_state.page = "integration_math"
            else:
                st.session_state.formal_item_index += 1
                st.session_state.page = "formal_math"
        st.rerun()


def render_math_practice_intro() -> None:
    st.title("第二部分：数学练习")
    st.write("您会看到简单数学题。请尽快计算，点击进入下一屏，然后判断给出的结果 True / False。")
    st.write("练习结束后，系统会用您的平均解题时间 + 2.5 个标准差，作为之后阶段的时间上限。")
    if st.button("开始数学练习", use_container_width=True):
        start_practice_math()
        st.rerun()


def render_math_practice_done() -> None:
    st.title("数学练习完成")
    rts = st.session_state.math_practice_rts
    avg = statistics.mean(rts) / 1000 if rts else DEFAULT_MATH_LIMIT_SEC
    sd = statistics.stdev(rts) / 1000 if len(rts) > 1 else 0.0
    st.success(f"之后阶段的数学时间上限为 {st.session_state.math_limit_sec:.2f} 秒。")
    st.write(f"练习平均 RT：{avg:.2f} 秒；标准差：{sd:.2f} 秒。")
    if st.button("进入双任务整合练习", use_container_width=True):
        st.session_state.page = "integration_intro"
        st.rerun()


def render_integration_intro() -> None:
    st.title("第三部分：双任务整合练习")
    st.write("接下来会在数学计算与字母记忆之间切换。数学题超出个人时间上限会记为超时错误。")
    if st.button("开始整合练习", use_container_width=True):
        start_letter_set("integration_practice")
        st.rerun()


def render_formal_intro() -> None:
    st.title("正式实验")
    st.write("正式实验包含 set size 3-7，每个 set size 3 个 set。请保持数学正确率不低于 85%。")
    st.warning("正式实验开始后请尽量连续完成，中途不要离开页面。")
    if st.button("开始正式实验", use_container_width=True):
        start_letter_set("formal")
        st.rerun()


def render_recall(block_type: str) -> None:
    current = get_active_set(block_type)
    if block_type == "formal":
        cols = st.columns([2, 1])
        with cols[1]:
            st.markdown(
                f"<div class='metric-red'>数学正确率：{math_accuracy_percent():.0f}%</div>",
                unsafe_allow_html=True,
            )
    st.subheader("请按顺序回忆字母")
    st.markdown(
        f"<div class='recall-box'>{' '.join(st.session_state.recall_response) or '&nbsp;'}</div>",
        unsafe_allow_html=True,
    )
    grid = [LETTERS[i : i + 4] for i in range(0, len(LETTERS), 4)]
    for r, row in enumerate(grid):
        cols = st.columns(4)
        for c, letter in enumerate(row):
            with cols[c]:
                if st.button(letter, key=f"{block_type}_recall_{current['set_id']}_{r}_{c}", use_container_width=True):
                    if len(st.session_state.recall_response) < current["set_size"]:
                        st.session_state.recall_response.append(letter)
                    st.rerun()
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("退格", use_container_width=True):
            if st.session_state.recall_response:
                st.session_state.recall_response.pop()
            st.rerun()
    with col2:
        if st.button("清空", use_container_width=True):
            st.session_state.recall_response = []
            st.rerun()
    with col3:
        if st.button("提交回忆", type="primary", use_container_width=True):
            score_recall(block_type)
            advance_after_recall(block_type)
            st.rerun()


def score_recall(block_type: str) -> None:
    current = get_active_set(block_type)
    target = current["letters"]
    response = st.session_state.recall_response[:]
    correct_positions = sum(
        1 for i, letter in enumerate(target) if i < len(response) and response[i] == letter
    )
    set_perfect = correct_positions == len(target) and len(response) == len(target)
    append_event(
        block_type=block_type,
        condition="recall",
        set_id=current["set_id"],
        set_size=current["set_size"],
        stimulus="letter_recall_matrix",
        response=response,
        correct_response=target,
        accuracy=set_perfect,
        rt_ms=elapsed_ms(st.session_state.recall_start),
        recall_target=target,
        recall_response=response,
        recall_correct_positions=correct_positions,
        set_perfect=set_perfect,
    )
    st.session_state.recall_start = None


def advance_after_recall(block_type: str) -> None:
    if block_type == "letter_practice":
        st.session_state.page = "math_practice_intro"
        return
    if block_type == "integration_practice":
        st.session_state.integration_set_index += 1
        if st.session_state.integration_set_index >= len(st.session_state.integration_sets):
            st.session_state.page = "formal_intro"
        else:
            start_letter_set("integration_practice")
        return
    st.session_state.formal_set_index += 1
    if st.session_state.formal_set_index >= len(st.session_state.formal_sets):
        st.session_state.summary = compute_summary()
        st.session_state.saved_paths = save_outputs()
        st.session_state.sync_status = sync_google_sheets()
        st.session_state.page = "finished"
    else:
        start_letter_set("formal")


def ensure_formal_finished() -> bool:
    formal_sets = st.session_state.get("formal_sets", [])
    if not formal_sets:
        return False
    if st.session_state.formal_set_index < len(formal_sets):
        return False

    if st.session_state.summary is None:
        st.session_state.summary = compute_summary()
    if st.session_state.saved_paths is None:
        st.session_state.saved_paths = save_outputs()
    if st.session_state.sync_status is None:
        st.session_state.sync_status = sync_google_sheets()
    st.session_state.page = "finished"
    return True


def ensure_integration_finished() -> bool:
    integration_sets = st.session_state.get("integration_sets", [])
    if not integration_sets:
        return False
    if st.session_state.integration_set_index < len(integration_sets):
        return False

    st.session_state.page = "formal_intro"
    st.session_state.integration_item_index = 0
    st.session_state.recall_response = []
    return True


def compute_summary() -> dict[str, Any]:
    formal_recalls = [
        e
        for e in st.session_state.events
        if e["block_type"] == "formal" and e["condition"] == "recall"
    ]
    formal_math = [
        e
        for e in st.session_state.events
        if e["block_type"] == "formal" and e["condition"] == "math"
    ]
    ospan_score = sum(int(e["set_size"] or 0) for e in formal_recalls if e["set_perfect"] is True)
    total_correct = sum(int(e["recall_correct_positions"] or 0) for e in formal_recalls)
    speed_errors = sum(1 for e in formal_math if e["timed_out"] is True)
    accuracy_errors = sum(
        1 for e in formal_math if e["timed_out"] is not True and e["accuracy"] is False
    )
    math_errors = speed_errors + accuracy_errors
    duration_sec = 0
    if st.session_state.started_at:
        try:
            start_dt = datetime.strptime(st.session_state.started_at, "%Y%m%d_%H%M%S")
            duration_sec = max(0, int((datetime.now() - start_dt).total_seconds()))
        except ValueError:
            duration_sec = 0
    return {
        "participant_name": st.session_state.participant.get("name", ""),
        "participant_id": st.session_state.participant.get("student_id", ""),
        "started_at": st.session_state.started_at,
        "finished_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "ospan_score": ospan_score,
        "total_correct": total_correct,
        "math_errors": math_errors,
        "speed_errors": speed_errors,
        "accuracy_errors": accuracy_errors,
        "math_accuracy_percent": round(math_accuracy_percent(), 2),
        "duration_sec": duration_sec,
        "math_limit_sec": round(st.session_state.math_limit_sec, 3),
        "trial_count": len(st.session_state.events),
    }


def save_outputs() -> dict[str, str]:
    DATA_DIR.mkdir(exist_ok=True)
    participant = st.session_state.participant
    stem = (
        f"{safe_slug(participant.get('student_id', ''))}_"
        f"{safe_slug(participant.get('name', ''))}_"
        f"{st.session_state.started_at}"
    )
    csv_path = DATA_DIR / f"{stem}_trials.csv"
    json_path = DATA_DIR / f"{stem}_trials.json"
    summary_path = DATA_DIR / f"{stem}_summary.json"
    events = st.session_state.events
    extra_fields = sorted(
        {key for event in events for key in event.keys()} - set(TRIAL_COLUMNS)
    )
    fields = TRIAL_COLUMNS + extra_fields
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(events)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(st.session_state.summary, f, ensure_ascii=False, indent=2)
    return {
        "csv": str(csv_path),
        "json": str(json_path),
        "summary": str(summary_path),
    }


def get_sheet_id() -> str | None:
    try:
        sheet_id = st.secrets.get("google_sheet_id")
        if sheet_id:
            return str(sheet_id)
        google_sheets = st.secrets.get("google_sheets", {})
        if isinstance(google_sheets, dict) and google_sheets.get("sheet_id"):
            return str(google_sheets["sheet_id"])
    except Exception:
        return None
    return None


def get_apps_script_webhook_url() -> str | None:
    try:
        webhook_url = st.secrets.get("apps_script_webhook_url")
        if webhook_url:
            return str(webhook_url)
        google_sheets = st.secrets.get("google_sheets", {})
        if isinstance(google_sheets, dict) and google_sheets.get("webhook_url"):
            return str(google_sheets["webhook_url"])
    except Exception:
        return None
    return None


def sync_google_sheets() -> dict[str, Any]:
    webhook_url = get_apps_script_webhook_url()
    if not webhook_url:
        return {
            "enabled": False,
            "success": False,
            "message": "未配置 Apps Script 收数 URL，数据仅保存在本地并可下载。",
        }

    try:
        import requests

        response = requests.post(
            webhook_url,
            json={
                "sheet_id": get_sheet_id(),
                "summary": st.session_state.summary,
                "events": st.session_state.events,
            },
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Apps Script 返回未知错误"))
        return {
            "enabled": True,
            "success": True,
            "message": "数据已同步到 Google Sheets。",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "success": False,
            "message": f"Google Sheets 同步失败：{exc}",
        }


def render_finished() -> None:
    st.title("任务完成")
    summary = st.session_state.summary or compute_summary()
    st.success("感谢您的参与。数据已保存。")
    c1, c2, c3 = st.columns(3)
    c1.metric("OSPAN score", summary["ospan_score"])
    c2.metric("Total correct", summary["total_correct"])
    c3.metric("数学正确率", f"{summary['math_accuracy_percent']:.0f}%")
    c4, c5, c6 = st.columns(3)
    c4.metric("Math errors", summary["math_errors"])
    c5.metric("Speed errors", summary["speed_errors"])
    c6.metric("Accuracy errors", summary["accuracy_errors"])
    st.write(f"总耗时：{summary['duration_sec'] // 60} 分 {summary['duration_sec'] % 60} 秒")
    paths = st.session_state.saved_paths or save_outputs()
    sync_status = st.session_state.sync_status
    if sync_status:
        if sync_status["success"]:
            st.success(sync_status["message"])
        elif sync_status["enabled"]:
            st.error(sync_status["message"])
        else:
            st.info(sync_status["message"])
    df = pd.DataFrame(st.session_state.events)
    st.dataframe(df.tail(20), use_container_width=True)
    with open(paths["csv"], "rb") as f:
        st.download_button("下载 trial-level CSV", f, file_name=Path(paths["csv"]).name, use_container_width=True)
    with open(paths["json"], "rb") as f:
        st.download_button("下载 trial-level JSON", f, file_name=Path(paths["json"]).name, use_container_width=True)
    st.caption(f"本地保存目录：{DATA_DIR}")


def is_smoke_test_requested() -> bool:
    try:
        return st.query_params.get("smoke_test") == "1"
    except Exception:
        params = st.experimental_get_query_params()
        return params.get("smoke_test", [""])[0] == "1"


def run_smoke_test() -> None:
    st.session_state.participant = {
        "name": "系统测试",
        "student_id": "TEST_AUTOMATION",
    }
    st.session_state.started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    build_experiment()
    st.session_state.math_limit_sec = 2.5

    for current_set in st.session_state.formal_sets:
        for idx, item in enumerate(current_set["math"], start=1):
            append_event(
                block_type="formal",
                condition="math",
                set_id=current_set["set_id"],
                set_size=current_set["set_size"],
                item_index=idx,
                stimulus=item["stimulus"],
                response=item["is_true"],
                correct_response=item["is_true"],
                accuracy=True,
                rt_ms=500,
                timed_out=False,
                extra={
                    "math_expression": item["expression"],
                    "math_answer": item["answer"],
                    "math_shown": item["shown"],
                },
            )
            append_event(
                block_type="formal",
                condition="letter",
                set_id=current_set["set_id"],
                set_size=current_set["set_size"],
                item_index=idx,
                stimulus=current_set["letters"][idx - 1],
                rt_ms=300,
            )
        append_event(
            block_type="formal",
            condition="recall",
            set_id=current_set["set_id"],
            set_size=current_set["set_size"],
            stimulus="letter_recall_matrix",
            response=current_set["letters"],
            correct_response=current_set["letters"],
            accuracy=True,
            rt_ms=1000,
            recall_target=current_set["letters"],
            recall_response=current_set["letters"],
            recall_correct_positions=current_set["set_size"],
            set_perfect=True,
        )

    st.session_state.summary = compute_summary()
    st.session_state.saved_paths = save_outputs()
    st.session_state.sync_status = sync_google_sheets()
    st.session_state.page = "finished"


def render_smoke_test() -> None:
    st.title("OSPAN Smoke Test")
    st.write("生成一份完整的系统测试数据，用于验证结果页和 Google Sheets 保存。")
    if st.button("生成测试结果并保存", use_container_width=True):
        run_smoke_test()
        st.rerun()


def main() -> None:
    inject_style()
    init_session()
    if is_smoke_test_requested() and st.session_state.page == "intro":
        render_smoke_test()
        return
    page = st.session_state.page
    if page.startswith("integration") and ensure_integration_finished():
        render_formal_intro()
        return
    if page.startswith("formal") and ensure_formal_finished():
        render_finished()
        return
    if page == "intro":
        render_intro()
    elif page == "letter_practice_intro":
        render_letter_practice_intro()
    elif page == "letter_show":
        render_letter_show("letter_practice")
    elif page == "letter_practice_recall":
        render_recall("letter_practice")
    elif page == "math_practice_intro":
        render_math_practice_intro()
    elif page == "math_practice_problem":
        render_math_problem("math_practice")
    elif page == "math_practice_judge":
        render_math_judge("math_practice")
    elif page == "math_practice_done":
        render_math_practice_done()
    elif page == "integration_intro":
        render_integration_intro()
    elif page == "integration_math":
        render_math_problem("integration_practice")
    elif page == "integration_judge":
        render_math_judge("integration_practice")
    elif page == "integration_letter":
        render_integration_letter("integration_practice")
    elif page == "integration_practice_recall":
        render_recall("integration_practice")
    elif page == "formal_intro":
        render_formal_intro()
    elif page == "formal_math":
        render_math_problem("formal")
    elif page == "formal_judge":
        render_math_judge("formal")
    elif page == "formal_letter":
        render_integration_letter("formal")
    elif page == "formal_recall":
        render_recall("formal")
    elif page == "finished":
        render_finished()
    else:
        st.error("状态异常，请刷新页面重新开始。")


if __name__ == "__main__":
    main()
