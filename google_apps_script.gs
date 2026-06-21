const TRIAL_COLUMNS = [
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
];

const SUMMARY_COLUMNS = [
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
];

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const trialsSheet = getOrCreateSheet_(spreadsheet, "trials", TRIAL_COLUMNS);
    const summarySheet = getOrCreateSheet_(spreadsheet, "summary", SUMMARY_COLUMNS);

    const trials = payload.events || [];
    const summary = payload.summary || {};

    if (trials.length > 0) {
      trialsSheet
        .getRange(trialsSheet.getLastRow() + 1, 1, trials.length, TRIAL_COLUMNS.length)
        .setValues(trials.map((row) => TRIAL_COLUMNS.map((column) => formatValue_(row[column]))));
    }

    summarySheet
      .getRange(summarySheet.getLastRow() + 1, 1, 1, SUMMARY_COLUMNS.length)
      .setValues([SUMMARY_COLUMNS.map((column) => formatValue_(summary[column]))]);

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, trials: trials.length }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(error) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getOrCreateSheet_(spreadsheet, name, columns) {
  let sheet = spreadsheet.getSheetByName(name);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(name);
  }

  const headerRange = sheet.getRange(1, 1, 1, columns.length);
  const existingHeader = headerRange.getValues()[0];
  const isEmpty = existingHeader.every((cell) => cell === "");
  if (isEmpty) {
    headerRange.setValues([columns]);
    sheet.setFrozenRows(1);
  }

  return sheet;
}

function formatValue_(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return value;
}
