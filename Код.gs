/*********** НАСТРОЙКИ ***********/
const SHEET_MAIN     = 'הזמנות 2026';
const SHEET_ARCHIVE  = 'ARCHIVE 2026';
const ANCHOR_ARCHIVE = 'SYNC_START_ARCHIVE';

const DATA_START_ROW = 6;

// Колонки
const COL_BG = colLetterToNumber_('BG'); // отметка "заархивировано" (TRUE / "TRUE")
const COL_BF = colLetterToNumber_('BF'); // ID (не обязателен для архивации, но оставляем)

// Новое условие для архивирования
const COL_BD = colLetterToNumber_('BD'); // статус "Подано 100%"
const VALUE_BD = 'Подано 100%';

// Связанные таблицы
const LINKED_TARGETS = [
  { id: '1-DX9-Mnat4VaZUOvpx2Z54RXRp5D6BjXf0--3DHgBPo', sheet: 'הזמנות 2026', name: 'Миша проектировщик' },
  { id: '130iEDDSPC80a0fi0waADYm1mJol0Vevgx3bg5xnUo6M', sheet: 'הזמנות 2026', name: 'Кирил проектировщик + Davidov&CO' },
  { id: '1g6Zir6osYOsFc4XSrA-JEkiOolibw7GhnoX_TOjuqeQ', sheet: 'הזמנות 2026', name: 'Анатолий проектировщик + Davidov&CO' },
  { id: '1HRpOKMBJ9gutUpXAlDlckc2XJbhzseHRtxEybdn3jGM', sheet: 'הזמנות 2026', name: 'Ринат + Davidov&CO' },
  { id: '1Yw5L-Zmq6NSK6a_gCF4UjzvkjNvGEceWh6dw1MFXl18', sheet: 'הזמנות 2026', name: 'Abdalla & Davidov 2026' },
  { id: '1URiyjVhF7rgxwzSZr-enAap7Oc3QPn91BSh3J9LERfI', sheet: 'הזמנות 2026', name: 'Suleyman & Davidov' },
  { id: '164by2q6q0nK49sX_g51Xz2YH1km-AeRF6PvATqR1GCQ', sheet: 'הזמנות 2026', name: 'Hamada & Davidov 2025' },
  { id: '1QWc7ADfKyGv9_YpaaY__6dW5EfyR2oHpCIRYhPFXptg', sheet: 'הזמנות 2026', name: 'Subhi & Davidov 2025' },
  { id: '1kVbk6fGiKCkiv7R87D4CXP5IGXE0f3b1us66Ja4-d2A', sheet: 'הזמנות 2026', name: 'Mahdi & Davidov 2026' },
  { id: '1jznx6zcIFC6Z7huxzU68eFY3-X6TLn1xD-qrPgc3xRs', sheet: 'הזמנות 2026', name: 'Sair & Davidov CO 2026' },
  { id: '1PRUcNkDa_OLybl_3_tYY69eCDYweoZ8ovvruswkaQ54', sheet: 'הזמנות 2026', name: 'Apokol & Davidov' },
];


/*********** МЕНЮ ***********/
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Управление')
    .addItem('Архивировать 100%', 'archive100_copy_to_archive_and_mark_BG_true')
    .addToUi();
}


/*********** LOCK WRAPPER ***********/
function withDocLock_(fn, label) {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(20000)) {
    SpreadsheetApp.getActive().toast(`⏳ Уже идёт операция. Повтори через 10–20 сек. (${label})`, label, 6);
    return;
  }
  try {
    fn();
  } finally {
    lock.releaseLock();
  }
}

/*********** AUTO UUID IN BF WHEN STATUS IN B IS SET ***********/
function onEdit(e) {
  try {
    if (!e || !e.range) return;

    const sh = e.range.getSheet();
    if (sh.getName() !== SHEET_MAIN) return;

    const editRow = e.range.getRow();
    const editCol = e.range.getColumn();
    const numRows = e.range.getNumRows();
    const numCols = e.range.getNumColumns();

    // диапазон должен пересекать колонку B
    const B_COL = 2;
    const editColEnd = editCol + numCols - 1;
    if (editCol > B_COL || editColEnd < B_COL) return;

    // рабочая часть диапазона по строкам
    const startRow = Math.max(editRow, DATA_START_ROW);
    const endRow = editRow + numRows - 1;
    if (endRow < DATA_START_ROW) return;

    const rowsCount = endRow - startRow + 1;

    // читаем сразу колонку B и BF на все затронутые строки
    const bVals  = sh.getRange(startRow, B_COL, rowsCount, 1).getDisplayValues();
    const bfVals = sh.getRange(startRow, COL_BF, rowsCount, 1).getDisplayValues();

    const out = [];
    let hasChanges = false;

    for (let i = 0; i < rowsCount; i++) {
      const bVal = String(bVals[i][0] || '').trim();
      const bfVal = String(bfVals[i][0] || '').trim();

      if (bVal !== '' && bfVal === '') {
        out.push([Utilities.getUuid()]);
        hasChanges = true;
      } else {
        out.push([bfVal]);
      }
    }

    if (hasChanges) {
      sh.getRange(startRow, COL_BF, rowsCount, 1).setValues(out);
    }

  } catch (err) {
    // молча, чтобы не мешать работе
  }
}

