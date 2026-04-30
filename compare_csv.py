import csv
import sys
import logging
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# ──────────────────────────────────────────────
#  Налаштування логування
# ──────────────────────────────────────────────

def setup_logger(log_path: str = "employee_diff.log") -> logging.Logger:
    logger = logging.getLogger("employee_diff")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # консоль
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # файл
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ──────────────────────────────────────────────
#  Читання CSV
# ──────────────────────────────────────────────

def read_csv(path: str) -> list[list[str]]:
    """
    Повертає список рядків (кожен рядок — список str).
    Перший рядок-заголовок пропускається.
    Порожні рядки ігноруються.
    """
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)          # пропустити заголовок
        for line_no, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                continue            # пустий рядок
            rows.append(row)
    return rows


def col(row: list[str], n: int) -> str:
    """Повертає значення Col{n} (1-based) або '' якщо колонки немає."""
    try:
        return row[n - 1].strip()
    except IndexError:
        return ""


# ──────────────────────────────────────────────
#  Допоміжні структури
# ──────────────────────────────────────────────

def build_index(rows: list[list[str]]) -> dict:
    """pib → список рядків із таким Col7."""
    idx: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        pib = col(row, 7)
        if pib:
            idx[pib].append(row)
    return idx


def find_row(pib: str, emp_id: str,
             index: dict[str, list[list[str]]]) -> list[str] | None:
    candidates = index.get(pib, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if emp_id:
        matched = [r for r in candidates if col(r, 9) == emp_id]
        if len(matched) == 1:
            return matched[0]
    return None


# ──────────────────────────────────────────────
#  Перевірка дублікатів всередині одного файлу
# ──────────────────────────────────────────────

def check_internal_duplicates(rows: list[list[str]],
                               label: str,
                               logger: logging.Logger) -> None:
    seen_col1: dict[str, list[int]] = defaultdict(list)
    seen_col7: dict[str, list[int]] = defaultdict(list)

    for i, row in enumerate(rows, start=1):
        c1 = col(row, 1)
        c7 = col(row, 7)
        if c1:
            seen_col1[c1].append(i)
        if c7:
            seen_col7[c7].append(i)

    logger.info(f"=== Перевірка дублікатів у файлі: {label} ===")

    dup_col1 = {k: v for k, v in seen_col1.items() if len(v) > 1}
    if dup_col1:
        for val, lines in sorted(dup_col1.items()):
            logger.warning(
                f"[ДУБЛІКАТ Col1] ПОРЯДКОВИЙ НОМЕР «{val}» "
                f"зустрічається {len(lines)} рази (рядки: {lines})"
            )
    else:
        logger.info("[OK] Дублікатів Col1 (ПОРЯДКОВИЙ НОМЕР) не знайдено.")

    dup_col7 = {k: v for k, v in seen_col7.items() if len(v) > 1}
    if dup_col7:
        for val, lines in sorted(dup_col7.items()):
            logger.warning(
                f"[ДУБЛІКАТ Col7] ПІБ «{val}» "
                f"зустрічається {len(lines)} рази (рядки: {lines})"
            )
    else:
        logger.info("[OK] Дублікатів Col7 (ПІБ) не знайдено.")


# ──────────────────────────────────────────────
#  Головна функція порівняння
# ──────────────────────────────────────────────

TRACKED_COLS = {
    8:  "ПРИМІТКА",
    9:  "НОМЕР ПРАЦІВНИКА",
    11: "СТАТУС КОЛЬОРУ КЛІТИНКИ ПІБ",
}

SEP = "=" * 34  # роздільник секцій


def log_section(title: str, messages: list[str], logger: logging.Logger) -> None:
    """Виводить заголовок секції і всі її повідомлення як WARNING."""
    logger.info("")
    logger.info(f"{SEP} {title} {SEP}")
    if messages:
        for msg in messages:
            logger.warning(msg)
    else:
        logger.info("Змін не виявлено.")


def compare_csv(old_path: str,
                new_path: str,
                log_path: str = "employee_diff.log") -> None:
    logger = setup_logger(log_path)

    logger.info("=" * 70)
    logger.info(f"СТАРИЙ файл : {old_path}")
    logger.info(f"НОВИЙ  файл : {new_path}")
    logger.info(f"Лог         : {log_path}")
    logger.info("=" * 70)

    # ── читання ──────────────────────────────
    old_rows = read_csv(old_path)
    new_rows = read_csv(new_path)
    logger.info(f"Записів у старому файлі: {len(old_rows)}")
    logger.info(f"Записів у новому  файлі: {len(new_rows)}")

    # ── внутрішні дублікати ───────────────────
    check_internal_duplicates(old_rows, f"СТАРИЙ ({old_path})", logger)
    check_internal_duplicates(new_rows, f"НОВИЙ  ({new_path})", logger)

    # ── індекси ──────────────────────────────
    old_index = build_index(old_rows)
    new_index = build_index(new_rows)

    old_pibs = set(old_index.keys())
    new_pibs = set(new_index.keys())

    fired         = old_pibs - new_pibs
    new_employees = new_pibs - old_pibs
    common        = old_pibs & new_pibs

    # ──────────────────────────────────────────
    #  1. ЗВІЛЬНЕНІ
    # ──────────────────────────────────────────
    logger.info("")
    logger.info("─── ЗВІЛЬНЕНІ ───────────────────────────────────────────")
    if fired:
        for pib in sorted(fired):
            for row in old_index[pib]:
                logger.warning(
                    f"[ЗВІЛЬНЕНИЙ] «{pib}» | "
                    f"Col1={col(row,1)} | Col2={col(row,2)} | "
                    f"[Col6]={col(row,6)} | Col9={col(row,9)}"
                )
    else:
        logger.info("Звільнених не виявлено.")

    # ──────────────────────────────────────────
    #  2. НОВІ ПРАЦІВНИКИ
    # ──────────────────────────────────────────
    logger.info("")
    logger.info("─── НОВІ ПРАЦІВНИКИ ─────────────────────────────────────")
    if new_employees:
        for pib in sorted(new_employees):
            for row in new_index[pib]:
                logger.info(
                    f"[НОВИЙ ПРАЦІВНИК] «{pib}» | "
                    f"Col1={col(row,1)} | Col2={col(row,2)} | "
                    f"[Col6]={col(row,6)} | Col9={col(row,9)}"
                )
    else:
        logger.info("Нових працівників не виявлено.")

    # ──────────────────────────────────────────
    #  3. ЗМІНИ У СПІЛЬНИХ ЗАПИСАХ
    # ──────────────────────────────────────────

    buf_ambiguous: list[str] = []  # неоднозначності
    buf_position:  list[str] = []  # [ЗМІНА ПОСАДИ]  — Col1
    buf_status:    list[str] = []  # [ЗМІНА СТАТУСУ] — Col6
    buf_field:     list[str] = []  # [ЗМІНА ПОЛЯ]    — Col8 / Col9 / Col11

    for pib in sorted(common):
        old_candidates = old_index[pib]
        new_candidates = new_index[pib]

        # неоднозначна ситуація: кілька записів з обох сторін
        if len(old_candidates) > 1 and len(new_candidates) > 1:
            buf_ambiguous.append(
                f"[НЕОДНОЗНАЧНІСТЬ] ПІБ «{pib}» має {len(old_candidates)} записів "
                f"у старому і {len(new_candidates)} у новому файлі. "
                f"Автоматичне зіставлення неможливе — перевірте вручну."
            )
            continue

        # зіставляємо пари old ↔ new
        pairs: list[tuple[list[str], list[str]]] = []

        if len(old_candidates) == 1 and len(new_candidates) == 1:
            pairs = [(old_candidates[0], new_candidates[0])]

        elif len(old_candidates) == 1 and len(new_candidates) > 1:
            emp_id = col(old_candidates[0], 9)
            matched_new = ([r for r in new_candidates if col(r, 9) == emp_id]
                           if emp_id else [])
            if len(matched_new) == 1:
                pairs = [(old_candidates[0], matched_new[0])]
            else:
                buf_ambiguous.append(
                    f"[НЕОДНОЗНАЧНІСТЬ] ПІБ «{pib}» — 1 старий запис, "
                    f"{len(new_candidates)} нових. Уточнення через Col9 не дало "
                    f"однозначного результату. Перевірте вручну."
                )
                continue

        elif len(old_candidates) > 1 and len(new_candidates) == 1:
            emp_id = col(new_candidates[0], 9)
            matched_old = ([r for r in old_candidates if col(r, 9) == emp_id]
                           if emp_id else [])
            if len(matched_old) == 1:
                pairs = [(matched_old[0], new_candidates[0])]
            else:
                buf_ambiguous.append(
                    f"[НЕОДНОЗНАЧНІСТЬ] ПІБ «{pib}» — {len(old_candidates)} старих "
                    f"записів, 1 новий. Уточнення через Col9 не дало однозначного "
                    f"результату. Перевірте вручну."
                )
                continue

        # аналізуємо кожну пару — кладемо у відповідний буфер
        for old_row, new_row in pairs:

            old_c1, new_c1 = col(old_row, 1), col(new_row, 1)
            if old_c1 != new_c1:
                buf_position.append(
                    f"[ЗМІНА ПОСАДИ] «{pib}» | "
                    f"Col1: {old_c1!r} → {new_c1!r} | "
                    f"Стара посада (Col2): {col(old_row,2)!r} | "
                    f"Нова  посада (Col2): {col(new_row,2)!r}"
                )

            old_st, new_st = col(old_row, 6), col(new_row, 6)
            if old_st != new_st:
                buf_status.append(
                    f"[ЗМІНА СТАТУСУ] «{pib}» | "
                    f"Статус (Col6): {old_st!r} → {new_st!r}"
                )

            for cn, cname in TRACKED_COLS.items():
                old_val, new_val = col(old_row, cn), col(new_row, cn)
                if old_val != new_val:
                    buf_field.append(
                        f"[ЗМІНА ПОЛЯ] «{pib}» | "
                        f"Col{cn} ({cname}): {old_val!r} → {new_val!r}"
                    )

    # ── виводимо по секціях із заголовками ───
    logger.info("")
    logger.info("─── ЗМІНИ У ЗАПИСАХ ─────────────────────────────────────")

    if not any([buf_ambiguous, buf_position, buf_status, buf_field]):
        logger.info("Змін у спільних записах не виявлено.")
    else:
        if buf_ambiguous:
            log_section("[НЕОДНОЗНАЧНОСТІ]", buf_ambiguous, logger)
        log_section("[ЗМІНИ ПОСАДИ]",  buf_position, logger)
        log_section("[ЗМІНИ СТАТУСУ]", buf_status,   logger)
        log_section("[ЗМІНИ ПОЛЯ]",    buf_field,     logger)

    logger.info("")
    logger.info("=" * 70)
    logger.info("Порівняння завершено.")
    logger.info("=" * 70)


# ──────────────────────────────────────────────
#  Точка входу
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Порівняння CSV-файлів працівників ===")
    print("Файли мають бути в одній папці зі скриптом,")
    print("або вкажіть повний шлях до файлу.\n")

    old_file = input("Назва СТАРОГО CSV-файлу: ").strip()
    new_file = input("Назва НОВОГО  CSV-файлу: ").strip()
    log_file = input("Назва лог-файлу [Enter = employee_diff.log]: ").strip()

    if not log_file:
        log_file = "employee_diff.log"

    if not Path(old_file).exists():
        print(f"Помилка: файл «{old_file}» не знайдено.")
        sys.exit(1)

    if not Path(new_file).exists():
        print(f"Помилка: файл «{new_file}» не знайдено.")
        sys.exit(1)

    compare_csv(old_file, new_file, log_file)
