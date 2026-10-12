# Pick-up point extractor + скрипты расстановки моторов

*Сделано с помощью моделей Grok.*

Видеоинструкция: https://www.youtube.com/watch?v=_y_PgrNg_jc

Порядок работы:
1. **Извлечение.** Запустите **Pick-up point extractor** и выберите проект d&b ArrayCalc (`.dbpr`) или отчёт L-Acoustics Soundvision (`.pdf`). Рядом с ним будет сохранён файл `..._hoist_picks.csv`.
2. **Расстановка.** В Vectorworks или AutoCAD запустите скрипт расстановки и выберите этот CSV. Моторы встанут в точки подвеса на нужной высоте, с подписями веса.

## Файлы релиза

| Файл | Назначение |
|---|---|
| `Pick-up_point_extractor_v1.0.exe` | Экстрактор для Windows |
| `Pick-up_point_extractor_v1.0.dmg` | Экстрактор для macOS (Apple Silicon и Intel, macOS 11+) |
| `PlaceArrayCalcHoistsV3.py` | Скрипт расстановки для Vectorworks 2026 |
| `Sound_Hoist_Class.vwx` | Стиль data tag «Sound_Hoist» для скрипта Vectorworks |
| `PlaceArrayCalcHoists.lsp` | Скрипт расстановки для AutoCAD, Windows и Mac (команды `ACHOISTS`, `ACHOISTS_CLI`) |
| `HoistPoint.dwg` | Блок мотора для AutoCAD; должен лежать рядом с `.lsp` |

---

## 1. Pick-up point extractor

**Windows:** запустите `.exe`. Если появится «Windows protected your PC» (Windows защитила ваш компьютер), нажмите **More info** (Подробнее), затем **Run anyway** (Выполнить в любом случае). Так происходит, потому что программа не подписана.

**macOS:**
1. Откройте `.dmg` и перетащите **Pick-up point extractor** в **Applications** (Программы).
2. Откройте **Terminal** и выполните:
   ```
   xattr -cr "/Applications/Pick-up point extractor.app"
   ```
3. Запустите приложение из Applications.

Команда снимает метку «загружено из интернета», из-за которой macOS пишет, что приложение невозможно открыть. Не выполняйте её на смонтированном образе диска: будут ошибки «Read-only file system».

---

## 2. Vectorworks 2026 (Windows и macOS)

### Установка стиля data tag
Скопируйте `Sound_Hoist_Class.vwx` в папку пользовательской библиотеки:

