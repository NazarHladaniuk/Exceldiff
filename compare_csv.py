import csv
import sys
import logging
from pathlib import Path
from collections import defaultdict, Counter


# ═══════════════════════════════════════════════════════════
#  ЛОГУВАННЯ
# ═══════════════════════════════════════════════════════════

def setup_logger(log_path: str = "info.log") -> logging.Logger:
    logger = logging.getLogger("employee_diff")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s  [%(levelname)s]  %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    for handler in [logging.StreamHandler(sys.stdout),
                    logging.FileHandler(log_path, encoding="utf-8")]:
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


SEP = "=" * 34

def log_section(title: str, messages: list, logger: logging.Logger) -> None:
    """Виводить заголовок секції і всі повідомлення як WARNING."""
    logger.info("")
    logger.info(f"{SEP} {title} {SEP}")
    if messages:
        for msg in messages:
            logger.warning(msg)
    else:
        logger.info("Змін не виявлено.")


# ═══════════════════════════════════════════════════════════
#  ЧИТАННЯ CSV
# ═══════════════════════════════════════════════════════════

def normalize(v) -> str:
    """Нормалізує значення: None / 'False' / 'false' → ''."""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "false" else s


def is_structure_row(raw: list) -> bool:
    """
    Структурний рядок: Col1 — непорожній текст (не число),
    решта колонок  — 'False' або порожні.
    """
    if not raw:
        return False
    c1 = raw[0].strip() if raw[0] else ""
    if not c1:
        return False
    try:
        float(c1)   # Col1 — число → не структурний рядок
        return False
    except ValueError:
        pass
    return all(v.strip().lower() in ("false", "") for v in raw[1:])


def read_combined_csv(path: str) -> tuple:
    """
    Читає об'єднаний CSV.

    Повертає:
      staff_rows     — записи з непорожнім Col7 (ПІБ), з полем 'subdivision'
      structure_list — список назв підрозділів по порядку (з повторами)
      raw_rows       — всі сирі рядки для запису updated_new.csv
    """
    staff_rows     = []
    structure_list = []
    raw_rows       = []
    current_sub    = None

    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.reader(f):
            raw_rows.append(raw)          # зберігаємо кожен рядок

            if not any(v.strip() for v in raw):
                continue                  # порожній рядок — пропускаємо

            if is_structure_row(raw):
                current_sub = raw[0].strip()
                structure_list.append(current_sub)
                continue

            def g(n: int) -> str:
                return normalize(raw[n - 1]) if len(raw) >= n else ""

            pib = g(7)
            if not pib:
                continue                  # вакантна посада — не в staff_rows

            staff_rows.append({
                'raw':         raw,       # той самий об'єкт, що й у raw_rows
                'subdivision': current_sub,
                'col1':  g(1),  'col2':  g(2),  'col3':  g(3),
                'col4':  g(4),  'col5':  g(5),  'col6':  g(6),
                'col7':  pib,   'col8':  g(8),  'col9':  g(9),
                'col10': g(10), 'col11': g(11), 'col12': g(12),
            })

    return staff_rows, structure_list, raw_rows


# ═══════════════════════════════════════════════════════════
#  ІНДЕКС ПО ПІБ
# ═══════════════════════════════════════════════════════════

def build_pib_index(staff: list) -> dict:
    idx = defaultdict(list)
    for e in staff:
        idx[e['col7']].append(e)
    return idx


# ═══════════════════════════════════════════════════════════
#  ПЕРЕВІРКА ДУБЛІКАТІВ
# ═══════════════════════════════════════════════════════════

_DUP_COLS = {
    'col1':  'Col1  (ПОРЯДКОВИЙ НОМЕР)',
    'col7':  'Col7  (ПІБ)',
    'col9':  'Col9  (ТАБЕЛЬНИЙ НОМЕР)',
    'col11': 'Col11 (ТЕЛЕФОН)',
}

def check_duplicates(staff: list, label: str, logger: logging.Logger) -> None:
    logger.info(f"=== Перевірка дублікатів у файлі: {label} ===")
    seen = {k: defaultdict(list) for k in _DUP_COLS}

    for i, e in enumerate(staff, start=1):
        for k in _DUP_COLS:
            v = e[k]
            if v:
                seen[k][v].append(i)

    for k, col_label in _DUP_COLS.items():
        dups = {v: lines for v, lines in seen[k].items() if len(lines) > 1}
        if dups:
            for v, lines in sorted(dups.items()):
                logger.warning(
                    f"[ДУБЛІКАТ {k.upper()}] {col_label} «{v}» "
                    f"зустрічається {len(lines)} рази (записи: {lines})"
                )
        else:
            logger.info(f"[OK] Дублікатів {col_label} не знайдено.")


