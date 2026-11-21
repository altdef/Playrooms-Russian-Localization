import json
import os
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

import UnityPy


BASE_DIR = Path(r"D:\loc\PlayRooms")
SOURCE_BUNDLE = Path(
    r"D:\do\Playrooms\Playrooms_Data\StreamingAssets\aa"
    r"\StandaloneWindows64\localization-string-tables-italian(it)_assets_all.bundle"
)
OUTPUT_DIR = BASE_DIR / "bundles"
OUTPUT_BUNDLE = OUTPUT_DIR / "localization-string-tables-russian-preserved.bundle"

GITHUB_RAW = (
    "https://raw.githubusercontent.com/"
    "altdef/Playrooms-Russian-Localization/main/"
)

TABLES = {
    "Mails_it": ("Original/Mails_it.json", "Russian/Mails_ru.json"),
    "General_it": ("Original/General_it.json", "Russian/General_ru.json"),
    "Popups_it": ("Original/Popups_it.json", "Russian/Popups_ru.json"),
    "Balli_it": ("Original/Balli_it.json", "Russian/Balli_ru.json"),
    "Skills_it": ("Original/Skills_it.json", "Russian/Skills_ru.json"),
    "Items_it": ("Original/Items_it.json", "Russian/Items_ru.json"),
}


def download_json(repo_path):
    url = GITHUB_RAW + repo_path
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Playrooms-Russian-Localization-Builder"},
    )
    print(f"Загружаю с GitHub: {repo_path}")

    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    data = json.loads(raw.decode("utf-8-sig"))
    table = data.get("m_TableData", {})
    rows = table.get("Array", []) if isinstance(table, dict) else table

    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"В {repo_path} не найдены записи m_TableData.Array")

    for row in rows:
        if "m_Id" not in row or "m_Localized" not in row:
            raise RuntimeError(
                f"Некорректная запись в {repo_path}: отсутствует m_Id или m_Localized"
            )

    print(f"  Получено записей: {len(rows)}")
    return rows


def build_translation_lookup(source_rows, russian_rows, table_name):
    if len(source_rows) != len(russian_rows):
        raise RuntimeError(
            f"{table_name}: количество исходных и русских записей различается "
            f"({len(source_rows)} и {len(russian_rows)}). Сборка отменена."
        )

    # Сопоставляем пары по позиции в экспортированных таблицах.
    # Один m_Id может законно повторяться для разных исходных строк.
    lookup = defaultdict(deque)

    for index, (source, russian) in enumerate(zip(source_rows, russian_rows)):
        if source["m_Id"] != russian["m_Id"]:
            raise RuntimeError(
                f"{table_name}: m_Id не совпадает в записи {index}: "
                f"{source['m_Id']} != {russian['m_Id']}. Сборка отменена."
            )

        lookup[(source["m_Id"], source["m_Localized"])].append(
            russian["m_Localized"]
        )

    return lookup


def main():
    if not SOURCE_BUNDLE.is_file():
        raise FileNotFoundError(f"Не найден исходный Unity-бандл:\n{SOURCE_BUNDLE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lookups = {}
    for table_name, (source_path, russian_path) in TABLES.items():
        source_rows = download_json(source_path)
        russian_rows = download_json(russian_path)
        lookups[table_name] = build_translation_lookup(
            source_rows, russian_rows, table_name
        )

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

        lookup = lookups[table_name]
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
            italian_text = row.get("m_Localized")
            key = (entry_id, italian_text)

            if key not in lookup or not lookup[key]:
                raise RuntimeError(
                    f"{table_name}: не найден точный перевод для m_Id "
                    f"{entry_id} и исходного текста {italian_text!r}. "
                    "Бандл не сохранён."
                )

            row["m_Localized"] = lookup[key].popleft()
            changed += 1

        leftovers = sum(len(values) for values in lookup.values())
        print(
            f"{table_name}: заменено {changed} строк; "
            f"неиспользованных записей JSON: {leftovers}"
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
        raise RuntimeError("Не найдено ни одного совпадения. Бандл не сохранён.")

    print("\nСохраняю с оригинальными параметрами UnityFS...")
    result = env.file.save(packer="original")

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
            locale_code = data["m_LocaleId"]["m_Code"]

            print(
                data["m_Name"],
                "| код:", locale_code,
                "| строк:", len(rows),
                "| пример:", rows[0]["m_Localized"] if rows else "пусто",
            )

            if locale_code != "ru":
                raise RuntimeError(
                    f"Проверка не пройдена: {data.get('m_Name')} не имеет locale ru"
                )
            verified += 1

    if verified != len(TABLES):
        raise RuntimeError(
            f"Проверка не пройдена: найдено таблиц {verified} из {len(TABLES)}"
        )

    print("\nГОТОВО!")
    print("Таблиц обновлено:", updated)
    print("Всего заменено строк:", total_changed)
    print("Файл:", OUTPUT_BUNDLE)
    print("Размер:", OUTPUT_BUNDLE.stat().st_size, "байт")
    print("\nПримечание: CRC в catalog.bin этим скриптом не изменяется.")


if __name__ == "__main__":
    main()
