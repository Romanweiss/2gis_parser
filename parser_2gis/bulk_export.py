from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from .cli import cli_app
from .config import Configuration
from .paths import data_path

RUSSIAN_DEFAULT_DOMAIN = 'ru'
DEFAULT_COUNTRY_CODE = 'ru'
DEFAULT_CITY_CODE = 'podolsk'
DEFAULT_CITY_NAME = 'Подольск'
DEFAULT_EXCLUDED_GROUP_IDS = {'1', '5419', '-1'}
DEFAULT_PROFILE_VERSION = 1
PAGE_SIZE = 20


def load_custom_cities() -> list[dict[str, Any]]:
    custom_cities_path = data_path() / 'custom_cities.json'
    if not custom_cities_path.exists():
        return []

    with open(custom_cities_path, 'r', encoding='utf-8') as f:
        custom_cities = json.load(f)

    if not isinstance(custom_cities, list):
        raise SystemExit(f'Файл {custom_cities_path} должен содержать список городов.')

    return custom_cities


def load_rubrics(*, is_russian: bool | None = True) -> dict[str, dict[str, Any]]:
    """Load and filter rubric tree."""
    rubric_path = data_path() / 'rubrics.json'
    with open(rubric_path, 'r', encoding='utf-8') as f:
        rubrics = json.load(f)

    if is_russian is True:
        rubrics = {k: v for k, v in rubrics.items() if v.get('isRussian', True)}
    elif is_russian is False:
        rubrics = {k: v for k, v in rubrics.items() if v.get('isNonRussian', True)}

    for node in rubrics.values():
        node['children'] = [child for child in node['children'] if child in rubrics]

    return rubrics


def load_cities() -> list[dict[str, Any]]:
    cities_path = data_path() / 'cities.json'
    with open(cities_path, 'r', encoding='utf-8') as f:
        cities = json.load(f)

    merged_cities: dict[str, dict[str, Any]] = {
        city['code']: dict(city)
        for city in cities
    }
    for city in load_custom_cities():
        merged_cities[city['code']] = dict(city)

    return list(merged_cities.values())


def load_profile(profile_path: str | None) -> dict[str, Any] | None:
    if not profile_path:
        return None

    path = Path(profile_path)
    with open(path, 'r', encoding='utf-8') as f:
        profile = json.load(f)

    if not isinstance(profile, dict):
        raise SystemExit(f'Профиль {path} имеет неверный формат.')

    return profile


