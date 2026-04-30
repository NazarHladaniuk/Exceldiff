from openpyxl import load_workbook
import csv

def save_to_csv(file_name, rows):
    with open(file_name, mode="w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if rows and not isinstance(rows[0], list):
            writer.writerows([[row] for row in rows])
        else:
            writer.writerows(rows)
    print(f"Збережено у файл: {file_name} | Записів: {len(rows)}")

def extract_structure_list(file_path):
    # data_only=True Читати результат формул, а не самі формули
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active
    result_rows = []

    for row in ws.iter_rows(min_col=1, max_col=1, values_only=True):
        first_value = row[0]
        if isinstance(first_value, str):
            first_value = first_value.strip()
            if first_value and first_value != "№ з/п":
                result_rows.append(first_value)
    return result_rows

def extract_staff_list(file_path):
    wb = load_workbook(file_path, data_only=True)
    ws = wb.active
    result_rows = []

    for row in ws.iter_rows(max_col=9): 
        if not row[0].value and not row[6].value:
            continue  # Пропускаємо порожні рядки відразу

        first_cell = row[0]   # №
        name_cell = row[6]    # ПІБ

        first_value = first_cell.value
        name_value = name_cell.value

        if isinstance(first_value, int) and name_value:
            has_background = False
            fill = name_cell.fill

            # Наявність кольору
            if fill and fill.patternType == 'solid':
                color_index = fill.fgColor.index
                color_rgb = fill.fgColor.rgb
                
                # Якщо колір не стандартний "авто" (0) або не чисто білий
                if color_index != 0 or (color_rgb and color_rgb != '00000000' and color_rgb != 'FFFFFFFF'):
                    has_background = True

            # Збираємо значення рядка (лише заповнені колонки)
            row_values = [cell.value for cell in row]
            row_values.append(has_background)
            
            result_rows.append(row_values)
            print(f"Оброблено: {name_value}")

    return result_rows

if __name__ == "__main__":
    source_excel = "fresh.xlsx"
    
    try:
        print("Читаємо структуру...")
        structure_data = extract_structure_list(source_excel)
        save_to_csv("str_fresh.csv", structure_data)

        print("Читаємо персонал (це може зайняти час)...")
        staff_data = extract_staff_list(source_excel)
        save_to_csv("all_fresh.csv", staff_data)
        
    except FileNotFoundError:
        print(f"Помилка: Файл {source_excel} не знайдено.")
    except Exception as e:
        print(f"Сталася помилка: {e}")