# ═══════════════════════════════════════════════════════════
#  ЗІСТАВЛЕННЯ ЗАПИСІВ (ПАРИНГ)
# ═══════════════════════════════════════════════════════════

def build_pairs(pib: str, old_index: dict, new_index: dict) -> list:
    """
    Зіставляє записи старого та нового файлів для одного ПІБ.
    Повертає список: (old_entry | None, new_entry, status)

    status:
      'ok'                  — однозначне зіставлення
      'ambiguous_no_col9'   — дублі ПІБ, Col9 відсутній у всіх
      'ambiguous_with_col9' — дублі ПІБ, Col9 є, але не дав результату
    """
    old_cands = old_index.get(pib, [])
    new_cands = new_index.get(pib, [])

    if not old_cands or not new_cands:
        return []

    # Простий випадок: по одному з кожного боку
    if len(old_cands) == 1 and len(new_cands) == 1:
        return [(old_cands[0], new_cands[0], 'ok')]

    # Кілька записів — спочатку зіставляємо за Col9
    pairs    = []
    used_old = set()
    used_new = set()

    for ni, new_e in enumerate(new_cands):
        if not new_e['col9']:
            continue
        for oi, old_e in enumerate(old_cands):
            if oi in used_old:
                continue
            if old_e['col9'] == new_e['col9']:
                pairs.append((old_e, new_e, 'ok'))
                used_old.add(oi)
                used_new.add(ni)
                break

    rem_old = [e for i, e in enumerate(old_cands) if i not in used_old]
    rem_new = [e for i, e in enumerate(new_cands) if i not in used_new]

    if len(rem_old) == 1 and len(rem_new) == 1:
        has_col9 = rem_old[0]['col9'] or rem_new[0]['col9']
        status   = 'ambiguous_with_col9' if has_col9 else 'ambiguous_no_col9'
        pairs.append((rem_old[0], rem_new[0], status))
    else:
        for new_e in rem_new:
            has_col9 = any(e['col9'] for e in rem_old) or new_e['col9']
            status   = 'ambiguous_with_col9' if has_col9 else 'ambiguous_no_col9'
            pairs.append((None, new_e, status))

    return pairs


# ═══════════════════════════════════════════════════════════
#  ГОЛОВНА ФУНКЦІЯ
# ═══════════════════════════════════════════════════════════

# Поля для відстеження змін (окрім Col1/Col5 які мають окрему логіку)
TRACKED_FIELDS = {
    'col8':  'Col8  (ПРИМІТКА)',
    'col9':  'Col9  (ТАБЕЛЬНИЙ НОМЕР)',
    'col12': 'Col12 (КОЛІР КЛІТИНКИ)',
}


