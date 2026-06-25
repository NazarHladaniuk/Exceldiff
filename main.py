import os
from pathlib import Path
import logging

# Імпортуємо твої існуючі функції
from read_xlsx import process_excel_to_single_csv
from compare_csv import compare_and_update
from csv_to_xlsx import convert_csv_to_formatted_excel

def main():
    print("=== Запуск пайплайну обробки файлів ===")

    # 1. Налаштування шляхів
    base_dir = Path(__file__).parent
    input_dir = base_dir / "input"
    temp_dir = base_dir / "temp"
    output_dir = base_dir / "output"

    # Створюємо папки, якщо їх не існує
    for directory in [input_dir, temp_dir, output_dir]:
        directory.mkdir(exist_ok=True)

    # 2. Визначення вхідних файлів
    # Шукаємо старий CSV та новий XLSX в папці input/
    old_csv_files = list(input_dir.glob("*.csv"))
    new_xlsx_files = list(input_dir.glob("*.xlsx"))

    if not old_csv_files or not new_xlsx_files:
        print("Помилка: Переконайтесь, що в папці 'input' є хоча б один старий .csv та один новий .xlsx файл.")
        return

    old_csv_path = old_csv_files[0]
    input_xlsx_path = new_xlsx_files[0]

    # Шляхи для проміжних та фінальних файлів
    temp_csv_from_xlsx = temp_dir / "extracted_new.csv"
    temp_updated_csv = temp_dir / "updated_new.csv"
    
    final_xlsx_path = output_dir / f"FINAL_{input_xlsx_path.stem}.xlsx"
    log_path = output_dir / "info.log"

    print(f"\n[Етап 1] Конвертація вхідного XLSX ({input_xlsx_path.name}) у тимчасовий CSV...")
    success = process_excel_to_single_csv(str(input_xlsx_path), str(temp_csv_from_xlsx))
    
    if success is False:
         print("Процес зупинено через помилку на Етапі 1.")
         return

    print(f"\n[Етап 2] Порівняння старого CSV ({old_csv_path.name}) та нового CSV...")
    compare_and_update(
        old_path=str(old_csv_path), 
        new_path=str(temp_csv_from_xlsx), 
        out_csv=str(temp_updated_csv), 
        log_path=str(log_path)
    )

    print(f"\n[Етап 3] Форматування фінального XLSX файлу...")
    convert_csv_to_formatted_excel(
        csv_path=temp_updated_csv, 
        excel_path=final_xlsx_path
    )

    print(f"\n=== Готово! Фінальний результат збережено в: {final_xlsx_path} ===")

if __name__ == "__main__":
    main()
