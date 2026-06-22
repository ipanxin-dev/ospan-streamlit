const CONFIG = {
  sheetId: "1mGkQ_qQWpy4tt9ag-DZ_z0rw4qDe8FL3ACPRasQr38c",
  webhookUrl: "https://script.google.com/macros/s/AKfycbzX8-SBD26liMvlSB0uci0coLEydmJU9VFwpIwpdp8yG0cmy3v0tOVKHnvVmFvbHqeL6Q/exec",
};

const LETTERS = ["F", "H", "J", "K", "L", "N", "P", "Q", "R", "S", "T", "Y"];
const SET_SIZES = [3, 4, 5, 6, 7];
const SETS_PER_SIZE = 3;
const DEFAULT_MATH_LIMIT_SEC = 6.0;
const FORMULA_DURATION_MS = 1200;
const LETTER_DURATION_MS = 1100;
const FEEDBACK_DURATION_MS = 800;

let participant = {};
let startedAt = "";
let startedPerf = 0;
let mathLimitSec = DEFAULT_MATH_LIMIT_SEC;
let mathPracticeRts = [];
let events = [];
let summary = null;
let saveState = "pending";

function nowIso() {
  return new Date().toISOString();
}

function timestampCompact(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    "_",
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sampleWithoutReplacement(items, n) {
  const pool = [...items];
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const index = Math.floor(Math.random() * pool.length);
    out.push(pool.splice(index, 1)[0]);
  }
  return out;
}