/**
 * ЕДИНСТВЕННАЯ КНОПКА:
 * BD="Подано 100%" и BG != TRUE -> копируем в ARCHIVE значениями -> BG=TRUE в главной
 */
function archive100_copy_to_archive_and_mark_BG_true() {
  withDocLock_(() => {
    const ss = SpreadsheetApp.getActive();
    const shMain = ss.getSheetByName(SHEET_MAIN);
    const shArchive = ss.getSheetByName(SHEET_ARCHIVE);

    if (!shMain) throw new Error(`Не найден лист: ${SHEET_MAIN}`);
    if (!shArchive) throw new Error(`Не найден лист: ${SHEET_ARCHIVE}`);

    // гарантируем, что колонка BG физически существует
    ensureColumns_(shMain, COL_BG);

    // 1) Собираем строки для архивации (BD="Подано 100%" и BG не TRUE)
    const rows = collectRowsForArchive_(shMain);
    if (rows.length === 0) {
      ss.toast(`ℹ️ Нет строк для архива (BD=${VALUE_BD}) или они уже отмечены BG=TRUE`, 'ARCHIVE 100%', 6);
      return;
    }

    // 2) Копируем строки в ARCHIVE значениями
    const moved = appendRowsToArchiveAsValues_(ss, shMain, shArchive, rows);
    if (moved === 0) {
      ss.toast(`⚠️ Ничего не скопировалось в архив`, 'ARCHIVE 100%', 8);
      return;
    }

    // 3) Ставим BG=TRUE в главной по тем же строкам
    setBGTrueOnRows_(shMain, rows);

    // 4) Принудительно обновляем фильтры в главной и связанных таблицах
    refreshAllBGFilters_(ss, shMain);

    ss.toast(`✅ В архив: ${moved}\n✅ BG=TRUE: ${rows.length}`, 'ARCHIVE 100%', 10);

  }, 'ARCHIVE 100%');
}


/*********** HELPERS ***********/

/**
 * Находим строки:
 * - BD (display) == "Подано 100%"
 * - BG НЕ true-like
 */
function collectRowsForArchive_(sheet) {
  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) return [];

  const numRows = lastRow - DATA_START_ROW + 1;

  const bdDisp = sheet.getRange(DATA_START_ROW, COL_BD, numRows, 1).getDisplayValues();
  const bgDisp = sheet.getRange(DATA_START_ROW, COL_BG, numRows, 1).getDisplayValues();

  const rows = [];
  for (let i = 0; i < numRows; i++) {
    const bgTxt = normalizeText_(bgDisp[i][0]);
    if (isTrueLike_(bgTxt)) continue;

    const bdTxt = normalizeText_(bdDisp[i][0]);
    if (bdTxt !== VALUE_BD) continue;

    rows.push(DATA_START_ROW + i);
  }
  return rows;
}

/**
 * Копируем выбранные строки в архив (значениями), пачками по блокам.
 */
function appendRowsToArchiveAsValues_(ss, sourceSheet, archiveSheet, rows) {
  if (!rows || rows.length === 0) return 0;

  const lastCol = sourceSheet.getLastColumn();
  rows = [...new Set(rows)].sort((a, b) => a - b);

  const dataToWrite = [];
  const blocks = buildBlocks_(rows);

  blocks.forEach(([start, end]) => {
    const h = end - start + 1;
    const vals = sourceSheet.getRange(start, 1, h, lastCol).getValues();
    vals.forEach(r => dataToWrite.push(r));
  });

  if (dataToWrite.length === 0) return 0;

  // расширяем архив по ширине если нужно
  const archiveLastCol = archiveSheet.getLastColumn();
  if (archiveLastCol < lastCol) {
    archiveSheet.insertColumnsAfter(archiveLastCol, lastCol - archiveLastCol);
  }

  // куда писать: ниже якоря или в конец
  const anchorOk = !!ss.getRangeByName(ANCHOR_ARCHIVE);
  const startRow = anchorOk
    ? findAppendRowBelowNamedRange_(ss, archiveSheet, ANCHOR_ARCHIVE, colLetterToNumber_('B'))
    : (Math.max(archiveSheet.getLastRow(), 1) + 1);

  archiveSheet.getRange(startRow, 1, dataToWrite.length, lastCol).setValues(dataToWrite);
  SpreadsheetApp.flush();

  return dataToWrite.length;
}