def compare_and_update(old_path: str, new_path: str,
                        out_csv:  str = "updated_new.csv",
                        log_path: str = "info.log") -> None:

    logger = setup_logger(log_path)

    logger.info("=" * 70)
    logger.info(f"СТАРИЙ файл : {old_path}")
    logger.info(f"НОВИЙ  файл : {new_path}")
    logger.info(f"Вихідний CSV: {out_csv}")
    logger.info(f"Лог         : {log_path}")
    logger.info("=" * 70)

    # ── читання ──────────────────────────────────────────────
    old_staff, old_struct, _        = read_combined_csv(old_path)
    new_staff, new_struct, new_raws = read_combined_csv(new_path)

    logger.info(f"Працівників у старому файлі: {len(old_staff)}")
    logger.info(f"Працівників у новому  файлі: {len(new_staff)}")

    # ── перевірка дублікатів ─────────────────────────────────
    check_duplicates(old_staff, f"СТАРИЙ ({old_path})", logger)
    check_duplicates(new_staff, f"НОВИЙ  ({new_path})", logger)

    # ── зміни структури підрозділів ──────────────────────────
    logger.info("")
    logger.info(f"{SEP} [ЗМІНИ СТРУКТУРИ ПІДРОЗДІЛІВ] {SEP}")
    old_cnt = Counter(old_struct)
    new_cnt = Counter(new_struct)
    struct_changes = []
    for name in sorted(set(old_cnt) | set(new_cnt)):
        o = old_cnt.get(name, 0)
        n = new_cnt.get(name, 0)
        diff = n - o
        if diff > 0:
            struct_changes.append(
                f"[ПІДРОЗДІЛ ДОДАНО]   «{name}»: було {o} → стало {n} (+{diff})"
            )
        elif diff < 0:
            struct_changes.append(
                f"[ПІДРОЗДІЛ ВИДАЛЕНО] «{name}»: було {o} → стало {n} ({diff})"
            )
    if struct_changes:
        for msg in struct_changes:
            logger.warning(msg)
        logger.info(
            f"Загалом підрозділів: було {len(old_struct)}, стало {len(new_struct)}"
        )
    else:
        logger.info("Структура підрозділів не змінилась.")

    # ── індекси ──────────────────────────────────────────────
    old_index = build_pib_index(old_staff)
    new_index = build_pib_index(new_staff)

    old_pibs = set(old_index)
    new_pibs = set(new_index)

    fired         = old_pibs - new_pibs
    new_employees = new_pibs - old_pibs
    common        = old_pibs & new_pibs

    # ── ЗВІЛЬНЕНІ ────────────────────────────────────────────
    logger.info("")
    logger.info("─── ЗВІЛЬНЕНІ ───────────────────────────────────────────")
    if fired:
        for pib in sorted(fired):
            for e in old_index[pib]:
                logger.warning(
                    f"[ЗВІЛЬНЕНИЙ] «{pib}» | Col1={e['col1']} | "
                    f"Посада={e['col2']} | Підрозділ={e['subdivision']} | "
                    f"Col9={e['col9']}"
                )
    else:
        logger.info("Звільнених не виявлено.")

    # ── НОВІ ПРАЦІВНИКИ ──────────────────────────────────────
    logger.info("")
    logger.info("─── НОВІ ПРАЦІВНИКИ ─────────────────────────────────────")
    if new_employees:
        for pib in sorted(new_employees):
            for e in new_index[pib]:
                logger.info(
                    f"[НОВИЙ ПРАЦІВНИК] «{pib}» | Col1={e['col1']} | "
                    f"Посада={e['col2']} | Підрозділ={e['subdivision']} | "
                    f"Col9={e['col9']}"
                )
    else:
        logger.info("Нових працівників не виявлено.")

    # ── ЗМІНИ У СПІЛЬНИХ ЗАПИСАХ ─────────────────────────────
    buf_ambiguous:   list[str] = []
    buf_subdivision: list[str] = []   # однакова посада, інший підрозділ
    buf_position:    list[str] = []   # зміна посади / Col1
    buf_status:      list[str] = []   # зміна Col5
    buf_field:       list[str] = []   # зміна Col8 / Col9 / Col12

    # id(raw) → (col10, col11) для оновлення CSV
    update_map: dict[int, tuple] = {}

    for pib in sorted(common):
        for old_e, new_e, status in build_pairs(pib, old_index, new_index):

            # ── неоднозначні випадки ─────────────────────────
            if status == 'ambiguous_no_col9':
                buf_ambiguous.append(
                    f"[НЕОДНОЗНАЧНІСТЬ — БЕЗ ТАБЕЛЬНОГО] ПІБ «{pib}» — "
                    f"кілька записів в старому файлі, Col9 відсутній у всіх. "
                    f"Col10/Col11 не скопійовано. Перевірте вручну."
                )
                continue

            if status == 'ambiguous_with_col9':
                buf_ambiguous.append(
                    f"[НЕОДНОЗНАЧНІСТЬ] ПІБ «{pib}» — "
                    f"кілька записів, Col9 не дав однозначного результату. "
                    f"Col10/Col11 не скопійовано. Перевірте вручну."
                )
                continue

            if old_e is None:
                continue

            # ── копіюємо Col10 / Col11 зі старого файлу ─────
            if old_e['col10'] or old_e['col11']:
                update_map[id(new_e['raw'])] = (old_e['col10'], old_e['col11'])

            # ── зміна посади або підрозділу ──────────────────
            if old_e['col1'] != new_e['col1']:
                same_pos = (old_e['col2'] == new_e['col2'])
                same_sub = (old_e['subdivision'] == new_e['subdivision'])

                if same_pos and not same_sub:
                    # та сама назва посади — але інший підрозділ
                    buf_subdivision.append(
                        f"[ЗМІНА ПІДРОЗДІЛУ] «{pib}» | "
                        f"Посада (Col2): {new_e['col2']!r} (незмінна) | "
                        f"Підрозділ: {old_e['subdivision']!r} → "
                        f"{new_e['subdivision']!r} | "
                        f"Col1: {old_e['col1']!r} → {new_e['col1']!r}"
                    )
                else:
                    buf_position.append(
                        f"[ЗМІНА ПОСАДИ] «{pib}» | "
                        f"Col1: {old_e['col1']!r} → {new_e['col1']!r} | "
                        f"Стара посада: {old_e['col2']!r} | "
                        f"Нова  посада: {new_e['col2']!r} | "
                        f"Підрозділ: {old_e['subdivision']!r} → "
                        f"{new_e['subdivision']!r}"
                    )

            # ── зміна статусу (Col5) ─────────────────────────
            if old_e['col5'] != new_e['col5']:
                buf_status.append(
                    f"[ЗМІНА СТАТУСУ] «{pib}» | "
                    f"Col5: {old_e['col5']!r} → {new_e['col5']!r}"
                )

            # ── решта відстежуваних полів ────────────────────
            for key, label in TRACKED_FIELDS.items():
                if old_e[key] != new_e[key]:
                    buf_field.append(
                        f"[ЗМІНА ПОЛЯ] «{pib}» | "
                        f"{label}: {old_e[key]!r} → {new_e[key]!r}"
                    )

    # ── виводимо по секціях із заголовками ───────────────────
    logger.info("")
    logger.info("─── ЗМІНИ У ЗАПИСАХ ─────────────────────────────────────")

    if not any([buf_ambiguous, buf_subdivision, buf_position, buf_status, buf_field]):
        logger.info("Змін у спільних записах не виявлено.")
    else:
        if buf_ambiguous:
            log_section("[НЕОДНОЗНАЧНОСТІ]",  buf_ambiguous,   logger)
        log_section("[ЗМІНИ ПІДРОЗДІЛУ]",     buf_subdivision, logger)
        log_section("[ЗМІНИ ПОСАДИ]",         buf_position,    logger)
        log_section("[ЗМІНИ СТАТУСУ]",        buf_status,      logger)
        log_section("[ЗМІНИ ПОЛЯ]",           buf_field,       logger)

    logger.info("")
    logger.info("=" * 70)
    logger.info("Порівняння завершено.")
    logger.info("=" * 70)

    # ── запис updated_new.csv ─────────────────────────────────
    _write_updated_csv(new_raws, update_map, out_csv)
    logger.info(f"Збережено: {out_csv}")