function shuffle(items) {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function generateMathItem() {
  const a = randomInt(1, 9);
  const b = randomInt(1, 9);
  const c = randomInt(1, 9);
  let op = Math.random() < 0.5 ? "+" : "-";
  let answer = op === "+" ? a * b + c : a * b - c;
  if (answer < 0) {
    op = "+";
    answer = a * b + c;
  }
  const isTrue = Math.random() < 0.5;
  let shown = answer;
  if (!isTrue) {
    const deltas = [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5];
    shown = answer + deltas[randomInt(0, deltas.length - 1)];
  }
  return {
    expression: `(${a} × ${b}) ${op} ${c}`,
    answer,
    shown,
    isTrue,
    stimulus: `${a}x${b}${op}${c}=${shown}`,
  };
}

function buildSets() {
  const letterPracticeSizes = [2, 2, 3, 3, 3];
  const letterPracticeSets = letterPracticeSizes.map((size, index) => ({
    set_id: `letter_practice_${index + 1}`,
    set_size: size,
    letters: sampleWithoutReplacement(LETTERS, size),
  }));

  const integrationSets = [2, 3].map((size, index) => ({
    set_id: `integration_practice_${index + 1}`,
    set_size: size,
    letters: sampleWithoutReplacement(LETTERS, size),
    math: Array.from({ length: size }, generateMathItem),
  }));

  const formalSets = [];
  SET_SIZES.forEach((size) => {
    for (let rep = 1; rep <= SETS_PER_SIZE; rep += 1) {
      formalSets.push({
        set_id: `formal_s${size}_${rep}`,
        set_size: size,
        letters: sampleWithoutReplacement(LETTERS, size),
        math: Array.from({ length: size }, generateMathItem),
      });
    }
  });

  return {
    letterPracticeSets,
    integrationSets,
    formalSets: shuffle(formalSets),
  };
}

function normalizeResponse(value) {
  if (Array.isArray(value) || (value && typeof value === "object")) {
    return JSON.stringify(value);
  }
  if (value === null || value === undefined) {
    return "";
  }
  return value;
}

function appendEvent(row) {
  events.push({
    timestamp: nowIso(),
    participant_name: participant.name || "",
    participant_id: participant.studentId || "",
    trial_index: events.length + 1,
    block_type: row.block_type || "",
    condition: row.condition || "",
    set_id: row.set_id || "",
    set_size: row.set_size ?? "",
    item_index: row.item_index ?? "",
    stimulus: row.stimulus || "",
    response: normalizeResponse(row.response),
    correct_response: normalizeResponse(row.correct_response),
    accuracy: row.accuracy ?? "",
    rt_ms: row.rt_ms ?? "",
    timed_out: row.timed_out ?? false,
    recall_target: normalizeResponse(row.recall_target || []),
    recall_response: normalizeResponse(row.recall_response || []),
    recall_correct_positions: row.recall_correct_positions ?? "",
    set_perfect: row.set_perfect ?? "",
    math_limit_sec: Number(mathLimitSec.toFixed(3)),
    math_expression: row.math_expression || "",
    math_answer: row.math_answer ?? "",
    math_shown: row.math_shown ?? "",
  });
}

function scoreMath(item, responseKey, timedOut) {
  if (timedOut) {
    return false;
  }
  const response = responseKey === "j";
  return response === item.isTrue;
}

function calculateMathLimit() {
  const rts = mathPracticeRts.filter((rt) => rt > 0).map((rt) => rt / 1000);
  if (rts.length === 0) {
    return DEFAULT_MATH_LIMIT_SEC;
  }
  if (rts.length === 1) {
    return Math.max(2.5, rts[0] + 1.5);
  }
  const mean = rts.reduce((sum, value) => sum + value, 0) / rts.length;
  const variance = rts.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (rts.length - 1);
  const limit = mean + 2.5 * Math.sqrt(variance);
  return Math.max(2.5, Math.min(limit, 20));
}

function mathAccuracyPercent() {
  const formalMath = events.filter((event) => event.block_type === "formal" && event.condition === "math");
  if (formalMath.length === 0) {
    return 100;
  }
  const correct = formalMath.filter((event) => event.accuracy === true).length;
  return (correct / formalMath.length) * 100;
}

function computeSummary() {
  const formalRecalls = events.filter((event) => event.block_type === "formal" && event.condition === "recall");
  const formalMath = events.filter((event) => event.block_type === "formal" && event.condition === "math");
  const ospanScore = formalRecalls
    .filter((event) => event.set_perfect === true)
    .reduce((sum, event) => sum + Number(event.set_size || 0), 0);
  const totalCorrect = formalRecalls.reduce((sum, event) => sum + Number(event.recall_correct_positions || 0), 0);
  const speedErrors = formalMath.filter((event) => event.timed_out === true).length;
  const accuracyErrors = formalMath.filter((event) => event.timed_out !== true && event.accuracy === false).length;
  const finishedAt = timestampCompact();
  return {
    participant_name: participant.name || "",
    participant_id: participant.studentId || "",
    started_at: startedAt,
    finished_at: finishedAt,
    ospan_score: ospanScore,
    total_correct: totalCorrect,
    math_errors: speedErrors + accuracyErrors,
    speed_errors: speedErrors,
    accuracy_errors: accuracyErrors,
    math_accuracy_percent: Number(mathAccuracyPercent().toFixed(2)),
    duration_sec: Math.max(0, Math.round((performance.now() - startedPerf) / 1000)),
    math_limit_sec: Number(mathLimitSec.toFixed(3)),
    trial_count: events.length,
  };
}

function getPayload() {
  return {
    sheet_id: CONFIG.sheetId,
    summary,
    events,
  };
}

async function submitData() {
  summary = computeSummary();
  const payload = getPayload();
  try {
    await fetch(CONFIG.webhookUrl, {
      method: "POST",
      mode: "no-cors",
      headers: {
        "Content-Type": "text/plain;charset=utf-8",
      },
      body: JSON.stringify(payload),
    });
    saveState = "sent";
  } catch (error) {
    saveState = `failed: ${error.message}`;
  }
}

function dataDownloadUrl() {
  const payload = JSON.stringify(getPayload(), null, 2);
  const blob = new Blob([payload], { type: "application/json;charset=utf-8" });
  return URL.createObjectURL(blob);
}

function instruction(title, body, button = "继续") {
  return {
    type: jsPsychHtmlButtonResponse,
    stimulus: `<div class="screen"><h2>${title}</h2>${body}</div>`,
    choices: [button],
    record_data: false,
  };
}

function feedbackTrial(isCorrect, detail = "", auto = false) {
  const stimulus = () => {
    const detailText = typeof detail === "function" ? detail() : detail;
    return `
      <div class="screen center">
        <div class="${isCorrect() ? "feedback-good" : "feedback-bad"}">${isCorrect() ? "回答正确" : "回答错误"}</div>
        ${detailText ? `<p>${detailText}</p>` : ""}
        ${auto ? "" : "<p class='muted'>点击继续。</p>"}
      </div>
    `;
  };
  if (!auto) {
    return {
      type: jsPsychHtmlButtonResponse,
      stimulus,
      choices: ["继续"],
      record_data: false,
    };
  }
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus,
    choices: "NO_KEYS",
    trial_duration: FEEDBACK_DURATION_MS,
    record_data: false,
  };
}