/**
 * Ставит BG=TRUE (именно boolean true) для списка строк.
 */
function setBGTrueOnRows_(sheet, rows) {
  if (!rows || rows.length === 0) return;

  rows = [...new Set(rows)].sort((a, b) => a - b);
  const blocks = buildBlocks_(rows);

  blocks.forEach(([start, end]) => {
    const h = end - start + 1;
    sheet.getRange(start, COL_BG, h, 1).setValues(Array.from({ length: h }, () => [true]));
  });

  SpreadsheetApp.flush();
}


/*********** FILTER REFRESH ***********/

/**
 * Обновляет фильтры по BG в главной таблице и во всех связанных таблицах из LINKED_TARGETS.
 * Работает только с обычным фильтром, не с Filter view.
 */
function refreshAllBGFilters_(mainSS, mainSheet) {
  // Главный файл
  refreshBGFilterOnSheet_(mainSheet);

  // Связанные файлы
  LINKED_TARGETS.forEach(t => {
    try {
      const ss = SpreadsheetApp.openById(t.id);
      const sh = ss.getSheetByName(t.sheet);
      if (sh) refreshBGFilterOnSheet_(sh);
    } catch (e) {
      // игнорируем ошибки, чтобы не ломать основной сценарий
    }
  });

  SpreadsheetApp.flush();
}

/**
 * Переустанавливает критерий фильтра по колонке BG, заставляя таблицу перерисоваться.
 * Если критерий не задан, ставит "показывать только пустые".
 */
function refreshBGFilterOnSheet_(sheet) {
  const filter = sheet.getFilter();
  if (!filter) return;

  const existing = filter.getColumnFilterCriteria(COL_BG);
  if (existing) {
    filter.setColumnFilterCriteria(COL_BG, existing);
  } else {
    const crit = SpreadsheetApp.newFilterCriteria().whenCellEmpty().build();
    filter.setColumnFilterCriteria(COL_BG, crit);
  }
}


/*********** UTILS ***********/
function ensureColumns_(sheet, neededCol) {
  const cur = sheet.getMaxColumns();
  if (cur < neededCol) sheet.insertColumnsAfter(cur, neededCol - cur);
}

function isTrueLike_(txt) {
  const t = String(txt || '').trim().toLowerCase();
  return t === 'true' || t === '1' || t === 'כן';
}

function normalizeText_(v) {
  return String(v || '').replace(/\u200E|\u200F/g, '').trim();
}

function buildBlocks_(rowsSortedUnique) {
  const blocks = [];
  let s = rowsSortedUnique[0];
  let p = rowsSortedUnique[0];

  for (let i = 1; i <= rowsSortedUnique.length; i++) {
    const c = rowsSortedUnique[i];
    if (c === p + 1) {
      p = c;
    } else {
      blocks.push([s, p]);
      s = c;
      p = c;
    }
  }
  return blocks;
}

function colLetterToNumber_(letters) {
  let col = 0;
  const s = String(letters).toUpperCase().trim();
  for (let i = 0; i < s.length; i++) col = col * 26 + (s.charCodeAt(i) - 64);
  return col;
}

/**
 * Добавляем в конец блока ниже якоря (без риска перезаписи).
 */
function findAppendRowBelowNamedRange_(ss, sheet, namedRange, checkCol) {
  let startRow = 2;
  const nr = ss.getRangeByName(namedRange);
  if (nr && nr.getSheet().getName() === sheet.getName()) startRow = Math.max(2, nr.getRow() + 1);

  const lastRow = sheet.getLastRow();
  if (lastRow < startRow) return startRow;

  const vals = sheet.getRange(startRow, checkCol, lastRow - startRow + 1, 1).getValues();

  let lastNonEmpty = -1;
  for (let i = 0; i < vals.length; i++) {
    if (String(vals[i][0]).trim() !== '') lastNonEmpty = i;
  }
  return startRow + lastNonEmpty + 1;
}