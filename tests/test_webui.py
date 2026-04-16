from parser_2gis.bulk_export import load_cities, load_rubrics
from parser_2gis.webui import (
    build_city_records,
    build_country_records,
    build_leaf_rubric_records,
    resolve_selection,
)


def test_build_country_records_puts_russia_first():
    countries = build_country_records(load_cities())

    assert countries[0]['code'] == 'ru'
    assert countries[0]['label'] == 'Россия'


def test_build_leaf_rubric_records_contains_top_group_and_path():
    records = build_leaf_rubric_records(load_rubrics(is_russian=None))
    apteki = next(record for record in records if record['code'] == '207')

    assert apteki['top_group_id'] == '5'
    assert 'Аптеки' in apteki['path']


def test_build_city_records_preserves_custom_search_fields():
    cities = build_city_records(load_cities())
    troitsk = next(city for city in cities if city['code'] == 'troitsk')

    assert troitsk['search_code'] == 'moscow'
    assert troitsk['query_suffix'] == 'Троицк'


def test_resolve_selection_validates_codes_and_returns_groups():
    selected_cities, selected_group_ids, selected_rubrics = resolve_selection({
        'city_codes': ['podolsk'],
        'rubric_ids': ['207'],
    })

    assert selected_cities[0]['code'] == 'podolsk'
    assert selected_group_ids == ['5']
    assert selected_rubrics == [{'code': '207', 'label': 'Аптеки'}]
