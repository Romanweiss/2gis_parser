<p align="center">
  <img alt="Parser2GIS" width="128" src="https://user-images.githubusercontent.com/20641837/174094285-6e32eb04-7feb-4a60-bddf-5a0fde5dba4d.png"/>
</p>
<h1 align="center">Parser2GIS</h1>

`Parser2GIS` — парсер данных из 2GIS с поддержкой CLI, пакетного экспорта по рубрикам и web UI для выбора стран, городов и конечных рубрик.

## Происхождение проекта

Этот репозиторий основан на оригинальном проекте [`interlark/parser-2gis`](https://github.com/interlark/parser-2gis).

В этой версии:

- сохранён исходный `LICENSE`
- история доработок ведётся поверх исходной кодовой базы
- upstream-репозиторий поддерживается отдельно от рабочего репозитория с пользовательскими изменениями

## Что добавлено в этой версии

Поверх исходного проекта в этом репозитории добавлены и доработаны:

- запуск через Docker и `docker compose`
- отдельный web UI для выбора стран, городов и листовых рубрик
- пакетный экспорт через `parser-2gis-bulk`
- сохранение и повторное использование профилей выбора
- экспорт в `xlsx`, `csv`, `json`
- готовые пресеты рубрик для типовых сценариев
- расширенный кастомный каталог городов, включая города Московской области и Якутии
- отдельная инструкция по Docker в [docs/DOCKER.md](docs/DOCKER.md)

## Что есть в проекте

- CLI-режим для парсинга отдельных URL
- пакетный экспорт `parser-2gis-bulk`
- web UI для выбора стран, городов и рубрик
- сохранение профилей экспорта
- экспорт в `xlsx`, `csv`, `json`
- запуск через Docker

## Быстрый старт через Docker

Из корня проекта выполните:

```bash
docker compose build
docker compose up -d parser-2gis-ui
```

После этого откройте:

```text
http://localhost:8787
```

Результаты будут сохраняться в папку `./output`.

Полная инструкция по Docker находится в [docs/DOCKER.md](docs/DOCKER.md).

## Сервисы Docker

В `docker-compose.yml` настроены два сервиса:

- `parser-2gis` — основной контейнер для CLI и пакетного экспорта
- `parser-2gis-ui` — web UI на порту `8787`

Порт `8787` выбран специально, чтобы не пересекаться с уже занятыми портами других контейнеров.

## Примеры запуска

### 1. Web UI

```bash
docker compose up -d parser-2gis-ui
```

### 2. Обычный CLI-парсинг одного URL

```bash
docker compose run --rm parser-2gis \
  -i "https://2gis.ru/moscow/search/Аптеки" \
  -o /data/output.csv \
  -f csv \
  --parser.max-records 10 \
  --chrome.headless yes
```

### 3. Пакетный экспорт по рубрикам

```bash
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis \
  --non-interactive \
  --city-code moscow \
  --city-name Москва \
  --include-groups 2,5,9,10,14 \
  --output-path /data/moscow_bulk.xlsx \
  --parser-max-records 100
```

### 4. Показать группы рубрик

```bash
docker compose run --rm --entrypoint parser-2gis-bulk parser-2gis \
  --list-groups \
  --non-interactive
```

## Web UI

Через web UI можно:

- выбрать страны
- выбрать города
- выбрать группы рубрик
- отметить конечные листовые рубрики
- сохранить профиль
- запустить экспорт
- скачать готовый файл

Для запуска:

```bash
docker compose up -d parser-2gis-ui
```

Логи UI:

```bash
docker compose logs -f parser-2gis-ui
```

Остановка UI:

```bash
docker compose stop parser-2gis-ui
```

## Пакетный экспорт

Команда `parser-2gis-bulk` помогает собирать данные по большому набору рубрик в один файл.

Поддерживается:

- выбор городов
- выбор групп рубрик
- выбор конечных рубрик
- фильтрация по названию рубрики
- сохранение профилей в `output/profiles`

## Структура результатов

Файлы сохраняются в:

- `output/*.xlsx`
- `output/*.csv`
- `output/*.json`
- `output/profiles/*.json`

## Работа с репозиторием

Рекомендуемая схема для этого репозитория:

- `origin` — исходный upstream `interlark/parser-2gis`
- `romanweiss` — основной рабочий репозиторий с вашими изменениями

Текущая разработка ведётся в вашем репозитории, при этом upstream сохраняется отдельно для сравнения, обновлений и возможных PR.

## Документация

- Docker: [docs/DOCKER.md](docs/DOCKER.md)
- Wiki оригинального проекта: https://github.com/interlark/parser-2gis/wiki

## Поддержка проекта

<a href="https://yoomoney.ru/to/4100118362270186" target="_blank">
  <img alt="Yoomoney Donate" src="https://github.com/interlark/parser-2gis/assets/20641837/e875e948-0d69-4ed5-804c-8a1736ab0c9d" width="150">
</a>