- **Windows:** `C:\Users\<вы>\AppData\Roaming\Nemetschek\Vectorworks\2026\Libraries\Annotations\Data Tag (styles)\`
- **macOS:** `~/Library/Application Support/Vectorworks/2026/Libraries/Annotations/Data Tag (styles)/`

Это пользовательские папки по умолчанию. Если вы переносили свою, посмотрите путь в **Vectorworks Preferences › User Folders** (Mac: **Vectorworks › Preferences**; Windows: **Tools › Options › Vectorworks Preferences**). Недостающие подпапки создайте сами. На macOS скрытая папка `Library` показывается в Finder сочетанием **Cmd+Shift+.**

Затем в Resource Manager щёлкните правой кнопкой по **User Libraries** и выберите **Refresh** (Обновить).

### Добавление скрипта как команды меню
1. **Tools › Plug-ins › Plug-in Manager**, вкладка **Custom Plug-ins**, кнопка **New…**, тип **Command**, имя `PlaceArrayCalcHoistsV3`.
2. Выделите его, нажмите **Edit Script…**, выберите язык **Python**, вставьте всё содержимое `PlaceArrayCalcHoistsV3.py` и нажмите OK.
3. **Tools › Workspaces › Workspaces**, выберите своё рабочее пространство и нажмите **Edit**. На вкладке **Menus** найдите команду в левом списке (в Miscellaneous или в выбранной категории) и перетащите её в меню справа.

При выходе новой версии вставьте новый код в ту же команду (**Edit Script…**). Одна лишь замена файла `.py` ничего не изменит.

### Работа
Запустите команду, выберите CSV, задайте параметры и нажмите **Place**:
- **Data tag style:** по умолчанию `Sound_Hoist`.
- **Quarter colour:** цвет класса `Hoist_Quarters`.
- **Lift tags to hoist height:** поднимать подписи на высоту мотора (включено по умолчанию).
- **Replace hoists + tags from earlier runs:** заменить моторы и подписи от прошлых запусков.
- **Single-point:** отметьте только источники, висящие на одной точке.

Если в сводке стиль помечен **NOT FOUND**, импортируйте `Sound_Hoist` через Resource Manager и запустите скрипт снова. Если в ресурсах чертежа есть старая копия `Sound_Hoist`, сначала удалите её, чтобы скрипт импортировал актуальную.

---

## 3. AutoCAD (Windows и Mac)

Проверено на AutoCAD 2025 для Windows и AutoCAD for Mac 2024/2025. Для обеих систем один и тот же скрипт.

### Установка
1. Положите `PlaceArrayCalcHoists.lsp` и `HoistPoint.dwg` в одну папку, например `C:\AutoCAD Hoists\` или на Mac `~/AutoCAD Hoists/`. На Mac держите папку **вне Desktop и Documents** (macOS ограничивает доступ программ к ним). Либо разрешите доступ: **System Settings › Privacy & Security › Files & Folders** (Системные настройки › Конфиденциальность и безопасность › Файлы и папки), включите для AutoCAD Desktop/Documents.
2. Добавьте эту папку в **Trusted Locations** (доверенные расположения, см. ниже).

### Trusted Locations (доверенные папки)
AutoCAD без вопросов загружает код только из доверенных папок. Иначе при загрузке будет предупреждение безопасности или ошибка `LOAD failed`.

- **Windows:** введите `OPTIONS` › вкладка **Files** › раскройте **Trusted Locations** › **Add**, затем **Browse** к папке › OK. Если AutoCAD предупредит, что папка не только для чтения, согласитесь. Ту же папку можно добавить и в **Support File Search Path**.
- **Mac:** **AutoCAD › Preferences › Application** › **Trusted Locations**, добавьте папку.
- **Mac, через командную строку:** введите `TRUSTEDPATHS` и путь, например `/Users/name/AutoCAD Hoists`. Добавьте в конце `/...`, чтобы включить подпапки. **Новое значение заменяет весь список**: если в нём уже что-то есть, перечислите пути через `;`.

### Загрузка
Введите `APPLOAD` (на Mac также **Tools › Load Application**), выберите `PlaceArrayCalcHoists.lsp` и нажмите **Load**. Чтобы скрипт загружался в каждом сеансе, в разделе **Startup Suite** (автозагрузка) нажмите **Contents…**, затем **Add…**. На Windows и Mac это работает одинаково.

После загрузки в командной строке появится `ACHOISTS loaded (Windows)` или `ACHOISTS loaded (Mac)`. Если этой строки нет и `ACHOISTS` не подсказывается автодополнением, проверьте доверенную папку и доступ к ней.

### Работа
В чертеже в миллиметрах введите `ACHOISTS` и выберите CSV. В диалоге задаются:
- расположение подписей (сбоку или сверху/снизу, для каждого источника);
- источники на одной точке подвеса;
- текст департамента и суффикс веса;
- цвет заливки, масштаб символа и поворот;
- удалять ли моторы от прошлых запусков.

Моторы ставятся на слой `AC_HOISTS` на своих высотах. Строки без веса (пустые или 0) пропускаются и перечисляются в сводке.

**Вариант для командной строки:** `ACHOISTS_CLI` задаёт те же вопросы в командной строке. Используйте его, если диалог работает неправильно (на Mac он запускается сам, если диалог не открылся). Важно:
- источники на одной точке: введите номера, например `3,4`;
- цвет: введите название, например `green`, или номер цвета; на неизвестное название будет повторный вопрос;
- расположение подписей одно для всех источников;
- суффикс веса с пробелом в начале вводите в кавычках, `" kg"`, иначе AutoCAD отбросит пробел.

Если в 3D/Realistic подписи выглядят угловатыми, введите `REGEN`.
