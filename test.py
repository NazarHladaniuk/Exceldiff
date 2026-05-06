def diff_csv(file1_path, file2_path):
    def read_csv_to_set(path):
        with open(path, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())

    set1 = read_csv_to_set(file1_path)
    set2 = read_csv_to_set(file2_path)

    return {
        "added": list(set2 - set1),
        "removed": list(set1 - set2),
        "common": list(set1 & set2)
    }


result = diff_csv('str_new.csv', 'str_new040526.csv')

print("Додано:", result["added"])
print("Видалено:", result["removed"])
