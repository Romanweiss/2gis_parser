from parser_2gis.bulk_export import (
    build_profile_payload,
    build_search_url,
    build_urls,
    default_group_ids,
    filter_leaf_rubrics,
    iter_leaf_rubrics,
    load_cities,
    load_rubrics,
    resolve_output_path,
    resolve_runtime_metadata,
    url_query_encode,
)


def test_url_query_encode_keeps_russian_letters_and_spaces():
    assert url_query_encode('Аптеки и оптика') == 'Аптеки и оптика'


def test_build_search_url_for_russian_city():
    city = {'code': 'podolsk', 'domain': 'ru'}
    rubric = {'label': 'Аптеки', 'code': '207'}
    assert build_search_url(city=city, rubric=rubric) == (
        'https://2gis.ru/podolsk/search/Аптеки/rubricId/207/filters/sort=name'
    )


def test_load_cities_includes_many_custom_moscow_region_cities():
    cities = load_cities()
    city_codes = {city['code'] for city in cities}

    assert 'podolsk' in city_codes
    assert 'chekhov' in city_codes
    assert 'domodedovo' in city_codes
    assert 'serpuhov' in city_codes
    assert 'balashikha' in city_codes
    assert 'khimki' in city_codes
    assert 'mytishchi' in city_codes
    assert len([city for city in cities if city.get('source') == 'custom']) >= 60


def test_build_search_url_supports_custom_region_search_code_and_suffix():
    city = {
        'code': 'balashikha',
        'domain': 'ru',
        'search_code': 'moscow_region',
        'query_suffix': 'Балашиха',
    }
    rubric = {'label': 'Аптеки', 'code': '207'}
    assert build_search_url(city=city, rubric=rubric) == (
        'https://2gis.ru/moscow_region/search/Аптеки Балашиха/rubricId/207/filters/sort=name'
    )


def test_build_search_url_supports_troitsk_special_case():
    city = {
        'code': 'troitsk',
        'domain': 'ru',
        'search_code': 'moscow',
        'query_suffix': 'Троицк',
    }
    rubric = {'label': 'Аптеки', 'code': '207'}
    assert build_search_url(city=city, rubric=rubric) == (
        'https://2gis.ru/moscow/search/Аптеки Троицк/rubricId/207/filters/sort=name'
    )


def test_default_groups_exclude_government_and_emergency():
    rubrics = load_rubrics()
    group_ids = default_group_ids(rubrics)
    assert '1' not in group_ids
    assert '5419' not in group_ids
    assert '-1' not in group_ids


def test_iter_leaf_rubrics_for_medicine_contains_apteki():
    rubrics = load_rubrics()
    leaf_codes = {node['code'] for node in iter_leaf_rubrics(rubrics, ['5'])}
    assert '207' in leaf_codes


def test_filter_leaf_rubrics_by_include_and_exclude_queries():
    leaf_rubrics = [
        {'code': '1', 'label': 'Аптеки'},
        {'code': '2', 'label': 'Аптечные пункты'},
        {'code': '3', 'label': 'Стоматологии'},
    ]

    filtered = filter_leaf_rubrics(
        leaf_rubrics,
        include_queries=['апт'],
        exclude_queries=['пункты'],
    )

    assert [item['code'] for item in filtered] == ['1']


def test_build_profile_payload_contains_codes_and_labels():
    payload = build_profile_payload(
        selected_cities=[{
            'code': 'podolsk',
            'name': 'Подольск',
            'domain': 'ru',
            'country_code': 'ru',
        }],
        selected_group_ids=['5'],
        selected_leaf_rubrics=[{'code': '207', 'label': 'Аптеки'}],
    )

    assert payload['city_code'] == 'podolsk'
    assert payload['group_ids'] == ['5']
    assert payload['rubric_ids'] == ['207']
    assert payload['rubrics'][0]['label'] == 'Аптеки'


def test_resolve_runtime_metadata_prefers_args_then_profile_then_defaults():
    city_code, domain, city_name = resolve_runtime_metadata(
        type('Args', (), {'city_code': None, 'domain': None, 'city_name': None})(),
        {'city_code': 'moscow', 'domain': 'ru', 'city_name': 'Москва'},
    )

    assert city_code == 'moscow'
    assert domain == 'ru'
    assert city_name == 'Москва'


def test_build_urls_for_multiple_cities():
    urls = build_urls(
        selected_cities=[
            {'code': 'podolsk', 'domain': 'ru'},
            {'code': 'moscow', 'domain': 'ru'},
        ],
        selected_leaf_rubrics=[{'code': '207', 'label': 'Аптеки'}],
    )

    assert urls == [
        'https://2gis.ru/podolsk/search/Аптеки/rubricId/207/filters/sort=name',
        'https://2gis.ru/moscow/search/Аптеки/rubricId/207/filters/sort=name',
    ]


def test_resolve_output_path_for_single_and_multi_city():
    single = resolve_output_path(
        type('Args', (), {'output_path': None, 'format': 'xlsx'})(),
        [{'code': 'podolsk'}],
    )
    multi = resolve_output_path(
        type('Args', (), {'output_path': None, 'format': 'xlsx'})(),
        [{'code': 'podolsk'}, {'code': 'moscow'}],
    )

    assert single == '/data/podolsk_rubrics.xlsx'
    assert multi == '/data/multi_city_rubrics.xlsx'
