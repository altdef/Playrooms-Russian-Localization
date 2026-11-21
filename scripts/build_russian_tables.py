import argparse
import json
import os
import struct
import urllib.request
import zlib
from collections import defaultdict, deque
from pathlib import Path

import UnityPy


# Папка репозитория определяется автоматически, поэтому проект можно
# хранить не только в D:\loc\PlayRooms.
BASE_DIR = Path(__file__).resolve().parent.parent

# Всегда используем чистый исходный bundle из репозитория, а не файл из игры.
SOURCE_BUNDLE = (
    BASE_DIR
    / "bundle"
    / "localization-string-tables-italian(it)_assets_all.bundle"
)

# Результаты сборки появятся здесь. Файлы игры скрипт не перезаписывает.
OUTPUT_DIR = BASE_DIR / "build"
OUTPUT_BUNDLE = (
    OUTPUT_DIR / "localization-string-tables-italian(it)_assets_all.bundle"
)
OUTPUT_CATALOG = OUTPUT_DIR / "catalog.bin"

DEFAULT_CATALOG = Path(
    r"D:\do\Playrooms\Playrooms_Data\StreamingAssets\aa\catalog.bin"
)
CATALOG_CRC_OFFSET = 10512

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

    # ID берём из исходного итальянского JSON, чтобы не потерять точность
    # 64-битных чисел при редактировании русского JSON.
    lookup = defaultdict(deque)

    for index, (source, russian) in enumerate(zip(source_rows, russian_rows)):
        if "m_Id" not in source or "m_Localized" not in source:
            raise RuntimeError(
                f"{table_name}: некорректная исходная запись {index}. Сборка отменена."
            )
        if "m_Localized" not in russian:
            raise RuntimeError(
                f"{table_name}: нет m_Localized в русской записи {index}. Сборка отменена."
            )

        key = (source["m_Id"], source["m_Localized"])
        lookup[key].append(russian["m_Localized"])

    return lookup


def get_file_bytes(file_object):
    """Возвращает исходные байты одного файла внутри Unity AssetBundle."""
    raw = getattr(file_object, "bytes", None)
    if raw is not None:
        return raw
    return file_object.save()


def calculate_unity_crc(bundle_path):
    """
    Unity проверяет CRC-32 несжатого содержимого AssetBundle,
    а не CRC-32 всего сжатого файла на диске.
    """
    env = UnityPy.load(str(bundle_path))
    crc = 0

    # Порядок файлов сохраняется таким, каким он записан в UnityFS directory.
    for file_object in env.file.files.values():
        crc = zlib.crc32(get_file_bytes(file_object), crc)

    return crc & 0xFFFFFFFF


def write_catalog_copy(catalog_source, unity_crc):
    if not catalog_source.is_file():
        raise FileNotFoundError(
            "Не найден catalog.bin. Укажи правильный путь параметром --catalog:\n"
            f"{catalog_source}"
        )

    catalog = bytearray(catalog_source.read_bytes())
    end = CATALOG_CRC_OFFSET + 4

    if len(catalog) < end:
        raise RuntimeError(
            f"catalog.bin слишком короткий для CRC по смещению {CATALOG_CRC_OFFSET}"
        )

    # Значение записывается в little-endian, как в проверенной ручной правке.
    catalog[CATALOG_CRC_OFFSET:end] = struct.pack("<I", unity_crc)

    temp_path = OUTPUT_CATALOG.with_suffix(".bin.tmp")
    temp_path.write_bytes(catalog)
    os.replace(temp_path, OUTPUT_CATALOG)


