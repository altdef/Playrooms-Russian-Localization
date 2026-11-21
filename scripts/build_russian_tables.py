import json
import os
import urllib.request
from pathlib import Path

import UnityPy


# Локальные пути
BASE_DIR = Path(r"D:\loc\PlayRooms")
SOURCE_BUNDLE = Path(
    r"D:\do\Playrooms\Playrooms_Data\StreamingAssets\aa"
    r"\StandaloneWindows64\localization-string-tables-italian(it)_assets_all.bundle"
)
OUTPUT_DIR = BASE_DIR / "bundles"
OUTPUT_BUNDLE = OUTPUT_DIR / "localization-string-tables-russian-preserved.bundle"

# Русские JSON загружаются напрямую из GitHub при каждом запуске.
GITHUB_RAW = (
    "https://raw.githubusercontent.com/"
    "altdef/Playrooms-Russian-Localization/main/Russian/"
)

TABLES = {
    "Mails_it": "Mails_ru.json",
    "General_it": "General_ru.json",
    "Popups_it": "Popups_ru.json",
    "Balli_it": "Balli_ru.json",
    "Skills_it": "Skills_ru.json",
    "Items_it": "Items_ru.json",
}


def download_translations(filename):
    url = GITHUB_RAW + filename
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Playrooms-Russian-Localization-Builder"},
    )

    print(f"Загружаю с GitHub: {filename}")

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    data = json.loads(raw.decode("utf-8-sig"))

    table = data.get("m_TableData", {})
    rows = table.get("Array", []) if isinstance(table, dict) else table

    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"В {filename} не найдены записи m_TableData.Array")

    # Один m_Id может встречаться несколько раз (например, текст письма
    # и его тема). Сохраняем все варианты в исходном порядке.
    translations = {}
    for row in rows:
        if "m_Id" not in row or "m_Localized" not in row:
            raise RuntimeError(f"Некорректная запись в {filename}: отсутствует m_Id или m_Localized")
        entry_id = row["m_Id"]
        translations.setdefault(entry_id, []).append(row["m_Localized"])

    duplicate_count = sum(len(values) - 1 for values in translations.values())
    print(
        f"  Получено записей: {len(rows)} "
        f"(уникальных ID: {len(translations)}, повторов: {duplicate_count})"
    )
    return translations


def main():
    if not SOURCE_BUNDLE.is_file():
        raise FileNotFoundError(f"Не найден исходный Unity-бандл:\n{SOURCE_BUNDLE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Сначала скачиваем и проверяем все JSON. Если хотя бы один недоступен,
    # сборка не начинается и старый результат не перезаписывается.
    all_translations = {
        table_name: download_translations(filename)
        for table_name, filename in TABLES.items()
    }

    print("\nЗагружаю оригинальный итальянский бандл...")
    env = UnityPy.load(str(SOURCE_BUNDLE))

    updated = 0
    total_changed = 0
    total_missing = 0

    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue

        data = obj.read_typetree()
        table_name = data.get("m_Name")

        if table_name not in TABLES:
            continue

        translations = all_translations[table_name]
        table_data = data.get("m_TableData", {})
        rows = (
            table_data.get("Array", [])
            if isinstance(table_data, dict)
            else table_data
        )

        changed = 0
        missing = 0
        occurrence_index = {}

        for row in rows:
            entry_id = row.get("m_Id")
            if entry_id in translations:
                position = occurrence_index.get(entry_id, 0)
                values = translations[entry_id]

                if position >= len(values):
                    raise RuntimeError(
                        f"{table_name}: в Unity-бандле больше повторов m_Id "
                        f"{entry_id}, чем в JSON. Бандл не сохранён."
                    )

                row["m_Localized"] = values[position]
                occurrence_index[entry_id] = position + 1
                changed += 1
            else:
                missing += 1

        # Проверяем, что JSON и исходная таблица содержат одинаковое
        # количество вхождений каждого ID.
        for entry_id, values in translations.items():
            used = occurrence_index.get(entry_id, 0)
            if used != len(values):
                raise RuntimeError(
                    f"{table_name}: для m_Id {entry_id} использовано "
                    f"{used} из {len(values)} переводов. Бандл не сохранён."
                )

        data["m_LocaleId"]["m_Code"] = "ru"
        obj.save_typetree(data)

        print(
            f"{table_name}: заменено {changed} из {len(rows)}; "
            f"нет совпадения: {missing}"
        )

        total_changed += changed
        total_missing += missing
        updated += 1

    if updated != len(TABLES):
        raise RuntimeError(
            f"Ожидалось {len(TABLES)} таблиц, обработано: {updated}. "
            "Бандл не сохранён."
        )

    if total_changed == 0:
        raise RuntimeError("Не найдено ни одного совпадающего ID. Бандл не сохранён.")

    print("\nСохраняю с оригинальными параметрами UnityFS...")
    result = env.file.save(packer="original")

    # Запись сначала во временный файл: существующий результат не будет
    # затронут, если сохранение не завершится.
    temp_output = OUTPUT_BUNDLE.with_suffix(OUTPUT_BUNDLE.suffix + ".tmp")
    with open(temp_output, "wb") as file:
        file.write(result)
    os.replace(temp_output, OUTPUT_BUNDLE)

    print("\nПроверяю повторную загрузку...")
    check = UnityPy.load(str(OUTPUT_BUNDLE))

    print("Объектов:", len(check.objects))
    print("Флаги UnityFS:", check.file.dataflags)
    print("Флаги блока:", check.file._block_info_flags)

    verified = 0
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
                "| пример:", rows[0]["m_Localized"] if rows else "пусто",
            )
            if data["m_LocaleId"]["m_Code"] != "ru":
                raise RuntimeError(f"Проверка не пройдена: {data.get('m_Name')} не имеет locale ru")
            verified += 1

    if verified != len(TABLES):
        raise RuntimeError(f"Проверка не пройдена: найдено таблиц {verified} из {len(TABLES)}")

    print("\nГОТОВО!")
    print("Таблиц обновлено:", updated)
    print("Всего заменено строк:", total_changed)
    print("Строк без совпадения ID:", total_missing)
    print("Файл:", OUTPUT_BUNDLE)
    print("Размер:", OUTPUT_BUNDLE.stat().st_size, "байт")
    print("\nПримечание: CRC в catalog.bin этим скриптом не изменяется.")


if __name__ == "__main__":
    main()