function formulaTrial(item, blockType, set, itemIndex) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="note">请尽快计算。</div>
      <div class="math-problem">${escapeHtml(item.expression)} =</div>
    `,
    choices: "NO_KEYS",
    trial_duration: FORMULA_DURATION_MS,
    data: {
      block_type: blockType,
      set_id: set ? set.set_id : "math_practice",
      item_index: itemIndex,
    },
    record_data: false,
  };
}

function mathJudgeTrial(item, blockType, set, itemIndex, options = {}) {
  let lastCorrect = false;
  const hasTimeout = options.timeout === true;
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="note">判断刚才算式的结果是否正确。</div>
      <div class="math-problem">${escapeHtml(item.shown)}</div>
      <div class="key-hint">
        <div class="key">F = False / 错误</div>
        <div class="key">J = True / 正确</div>
      </div>
    `,
    choices: ["f", "j"],
    trial_duration: hasTimeout ? () => Math.round(mathLimitSec * 1000) : null,
    response_ends_trial: true,
    on_finish: (data) => {
      const timedOut = data.response === null;
      const rt = timedOut ? Math.round(mathLimitSec * 1000) : Math.round(FORMULA_DURATION_MS + data.rt);
      lastCorrect = scoreMath(item, data.response, timedOut);
      if (blockType === "math_practice" && !timedOut) {
        mathPracticeRts.push(rt);
      }
      appendEvent({
        block_type: blockType,
        condition: "math",
        set_id: set ? set.set_id : "math_practice",
        set_size: set ? set.set_size : "",
        item_index: itemIndex,
        stimulus: `${item.expression} = ${item.shown}`,
        response: timedOut ? "TIMEOUT" : data.response === "j",
        correct_response: item.isTrue,
        accuracy: lastCorrect,
        rt_ms: rt,
        timed_out: timedOut,
        math_expression: item.expression,
        math_answer: item.answer,
        math_shown: item.shown,
      });
    },
    on_load: () => {
      mathJudgeTrial.lastCorrect = () => lastCorrect;
    },
  };
}