def _write_updated_csv(raw_rows: list, update_map: dict, out_path: str) -> None:
    """
    Записує updated_new.csv — повна копія new.csv, але з заповненими
    Col10 та Col11 там де вдалося знайти дані в старому файлі.
    """
    with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for raw in raw_rows:
            row_id = id(raw)
            if row_id in update_map:
                updated = list(raw)
                col10, col11 = update_map[row_id]
                while len(updated) < 11:
                    updated.append("")
                if col10:
                    updated[9]  = col10   # Col10 = індекс 9
                if col11:
                    updated[10] = col11   # Col11 = індекс 10
                writer.writerow(updated)
            else:
                writer.writerow(raw)


# ═══════════════════════════════════════════════════════════
#  ТОЧКА ВХОДУ
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Порівняння CSV-файлів працівників ===\n")

    old_file = input("Назва СТАРОГО CSV-файлу: ").strip()
    new_file = input("Назва НОВОГО  CSV-файлу: ").strip()
    out_file = (input("Назва вихідного CSV    [Enter = updated_new.csv]: ").strip()
                or "updated_new.csv")
    log_file = (input("Назва лог-файлу        [Enter = info.log]: ").strip()
                or "info.log")

    for f in [old_file, new_file]:
        if not Path(f).exists():
            print(f"Помилка: файл «{f}» не знайдено.")
            sys.exit(1)

    compare_and_update(old_file, new_file, out_file, log_file)