def main():
    parser = argparse.ArgumentParser(
        description="Сборка русского перевода Playrooms из JSON на GitHub"
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG,
        help="Путь к catalog.bin игры (по умолчанию — известный путь Playrooms)",
    )
    args = parser.parse_args()

    if not SOURCE_BUNDLE.is_file():
        raise FileNotFoundError(
            "Не найден чистый исходный bundle в репозитории:\n"
            f"{SOURCE_BUNDLE}"
        )

    if not args.catalog.is_file():
        raise FileNotFoundError(
            "Не найден catalog.bin:\n"
            f"{args.catalog}\n"
            "Укажи путь: python scripts\\build_russian_tables.py --catalog "
            '"ПОЛНЫЙ_ПУТЬ_К_catalog.bin"'
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    lookups = {}
    for table_name, (source_path, russian_path) in TABLES.items():
        source_rows = download_json(source_path)
        russian_rows = download_json(russian_path)
        lookups[table_name] = build_translation_lookup(
            source_rows, russian_rows, table_name
        )

    print("\nЗагружаю чистый оригинальный итальянский bundle из репозитория...")
    env = UnityPy.load(str(SOURCE_BUNDLE))

    updated = 0
    total_changed = 0

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

        for row in rows:
            entry_id = row.get("m_Id")
            italian_text = row.get("m_Localized")
            key = (entry_id, italian_text)

            if key not in lookup or not lookup[key]:
                raise RuntimeError(
                    f"{table_name}: не найден точный перевод для m_Id "
                    f"{entry_id} и исходного текста {italian_text!r}. "
                    "Bundle не сохранён."
                )

            row["m_Localized"] = lookup[key].popleft()
            changed += 1

        locale_data = data.get("m_LocaleId")
        if not isinstance(locale_data, dict) or "m_Code" not in locale_data:
            raise RuntimeError(
                f"{table_name}: не найдено поле m_LocaleId.m_Code. "
                "Bundle не сохранён."
            )

        locale_data["m_Code"] = "ru"
        obj.save_typetree(data)

        leftovers = sum(len(values) for values in lookup.values())
        if leftovers:
            raise RuntimeError(
                f"{table_name}: осталось {leftovers} неиспользованных переводов. "
                "Bundle не сохранён."
            )

        print(
            f"{table_name}: заменено {changed} строк; locale ru; "
            f"неиспользованных записей JSON: {leftovers}"
        )

        total_changed += changed
        updated += 1

    if updated != len(TABLES):
        raise RuntimeError(
            f"Ожидалось {len(TABLES)} таблиц, обработано: {updated}. "
            "Bundle не сохранён."
        )

    if total_changed == 0:
        raise RuntimeError("Не найдено ни одного совпадения. Bundle не сохранён.")

    print("\nСохраняю bundle с оригинальными параметрами UnityFS...")
    result = env.file.save(packer="original")

    temp_bundle = OUTPUT_BUNDLE.with_suffix(OUTPUT_BUNDLE.suffix + ".tmp")
    temp_bundle.write_bytes(result)
    os.replace(temp_bundle, OUTPUT_BUNDLE)

    print("\nПовторно открываю и проверяю собранный bundle...")
    check = UnityPy.load(str(OUTPUT_BUNDLE))

    print("Объектов:", len(check.objects))
    print("Флаги UnityFS:", check.file.dataflags)
    print("Флаги блока:", check.file._block_info_flags)

    verified = 0
    for obj in check.objects:
        if obj.type.name != "MonoBehaviour":
            continue

        data = obj.read_typetree()
        if data.get("m_Name") not in TABLES:
            continue

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
        if not rows:
            raise RuntimeError(
                f"Проверка не пройдена: {data.get('m_Name')} пустая"
            )
        verified += 1

    if verified != len(TABLES):
        raise RuntimeError(
            f"Проверка не пройдена: найдено таблиц {verified} из {len(TABLES)}"
        )

    # Вычисляем именно Unity CRC по несжатым файлам внутри bundle.
    unity_crc = calculate_unity_crc(OUTPUT_BUNDLE)
    write_catalog_copy(args.catalog, unity_crc)

    print("\nСБОРКА ЗАВЕРШЕНА УСПЕШНО")
    print("Таблиц обновлено:", updated)
    print("Всего заменено строк:", total_changed)
    print("Unity CRC32:", f"{unity_crc:08X}")
    print("Bundle:", OUTPUT_BUNDLE)
    print("Размер bundle:", OUTPUT_BUNDLE.stat().st_size, "байт")
    print("Каталог (копия):", OUTPUT_CATALOG)
    print("\nФайлы игры не изменялись. Установи обе копии вручную после проверки.")


if __name__ == "__main__":
    main()
