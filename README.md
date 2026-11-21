# Playrooms Russian Localization

## Редактирование перевода

Меняй тексты в папке `Russian`:
- `General_ru.json`
- `Items_ru.json`
- `Mails_ru.json`
- `Popups_ru.json`
- `Balli_ru.json`
- `Skills_ru.json`

Не меняй `m_Id`, порядок записей и структуру JSON. Редактируй только `m_Localized`.

## Сборка в Windows

Нужны Python 3.11 и доступ в интернет.

Один раз установи зависимость из корня репозитория:

```powershell
python -m pip install -r requirements.txt
```

Есть два независимых сборщика. Оба берут чистый исходный bundle из папки `bundle`, копию `catalog.bin` — из установленной игры (или из пути, указанного через `--catalog`), а результат сохраняют в `build`. Файлы игры автоматически не изменяются.

### Вариант 1 — локальные JSON из соседних папок проекта

Используй, если JSON находятся в папках `Original` и `Russian` рядом с `scripts`:

```powershell
python scripts\\build_russian_tables.py
```

Этот вариант не скачивает JSON из GitHub.

### Вариант 2 — скачивать JSON с GitHub при каждой сборке

```powershell
python scripts\\build_russian_tables_github.py
```

Этот вариант получает актуальные JSON из ветки `main` и не требует локальных папок `Original` и `Russian` для чтения перевода.

Оба скрипта создают два файла в папке `build`:

- `localization-string-tables-italian(it)_assets_all.bundle`
- `catalog.bin`

CRC вычисляется по несжатому содержимому AssetBundle, как ожидает Unity. Скрипт обновляет CRC в копии каталога по смещению 10512 (little-endian). Файлы в установленной игре скрипт не изменяет.

Если игра установлена в другом месте, укажи путь к каталогу явно:

```powershell
python scripts\build_russian_tables.py --catalog "D:\путь\к\Playrooms_Data\StreamingAssets\aa\catalog.bin"
```

## Установка

1. Закрой игру.
2. Сохрани резервные копии установленных bundle и catalog.bin.
3. Скопируй оба файла из папки `build` в соответствующие места игры:
   - bundle — в `StreamingAssets\aa\StandaloneWindows64\`, с именем `localization-string-tables-italian(it)_assets_all.bundle`;
   - catalog — в `StreamingAssets\aa\catalog.bin`.
4. Запусти игру и проверь лог, если загрузка не удалась.

Для первого контрольного запуска с текущими, ещё не изменёнными JSON ожидаемый Unity CRC — `6DA9F4B4`. После правок переводов CRC будет меняться — это нормально.

## Важно

- Не редактируй исходный bundle в папке `bundle`.
- Не используй установленный игровой bundle как исходник для следующей сборки.
- Сборщик создаёт отдельные выходные файлы и не перезаписывает файлы игры.
- Сохраняй `m_Id` и плейсхолдеры вроде `{0}`, `%%` без изменений.
