from parser_2gis.bulk_export import load_cities, load_rubrics
from parser_2gis.webui import (
    build_city_records,
    build_country_records,
    build_leaf_rubric_records,
    build_preset_records,
    resolve_selection,
    rubric_matches_preset,
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
    balashikha = next(city for city in cities if city['code'] == 'balashikha')
    troitsk = next(city for city in cities if city['code'] == 'troitsk')
    verkhoyansk = next(city for city in cities if city['code'] == 'verkhoyansk')
    mirny = next(city for city in cities if city['code'] == 'mirny')

    assert balashikha['search_code'] == 'moscow_region'
    assert balashikha['query_suffix'] == 'Балашиха'
    assert troitsk['search_code'] == 'moscow'
    assert verkhoyansk['search_code'] == 'geo/70030076128027117'
    assert mirny['search_code'] == 'mirnyj-yakutia-region'


def test_build_city_records_contains_many_custom_region_cities():
    cities = build_city_records(load_cities())
    custom_cities = [city for city in cities if city.get('source') == 'custom']

    assert len(custom_cities) >= 80
    assert any(city['code'] == 'khimki' for city in custom_cities)
    assert any(city['code'] == 'mytishchi' for city in custom_cities)
    assert any(city['code'] == 'aldan' for city in custom_cities)
    assert any(city['code'] == 'neryungri' for city in custom_cities)
    assert any(city['code'] == 'udachny' for city in custom_cities)


def test_rubric_matches_preset_respects_include_and_exclude_terms():
    rubric = {
        'label': 'Оптовые продажи стройматериалов',
        'path': 'Оптовые продажи / Стройматериалы',
        'top_group_label': 'Строительство',
    }
    preset = {
        'include_terms': ['опт', 'строй'],
        'exclude_terms': ['кафе'],
    }

    assert rubric_matches_preset(rubric, preset) is True


def test_build_preset_records_returns_non_empty_core_presets():
    rubrics = build_leaf_rubric_records(load_rubrics(is_russian=None))
    presets = {preset['id']: preset for preset in build_preset_records(rubrics)}

    assert presets['b2b_logistics']['rubrics_count'] > 0
    assert presets['wholesale']['rubrics_count'] > 0
    assert presets['construction']['rubrics_count'] > 0
    assert presets['manufacturing']['rubrics_count'] > 0


def test_resolve_selection_validates_codes_and_returns_groups():
    selected_cities, selected_group_ids, selected_rubrics = resolve_selection({
        'city_codes': ['podolsk'],
        'rubric_ids': ['207'],
    })

    assert selected_cities[0]['code'] == 'podolsk'
    assert selected_group_ids == ['5']
    assert selected_rubrics == [{'code': '207', 'label': 'Аптеки'}]
