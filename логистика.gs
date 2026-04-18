function onEdit(e) {
  var sheet = e.source.getActiveSheet();

  if (sheet.getName() !== "הזמנות 2026") return;

  var col = e.range.getColumn();
  var row = e.range.getRow();

  if (col !== 21 || row === 1) return;

  var newValue = e.range.getValue();
  if (!newValue || newValue === "") return;

  var targetSpreadsheet = SpreadsheetApp.openById("1c_zFZTCCEaE-eB2Mp7WaKBht66zr3Y2uxVhNJU6FRcs");
  var targetSheet = targetSpreadsheet.getSheetByName("הזמנות 2026");
  if (!targetSheet) return;

  var sourceRow = sheet.getRange(row, 1, 1, 30).getValues()[0];
  var lastRow = targetSheet.getLastRow();
  targetSheet.getRange(lastRow + 1, 1, 1, 30).setValues([sourceRow]);
}

function createTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  ScriptApp.newTrigger("onEdit")
    .forSpreadsheet(ss)
    .onEdit()
    .create();
}

function testHardcode() {
  var targetSpreadsheet = SpreadsheetApp.openById("1c_zFZTCCEaE-eB2Mp7WaKBht66zr3Y2uxVhNJU6FRcs");
  var targetSheet = targetSpreadsheet.getSheetByName("הזמנות 2026");
  if (!targetSheet) return;
  targetSheet.getRange("A729").setValue("ТЕСТ");
}