function letterTrial(letter, blockType, set, itemIndex) {
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="note">请记住第 ${itemIndex} / ${set.set_size} 个字母。</div>
      <div class="stimulus-letter">${letter}</div>
    `,
    choices: "NO_KEYS",
    trial_duration: LETTER_DURATION_MS,
    on_finish: () => {
      appendEvent({
        block_type: blockType,
        condition: "letter",
        set_id: set.set_id,
        set_size: set.set_size,
        item_index: itemIndex,
        stimulus: letter,
        rt_ms: LETTER_DURATION_MS,
      });
    },
  };
}

function recallTrial(blockType, set, practiceFeedback = false) {
  let recallResult = null;
  return {
    type: jsPsychHtmlKeyboardResponse,
    stimulus: `
      <div class="recall-shell">
        <h2 class="center">请按顺序回忆字母</h2>
        <div id="recall-box" class="recall-box">&nbsp;</div>
        <div class="letter-grid">
          ${LETTERS.map((letter) => `<button type="button" class="recall-letter" data-letter="${letter}">${letter}</button>`).join("")}
        </div>
        <div class="recall-actions">
          <button type="button" id="recall-back">退格</button>
          <button type="button" id="recall-clear">清空</button>
          <button type="button" id="recall-submit" class="primary">提交回忆</button>
        </div>
      </div>
    `,
    choices: "NO_KEYS",
    response_ends_trial: false,
    on_load: () => {
      const started = performance.now();
      const response = [];
      const box = document.querySelector("#recall-box");
      const render = () => {
        box.innerHTML = response.length ? response.join(" ") : "&nbsp;";
      };
      document.querySelectorAll(".recall-letter").forEach((button) => {
        button.addEventListener("click", () => {
          if (response.length < set.set_size) {
            response.push(button.dataset.letter);
            render();
          }
        });
      });
      document.querySelector("#recall-back").addEventListener("click", () => {
        response.pop();
        render();
      });
      document.querySelector("#recall-clear").addEventListener("click", () => {
        response.length = 0;
        render();
      });
      document.querySelector("#recall-submit").addEventListener("click", () => {
        const correctPositions = set.letters.reduce(
          (sum, letter, index) => sum + (response[index] === letter ? 1 : 0),
          0
        );
        const setPerfect = correctPositions === set.letters.length && response.length === set.letters.length;
        const rt = Math.round(performance.now() - started);
        appendEvent({
          block_type: blockType,
          condition: "recall",
          set_id: set.set_id,
          set_size: set.set_size,
          stimulus: "letter_recall_matrix",
          response: [...response],
          correct_response: set.letters,
          accuracy: setPerfect,
          rt_ms: rt,
          recall_target: set.letters,
          recall_response: [...response],
          recall_correct_positions: correctPositions,
          set_perfect: setPerfect,
        });
        recallResult = { correctPositions, setPerfect };
        jsPsych.finishTrial({ recall_result: recallResult });
      });
    },
    on_finish: () => {
      if (practiceFeedback && recallResult) {
        recallTrial.lastCorrect = () => recallResult.setPerfect;
        recallTrial.lastDetail = () => `正确位置：${recallResult.correctPositions} / ${set.set_size}`;
      }
    },
  };
}

function mathSequence(item, blockType, set, itemIndex, options = {}) {
  const judge = mathJudgeTrial(item, blockType, set, itemIndex, options);
  const sequence = [formulaTrial(item, blockType, set, itemIndex), judge];
  if (options.feedback) {
    sequence.push(feedbackTrial(() => mathJudgeTrial.lastCorrect(), "", options.autoFeedback === true));
  }
  return sequence;
}

function setSequence(blockType, set, options = {}) {
  const sequence = [];
  set.letters.forEach((letter, index) => {
    const itemIndex = index + 1;
    sequence.push(...mathSequence(set.math[index], blockType, set, itemIndex, options));
    sequence.push(letterTrial(letter, blockType, set, itemIndex));
  });
  sequence.push(recallTrial(blockType, set, options.recallFeedback === true));
  if (options.recallFeedback) {
    sequence.push(
      feedbackTrial(
        () => recallTrial.lastCorrect(),
        () => (recallTrial.lastDetail ? recallTrial.lastDetail() : ""),
        false
      )
    );
  }
  return sequence;
}

function createTimeline() {
  const sets = buildSets();
  const timeline = [];

  timeline.push({
    type: jsPsychSurveyHtmlForm,
    preamble: `
      <div class="screen">
        <h1>记忆与注意力任务</h1>
        <p>本任务用于测量您的记忆与注意力。您需要同时进行简单的数学判断，并记忆出现的字母顺序。</p>
        <div class="notice">
          <p>请在安静环境中完成，双手放在键盘附近，快速且准确地反应。</p>
          <p>练习阶段将不进入正式分析。</p>
          <p>数据将严格保密，仅用于研究分析，您可以随时关闭页面退出。</p>
        </div>
      </div>
    `,
    html: `
      <div class="form-row">
        <label for="name">姓名</label>
        <input id="name" name="name" required />
      </div>
      <div class="form-row">
        <label for="student_id">学号</label>
        <input id="student_id" name="student_id" required />
      </div>
      <label class="consent">
        <input type="checkbox" name="consent" value="yes" required />
        <span>我已阅读任务说明，自愿参加，并同意记录本次实验数据。</span>
      </label>
    `,
    button_label: "开始任务",
    on_finish: (data) => {
      participant = {
        name: data.response.name.trim(),
        studentId: data.response.student_id.trim(),
      };
      startedAt = timestampCompact();
      startedPerf = performance.now();
      jsPsych.data.addProperties({
        participant_name: participant.name,
        participant_id: participant.studentId,
        started_at: startedAt,
      });
    },
  });

  timeline.push(
    instruction(
      "准备开始",
      "<p>请把浏览器窗口保持在前台，关闭不必要的通知。正式任务中请尽量不要切换页面。</p><p>数学判断请使用键盘作答：F 表示错误，J 表示正确。</p>"
    )
  );

  timeline.push(
    instruction(
      "第一部分：字母记忆练习",
      "<p>屏幕会依次呈现字母。请记住它们出现的顺序，随后在 4×3 字母矩阵中按顺序点击回忆。</p><p>本阶段包含 5 组练习：前 2 组每组 2 个字母，后 3 组每组 3 个字母。</p>"
    )
  );
  sets.letterPracticeSets.forEach((set) => {
    set.letters.forEach((letter, index) => {
      timeline.push(letterTrial(letter, "letter_practice", set, index + 1));
    });
    timeline.push(recallTrial("letter_practice", set, true));
    timeline.push(
      feedbackTrial(
        () => recallTrial.lastCorrect(),
        () => (recallTrial.lastDetail ? recallTrial.lastDetail() : ""),
        false
      )
    );
  });

  timeline.push(
    instruction(
      "第二部分：数学练习",
      "<p>您会看到简单数学题。请快速计算，并判断随后出现的结果是否正确。</p><p>请用键盘作答：F 表示错误，J 表示正确。</p>"
    )
  );
  Array.from({ length: 8 }, generateMathItem).forEach((item, index) => {
    timeline.push(...mathSequence(item, "math_practice", null, index + 1, { feedback: true }));
  });
  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: "<div class='screen center'><h2>数学练习完成</h2><p>练习已完成。按空格键进入双任务整合练习。</p></div>",
    choices: [" "],
    on_start: () => {
      mathLimitSec = calculateMathLimit();
    },
    record_data: false,
  });

  timeline.push(
    instruction(
      "第三部分：双任务整合练习",
      "<p>接下来会在数学计算与字母记忆之间切换。请快速且准确地完成判断，并记住出现的字母。</p><p>练习阶段必须完成反馈后再继续。</p>"
    )
  );
  sets.integrationSets.forEach((set) => {
    timeline.push(...setSequence("integration_practice", set, {
      feedback: true,
      autoFeedback: true,
      recallFeedback: true,
      timeout: true,
    }));
  });

  timeline.push(
    instruction(
      "正式实验",
      "<p>正式实验包含 set size 3-7，每个 set size 3 个 set。请继续快速且准确地完成判断，并记住出现的字母。</p><p>正式实验开始后请尽量连续完成，中途不要离开页面。</p>"
    )
  );
  sets.formalSets.forEach((set) => {
    timeline.push(...setSequence("formal", set, { timeout: true }));
  });

  timeline.push({
    type: jsPsychCallFunction,
    async: true,
    func: async (done) => {
      await submitData();
      done();
    },
  });

  timeline.push({
    type: jsPsychHtmlKeyboardResponse,
    stimulus: () => {
      const url = dataDownloadUrl();
      const stateText = saveState === "sent" ? "数据提交请求已发送。" : "自动提交可能失败，请下载备用数据。";
      return `
        <div class="screen center">
          <h1>任务完成</h1>
          <p>${stateText}</p>
          <p>OSPAN score：${summary.ospan_score}</p>
          <p>Total correct：${summary.total_correct}</p>
          <p>Math errors：${summary.math_errors}</p>
          <p><a class="download-link" href="${url}" download="ospan_${escapeHtml(participant.studentId || "participant")}_${startedAt}.json">下载备用数据</a></p>
          <p class="muted">您可以关闭页面。</p>
        </div>
      `;
    },
    choices: "NO_KEYS",
  });

  return timeline;
}

const jsPsych = initJsPsych({
  show_progress_bar: true,
  auto_update_progress_bar: true,
});

jsPsych.run(createTimeline());
