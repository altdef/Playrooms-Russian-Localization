
import os
import json
import UnityPy

BASE_DIR = r"D:\loc\cellarkeeper\Game_Translation"

SOURCE_BUNDLE = (
    r"D:\do\Playrooms\Playrooms_Data\StreamingAssets\aa"
    r"\StandaloneWindows64\localization-string-tables-italian(it)_assets_all.bundle"
)

OUTPUT_BUNDLE = os.path.join(
    BASE_DIR,
    "localization-string-tables-russian-preserved.bundle"
)

JSON_DIR = os.path.join(BASE_DIR, "Russian_Tables")

TABLES = {
    "Mails_it": "Mails_ru.json",
    "General_it": "General_ru.json",
    "Popups_it": "Popups_ru.json",
    "Balli_it": "Balli_ru.json",
    "Skills_it": "Skills_ru.json",
    "Items_it": "Items_ru.json",
}


def load_translations(filename):
    path = os.path.join(JSON_DIR, filename)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    table = data.get("m_TableData", {})
    rows = table.get("Array", []) if isinstance(table, dict) else table

    translations = {}

    for row in rows:
        if "m_Id" in row and "m_Localized" in row:
            translations[row["m_Id"]] = row["m_Localized"]

    return translations


print("Загружаю оригинальный итальянский бандл...")
env = UnityPy.load(SOURCE_BUNDLE)

updated = 0
total_changed = 0

for obj in env.objects:
    if obj.type.name != "MonoBehaviour":
        continue

    data = obj.read_typetree()
    table_name = data.get("m_Name")

    if table_name not in TABLES:
        continue

    translations = load_translations(TABLES[table_name])

    table_data = data.get("m_TableData", {})
    rows = (
        table_data.get("Array", [])
        if isinstance(table_data, dict)
        else table_data
    )

    changed = 0
    missing = 0

    for row in rows:
        entry_id = row.get("m_Id")

        if entry_id in translations:
            row["m_Localized"] = translations[entry_id]
            changed += 1
        else:
            missing += 1

    data["m_LocaleId"]["m_Code"] = "ru"

    obj.save_typetree(data)

    print(
        f"{table_name}: заменено {changed} из {len(rows)}; "
        f"нет совпадения: {missing}"
    )

    total_changed += changed
    updated += 1

if updated != 6:
    raise RuntimeError(
        f"Ожидалось 6 таблиц, обработано: {updated}"
    )

if total_changed == 0:
    raise RuntimeError("Не найдено ни одного совпадающего ID!")

print("\nСохраняю с оригинальными параметрами UnityFS...")

result = env.file.save(packer="original")

with open(OUTPUT_BUNDLE, "wb") as f:
    f.write(result)

print("\nГотово!")
print("Всего заменено строк:", total_changed)
print("Файл:", OUTPUT_BUNDLE)
print("Размер:", os.path.getsize(OUTPUT_BUNDLE), "байт")

print("\nПроверка повторной загрузки...")
check = UnityPy.load(OUTPUT_BUNDLE)

print("Объектов:", len(check.objects))
print("Флаги UnityFS:", check.file.dataflags)
print("Флаги блока:", check.file._block_info_flags)

for obj in check.objects:
    if obj.type.name != "MonoBehaviour":
        continue

    data = obj.read_typetree()

    if data.get("m_Name") in TABLES:
        table = data["m_TableData"]
        rows = table.get("Array", []) if isinstance(table, dict) else table

        print(
            data["m_Name"],
            "| код:", data["m_LocaleId"]["m_Code"],
            "| строк:", len(rows),
            "| пример:", rows[0]["m_Localized"] if rows else "пусто"
        )
