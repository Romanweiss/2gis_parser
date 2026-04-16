# Запуск Parser2GIS через Docker

Этот файл описывает, как запускать проект в контейнерах без ручной установки Python и Chrome на хостовую машину.

## Что уже подготовлено в проекте

В репозитории уже есть:

- `Dockerfile`
- `docker-compose.yml`
- сервис `parser-2gis` для CLI и пакетного экспорта
- сервис `parser-2gis-ui` для web UI

Результаты сохраняются в локальную папку `./output`.

## Требования

Нужно, чтобы на компьютере были установлены:

- Docker Desktop или Docker Engine
- Docker Compose

Проверить можно так:

```powershell
docker --version
docker compose version
```

## Где выполнять команды

Перейдите в корень проекта:

```powershell
cd F:\Learning_projects\2gisparser\parser-2gis
```

## Сборка образа

```powershell
docker compose build
```

Эту команду обычно достаточно выполнить:

- один раз после клонирования проекта
- повторно после изменений в коде или зависимостях

## Запуск web UI

Основной сценарий для удобной работы:

```powershell
docker compose up -d parser-2gis-ui
```

После запуска откройте:

```text
http://localhost:8787
```

Порт `8787` выбран специально, чтобы не пересекаться с уже занятыми портами из других контейнеров.

### Полезные команды для UI

Посмотреть логи:

```powershell
docker compose logs -f parser-2gis-ui
```

Остановить UI:

```powershell
docker compose stop parser-2gis-ui
```

Полностью убрать контейнер UI:

```powershell
docker compose rm -f parser-2gis-ui
```

## Запуск обычного CLI-парсинга

Если нужно спарсить один URL без UI:

```powershell
docker compose run --rm parser-2gis `
  -i "https://2gis.ru/moscow/search/Аптеки" `
  -o /data/output.csv `
  -f csv `
  --parser.max-records 10 `
  --chrome.headless yes
```

Файл появится в:

```text
F:\Learning_projects\2gisparser\parser-2gis\output
```

## Пакетный экспорт по рубрикам

Для пакетного запуска используется helper `parser-2gis-bulk`.

Пример:

```powershell
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis `
  --non-interactive `
  --city-code moscow `
  --city-name Москва `
  --include-groups 2,5,9,10,14 `
  --output-path /data/moscow_bulk.xlsx `
  --parser-max-records 100
```

### Показать верхнеуровневые группы рубрик

```powershell
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis `
  --list-groups `
  --non-interactive
```

### Сохранить профиль выбора рубрик

```powershell
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis `
  --city-code moscow `
  --city-name Москва `
  --save-profile-path /data/profiles/moscow_custom.json `
  --dry-run
```

### Повторный запуск по сохранённому профилю

```powershell
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis `
  --profile-path /data/profiles/moscow_custom.json `
  --non-interactive `
  --output-path /data/moscow_custom.xlsx
```

## Где лежат результаты

Все выходные файлы сохраняются в:

- `output/*.xlsx`
- `output/*.csv`
- `output/*.json`
- `output/profiles/*.json`

## Что делать, если UI не открывается

1. Проверьте, что контейнер запущен:

```powershell
docker compose ps
```

2. Проверьте логи:

```powershell
docker compose logs -f parser-2gis-ui
```

3. Убедитесь, что порт `8787` не занят другим приложением.

4. Если меняли код, пересоберите образ:

```powershell
docker compose build
docker compose up -d parser-2gis-ui
```

## Что делать, если не создаётся выходной файл

Проверьте:

- есть ли логи ошибок у контейнера
- не открыт ли итоговый `.xlsx` в Excel во время перезаписи
- достаточно ли узкий набор рубрик выбран
- не слишком ли большой объём данных вы пытаетесь собрать за один проход

Практически всегда лучше сначала делать тестовый запуск на маленьком объёме.

## Рекомендуемый порядок работы

1. `docker compose build`
2. `docker compose up -d parser-2gis-ui`
3. открыть `http://localhost:8787`
4. выбрать страны, города и рубрики
5. сохранить профиль
6. сделать тестовый экспорт
7. после проверки запускать широкий экспорт