def save_profile(profile_path: str, payload: dict[str, Any]) -> None:
    path = Path(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def url_query_encode(value: str) -> str:
    """Encode query the same way as GUI URL generator."""
    encoded_characters: list[str] = []
    for char in value:
        char_ord = ord(char.lower())
        if 1072 <= char_ord <= 1103 or char_ord in (1105, 32):
            encoded_characters.append(char)
        else:
            encoded_characters.append(quote(char, safe=''))
    return ''.join(encoded_characters)


def top_level_group_ids(rubrics: dict[str, dict[str, Any]]) -> list[str]:
    return [code for code, node in rubrics.items() if node['parentCode'] == '0']


def iter_leaf_rubrics(rubrics: dict[str, dict[str, Any]],
                      group_ids: Iterable[str]) -> Iterable[dict[str, Any]]:
    """Yield leaf rubrics for selected group ids."""
    def walk(node_id: str) -> Iterable[dict[str, Any]]:
        node = rubrics[node_id]
        if not node['children']:
            yield node
            return
        for child_id in node['children']:
            yield from walk(child_id)

    seen_ids: set[str] = set()
    for group_id in group_ids:
        if group_id not in rubrics:
            continue
        for node in walk(group_id):
            node_id = node['code']
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            yield node


def leaf_count(rubrics: dict[str, dict[str, Any]], group_id: str) -> int:
    return sum(1 for _ in iter_leaf_rubrics(rubrics, [group_id]))


def default_group_ids(rubrics: dict[str, dict[str, Any]]) -> list[str]:
    return [group_id for group_id in top_level_group_ids(rubrics)
            if group_id not in DEFAULT_EXCLUDED_GROUP_IDS]


def parse_csv_arguments(values: list[str] | None) -> list[str]:
    if not values:
        return []

    result: list[str] = []
    for value in values:
        result.extend([item.strip() for item in value.split(',') if item.strip()])
    return result


def build_search_url(*, city: dict[str, Any], rubric: dict[str, Any]) -> str:
    search_domain = city.get('search_domain', city['domain'])
    search_code = city.get('search_code', city['code'])
    query_parts = [
        str(city.get('query_prefix', '')).strip(),
        rubric['label'],
        str(city.get('query_suffix', '')).strip(),
    ]
    search_query = ' '.join(part for part in query_parts if part)
    query = url_query_encode(search_query)
    return f'https://2gis.{search_domain}/{search_code}/search/{query}/rubricId/{rubric["code"]}/filters/sort=name'


def rubric_label(node: dict[str, Any]) -> str:
    return node.get('label') or f'<rubric {node["code"]}>'


def city_label(city: dict[str, Any]) -> str:
    return city.get('name') or city.get('code') or '<city>'


def print_group_table(rubrics: dict[str, dict[str, Any]]) -> None:
    print('Доступные верхнеуровневые блоки:')
    for group_id in top_level_group_ids(rubrics):
        node = rubrics[group_id]
        print(f'  {group_id:>5} | {rubric_label(node)} | листовых рубрик: {leaf_count(rubrics, group_id)}')


def parse_index_selection(raw_value: str, max_value: int) -> list[int]:
    selected_indexes: set[int] = set()
    for chunk in [item.strip() for item in raw_value.split(',') if item.strip()]:
        if '-' in chunk:
            left, right = chunk.split('-', 1)
            if not left.isdigit() or not right.isdigit():
                raise ValueError(f'Неверный диапазон: {chunk}')
            start = int(left)
            end = int(right)
            if start > end:
                start, end = end, start
            selected_indexes.update(range(start, end + 1))
        else:
            if not chunk.isdigit():
                raise ValueError(f'Неверный номер: {chunk}')
            selected_indexes.add(int(chunk))

    invalid = [index for index in selected_indexes if index < 1 or index > max_value]
    if invalid:
        raise ValueError(f'Номера вне диапазона 1..{max_value}: {", ".join(map(str, sorted(invalid)))}')

    return sorted(selected_indexes)


def print_leaf_page(filtered_leaf_rubrics: list[dict[str, Any]],
                    selected_ids: set[str],
                    page: int) -> list[dict[str, Any]]:
    total = len(filtered_leaf_rubrics)
    if total == 0:
        print('По текущему фильтру ничего не найдено.')
        return []

    total_pages = max((total - 1) // PAGE_SIZE + 1, 1)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_items = filtered_leaf_rubrics[start:end]

    print()
    print(f'Страница {page + 1}/{total_pages}. Найдено рубрик: {total}. Выбрано: {len(selected_ids)}.')
    for offset, rubric in enumerate(page_items, start=1):
        mark = '*' if rubric['code'] in selected_ids else ' '
        print(f'  [{mark}] {offset:>2}. {rubric_label(rubric)} ({rubric["code"]})')

    return page_items


def print_leaf_selection_help() -> None:
    print('Команды выбора рубрик:')
    print('  s <текст>     - поиск по названию рубрик')
    print('  reset         - сбросить поиск')
    print('  n / p         - следующая / предыдущая страница')
    print('  a <1,2,5-8>   - добавить рубрики с текущей страницы в выбор')
    print('  r <1,2,5-8>   - убрать рубрики с текущей страницы из выбора')
    print('  aa            - добавить все рубрики из текущего фильтра')
    print('  rr            - убрать все рубрики из текущего фильтра')
    print('  l             - показать выбранные рубрики')
    print('  c             - очистить выбор')
    print('  done          - завершить выбор')
    print('  help          - показать эту справку')


def print_selected_rubrics(selected_rubrics: list[dict[str, Any]]) -> None:
    print(f'Выбрано конечных рубрик: {len(selected_rubrics)}')
    for rubric in selected_rubrics[:50]:
        print(f'  {rubric["code"]:>6} | {rubric_label(rubric)}')
    if len(selected_rubrics) > 50:
        print(f'  ... и ещё {len(selected_rubrics) - 50}')


def print_selected_cities(selected_cities: list[dict[str, Any]]) -> None:
    print(f'Выбрано городов: {len(selected_cities)}')
    for city in selected_cities[:30]:
        print(f'  {city_label(city)} ({city["code"]}, {city["domain"]})')
    if len(selected_cities) > 30:
        print(f'  ... и ещё {len(selected_cities) - 30}')


def safe_input(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError as e:
        raise SystemExit('Интерактивный ввод был прерван.') from e


def choose_group_ids_interactively(rubrics: dict[str, dict[str, Any]],
                                   default_ids: list[str]) -> list[str]:
    print_group_table(rubrics)
    default_value = ','.join(default_ids)
    print()
    print('Нажмите Enter, чтобы взять рекомендованный широкий набор для бизнеса и услуг.')
    raw_value = safe_input(f'Введите id блоков через запятую [{default_value}]: ').strip()
    if not raw_value:
        return default_ids

    selected = [item.strip() for item in raw_value.split(',') if item.strip()]
    unknown = [item for item in selected if item not in rubrics]
    if unknown:
        raise SystemExit(f'Неизвестные id блоков: {", ".join(unknown)}')
    return selected


def choose_leaf_rubrics_interactively(leaf_rubrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not leaf_rubrics:
        return []

    rubric_by_id = {rubric['code']: rubric for rubric in leaf_rubrics}
    selected_ids: set[str] = set()
    search_query = ''
    page = 0

    print()
    print('Переходим к выбору конечных рубрик.')
    print('Можно искать по названию и собирать точный набор. Если ничего не выбрать,')
    print('по команде done helper предложит взять все рубрики текущего фильтра.')
    print_leaf_selection_help()

    while True:
        filtered = [
            rubric for rubric in leaf_rubrics
            if search_query.lower() in rubric_label(rubric).lower()
        ]
        page_items = print_leaf_page(filtered, selected_ids, page)
        raw_command = safe_input('rubrics> ').strip()

        if not raw_command:
            continue

        if raw_command == 'help':
            print_leaf_selection_help()
            continue

        if raw_command == 'reset':
            search_query = ''
            page = 0
            continue

        if raw_command == 'n':
            if filtered:
                page = min(page + 1, max((len(filtered) - 1) // PAGE_SIZE, 0))
            continue

        if raw_command == 'p':
            page = max(page - 1, 0)
            continue

        if raw_command == 'aa':
            selected_ids.update(rubric['code'] for rubric in filtered)
            continue

        if raw_command == 'rr':
            selected_ids.difference_update(rubric['code'] for rubric in filtered)
            continue

        if raw_command == 'l':
            print_selected_rubrics(sorted(
                (rubric_by_id[rubric_id] for rubric_id in selected_ids),
                key=lambda rubric: rubric_label(rubric)
            ))
            continue

        if raw_command == 'c':
            selected_ids.clear()
            continue

        if raw_command == 'done':
            if selected_ids:
                return sorted(
                    (rubric_by_id[rubric_id] for rubric_id in selected_ids),
                    key=lambda rubric: rubric_label(rubric)
                )

            answer = safe_input('Ничего не выбрано. Взять все рубрики текущего фильтра? [y/N]: ').strip().lower()
            if answer in ('y', 'yes', 'д', 'да'):
                return filtered
            continue

        if raw_command.startswith('s '):
            search_query = raw_command[2:].strip()
            page = 0
            continue

        if raw_command.startswith('a ') or raw_command.startswith('r '):
            if not page_items:
                print('На текущей странице нет рубрик для выбора.')
                continue

            try:
                indexes = parse_index_selection(raw_command[2:].strip(), len(page_items))
            except ValueError as e:
                print(e)
                continue

            target_ids = {page_items[index - 1]['code'] for index in indexes}
            if raw_command.startswith('a '):
                selected_ids.update(target_ids)
            else:
                selected_ids.difference_update(target_ids)
            continue

        print('Неизвестная команда. Введите help для списка доступных команд.')


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='parser-2gis-bulk',
        description='Пакетный экспорт 2GIS по листовым рубрикам в один файл'
    )
    parser.add_argument('--city-code', default=None,
                        help='Код одного города в URL 2GIS, например podolsk')
    parser.add_argument('--city-name', default=None,
                        help='Человекочитаемое имя одного города для логов')
    parser.add_argument('--domain', default=None,
                        help='Домен 2GIS для одного города, например ru')
    parser.add_argument('--city-codes', action='append',
                        help='Список кодов городов через запятую для пакетного запуска')
    parser.add_argument('--country-codes', action='append',
                        help='Ограничить выбор городов указанными кодами стран, например ru,kz')
    parser.add_argument('--output-path', default=None,
                        help='Итоговый путь результата')
    parser.add_argument('--format', choices=['csv', 'xlsx', 'json'], default='xlsx',
                        help='Формат результирующего файла')
    parser.add_argument('--profile-path', default=None,
                        help='Путь к профилю выбора рубрик в формате JSON')
    parser.add_argument('--save-profile-path', default=None,
                        help='Сохранить итоговый выбор рубрик в JSON-профиль')
    parser.add_argument('--include-groups', action='append',
                        help='Список id верхнеуровневых блоков через запятую')
    parser.add_argument('--exclude-groups', action='append',
                        help='Список id блоков для исключения через запятую')
    parser.add_argument('--rubric-ids', action='append',
                        help='Явно задать конечные rubricId через запятую')
    parser.add_argument('--include-rubric-query', action='append',
                        help='Оставить только листовые рубрики, чьи названия содержат указанные фрагменты')
    parser.add_argument('--exclude-rubric-query', action='append',
                        help='Исключить листовые рубрики, чьи названия содержат указанные фрагменты')
    parser.add_argument('--all-groups', action='store_true',
                        help='Использовать все верхнеуровневые блоки, включая власть и экстренные службы')
    parser.add_argument('--list-groups', action='store_true',
                        help='Показать доступные верхнеуровневые блоки и выйти')
    parser.add_argument('--list-selected-rubrics', action='store_true',
                        help='Показать итоговый список выбранных конечных рубрик')
    parser.add_argument('--list-selected-cities', action='store_true',
                        help='Показать итоговый список выбранных городов')
    parser.add_argument('--use-all-leaf-rubrics', action='store_true',
                        help='Не запускать интерактивный выбор листовых рубрик, взять все после фильтров')
    parser.add_argument('--dry-run', action='store_true',
                        help='Только показать выбранные рубрики и URL, не запускать экспорт')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Не задавать вопросов, использовать переданные параметры и пресеты')
    parser.add_argument('--limit-rubrics', type=int, default=None,
                        help='Ограничить количество листовых рубрик для тестового запуска')
    parser.add_argument('--parser-max-records', type=int, default=None,
                        help='Лимит записей на одну листовую рубрику')
    parser.add_argument('--show-browser', action='store_true',
                        help='Запускать браузер не в headless-режиме')
    parser.add_argument('--keep-duplicates', action='store_true',
                        help='Не удалять дубли на финальном этапе')
    parser.add_argument('--write-urls-path', default=None,
                        help='Сохранить сгенерированные URL в текстовый файл')
    return parser


def resolve_runtime_metadata(args: argparse.Namespace,
                             profile: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    city_code = args.city_code or (profile or {}).get('city_code')
    domain = args.domain or (profile or {}).get('domain')
    city_name = args.city_name or (profile or {}).get('city_name')
    return city_code, domain, city_name


def resolve_selected_cities(args: argparse.Namespace,
                            profile: dict[str, Any] | None,
                            cities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if profile and profile.get('cities'):
        return [dict(city) for city in profile['cities']]

    city_codes = parse_csv_arguments(args.city_codes)
    if not city_codes:
        city_code, domain, city_name = resolve_runtime_metadata(args, profile)
        if city_code:
            city_codes = [city_code]
        else:
            city_codes = [DEFAULT_CITY_CODE]
            if domain is None:
                domain = RUSSIAN_DEFAULT_DOMAIN
            if city_name is None:
                city_name = DEFAULT_CITY_NAME

        matched = [city for city in cities if city['code'] == city_codes[0]]
        if matched:
            return matched[:1]

        return [{
            'name': city_name or DEFAULT_CITY_NAME,
            'code': city_codes[0],
            'domain': domain or RUSSIAN_DEFAULT_DOMAIN,
            'country_code': DEFAULT_COUNTRY_CODE,
        }]

    country_codes = set(parse_csv_arguments(args.country_codes))
    selected_cities = [
        city for city in cities
        if city['code'] in city_codes and (not country_codes or city['country_code'] in country_codes)
    ]

    missing_codes = sorted(set(city_codes) - {city['code'] for city in selected_cities})
    if missing_codes:
        raise SystemExit(f'Не найдены города с кодами: {", ".join(missing_codes)}')

    return selected_cities


def resolve_selected_group_ids(args: argparse.Namespace,
                               rubrics: dict[str, dict[str, Any]],
                               profile: dict[str, Any] | None) -> list[str]:
    top_groups = top_level_group_ids(rubrics)
    if args.all_groups:
        selected_ids = top_groups
    else:
        selected_ids = default_group_ids(rubrics)

    if profile and profile.get('group_ids'):
        selected_ids = [str(value) for value in profile['group_ids']]

    included = parse_csv_arguments(args.include_groups)
    if included:
        selected_ids = included
    elif not args.non_interactive and not profile:
        selected_ids = choose_group_ids_interactively(rubrics, selected_ids)

    excluded = set(parse_csv_arguments(args.exclude_groups))
    selected_ids = [group_id for group_id in selected_ids if group_id not in excluded]

    unknown = [group_id for group_id in selected_ids if group_id not in rubrics]
    if unknown:
        raise SystemExit(f'Неизвестные id блоков: {", ".join(unknown)}')

    return selected_ids


def resolve_output_path(args: argparse.Namespace, selected_cities: list[dict[str, Any]]) -> str:
    if args.output_path:
        return args.output_path
    if len(selected_cities) == 1:
        return f'/data/{selected_cities[0]["code"]}_rubrics.{args.format}'
    return f'/data/multi_city_rubrics.{args.format}'


def filter_leaf_rubrics(leaf_rubrics: list[dict[str, Any]],
                        include_queries: list[str] | None,
                        exclude_queries: list[str] | None) -> list[dict[str, Any]]:
    include_parts = [value.lower() for value in parse_csv_arguments(include_queries)]
    exclude_parts = [value.lower() for value in parse_csv_arguments(exclude_queries)]

    filtered = leaf_rubrics
    if include_parts:
        filtered = [
            rubric for rubric in filtered
            if any(part in rubric_label(rubric).lower() for part in include_parts)
        ]

    if exclude_parts:
        filtered = [
            rubric for rubric in filtered
            if not any(part in rubric_label(rubric).lower() for part in exclude_parts)
        ]

    return filtered


def resolve_selected_leaf_rubrics(args: argparse.Namespace,
                                  rubrics: dict[str, dict[str, Any]],
                                  selected_group_ids: list[str],
                                  profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    leaf_rubrics = list(iter_leaf_rubrics(rubrics, selected_group_ids))
    leaf_rubrics = filter_leaf_rubrics(
        leaf_rubrics,
        include_queries=args.include_rubric_query,
        exclude_queries=args.exclude_rubric_query,
    )

    rubric_by_id = {rubric['code']: rubric for rubric in leaf_rubrics}

    selected_rubric_ids = parse_csv_arguments(args.rubric_ids)
    if not selected_rubric_ids and profile and profile.get('rubric_ids'):
        selected_rubric_ids = [str(value) for value in profile['rubric_ids']]

    if selected_rubric_ids:
        missing_rubrics = [rubric_id for rubric_id in selected_rubric_ids if rubric_id not in rubric_by_id]
        if missing_rubrics:
            raise SystemExit(
                'Некоторые rubricId отсутствуют в выбранных блоках или были отфильтрованы: '
                + ', '.join(missing_rubrics)
            )
        selected_leaf_rubrics = [rubric_by_id[rubric_id] for rubric_id in selected_rubric_ids]
    elif args.non_interactive or args.use_all_leaf_rubrics:
        selected_leaf_rubrics = leaf_rubrics
    else:
        selected_leaf_rubrics = choose_leaf_rubrics_interactively(
            sorted(leaf_rubrics, key=lambda rubric: rubric_label(rubric))
        )

    selected_leaf_rubrics = sorted(selected_leaf_rubrics, key=lambda rubric: rubric_label(rubric))

    if args.limit_rubrics is not None:
        selected_leaf_rubrics = selected_leaf_rubrics[:args.limit_rubrics]

    return selected_leaf_rubrics


def build_profile_payload(*, selected_cities: list[dict[str, Any]], selected_group_ids: list[str],
                          selected_leaf_rubrics: list[dict[str, Any]]) -> dict[str, Any]:
    first_city = selected_cities[0] if selected_cities else {
        'code': DEFAULT_CITY_CODE,
        'name': DEFAULT_CITY_NAME,
        'domain': RUSSIAN_DEFAULT_DOMAIN,
    }
    return {
        'version': DEFAULT_PROFILE_VERSION,
        'city_code': first_city['code'],
        'city_name': first_city['name'],
        'domain': first_city['domain'],
        'cities': selected_cities,
        'group_ids': selected_group_ids,
        'rubric_ids': [rubric['code'] for rubric in selected_leaf_rubrics],
        'rubrics': [
            {'code': rubric['code'], 'label': rubric_label(rubric)}
            for rubric in selected_leaf_rubrics
        ],
    }


def build_urls(selected_cities: list[dict[str, Any]],
               selected_leaf_rubrics: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for city in selected_cities:
        for rubric in selected_leaf_rubrics:
            urls.append(build_search_url(city=city, rubric=rubric))
    return urls


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    profile = load_profile(args.profile_path)
    cities = load_cities()
    selected_cities = resolve_selected_cities(args, profile, cities)
    all_ru = all(city['country_code'] == 'ru' for city in selected_cities)
    all_non_ru = all(city['country_code'] != 'ru' for city in selected_cities)
    if all_ru:
        rubrics = load_rubrics(is_russian=True)
    elif all_non_ru:
        rubrics = load_rubrics(is_russian=False)
    else:
        rubrics = load_rubrics(is_russian=None)

    if args.list_groups:
        print_group_table(rubrics)
        return

    selected_group_ids = resolve_selected_group_ids(args, rubrics, profile)
    selected_leaf_rubrics = resolve_selected_leaf_rubrics(args, rubrics, selected_group_ids, profile)
    urls = build_urls(selected_cities, selected_leaf_rubrics)

    if args.write_urls_path:
        write_urls_path = Path(args.write_urls_path)
        write_urls_path.parent.mkdir(parents=True, exist_ok=True)
        write_urls_path.write_text('\n'.join(urls), encoding='utf-8')

    if args.save_profile_path:
        payload = build_profile_payload(
            selected_cities=selected_cities,
            selected_group_ids=selected_group_ids,
            selected_leaf_rubrics=selected_leaf_rubrics,
        )
        save_profile(args.save_profile_path, payload)

    output_path = resolve_output_path(args, selected_cities)
    print(f'Выбрано городов: {len(selected_cities)}')
    print(f'Выбрано верхнеуровневых блоков: {len(selected_group_ids)}')
    print(f'Выбрано листовых рубрик: {len(selected_leaf_rubrics)}')
    print(f'Сгенерировано URL: {len(urls)}')
    print(f'Итоговый файл: {output_path}')

    if args.list_selected_cities:
        print()
        print_selected_cities(selected_cities)

    for group_id in selected_group_ids:
        print(f'  {group_id:>5} | {rubric_label(rubrics[group_id])}')

    if args.list_selected_rubrics:
        print()
        print_selected_rubrics(selected_leaf_rubrics)

    if args.dry_run:
        print()
        print('Первые URL:')
        for url in urls[:20]:
            print(url)
        if len(urls) > 20:
            print(f'... ещё {len(urls) - 20} URL')
        return

    config = Configuration()
    config.chrome.headless = not args.show_browser
    config.writer.csv.remove_duplicates = not args.keep_duplicates
    if args.parser_max_records is not None:
        config.parser.max_records = args.parser_max_records

    cli_app(urls, output_path, args.format, config)
