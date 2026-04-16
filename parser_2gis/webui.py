from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

from .bulk_export import (
    build_profile_payload,
    iter_leaf_rubrics,
    load_cities,
    load_rubrics,
    rubric_label,
    save_profile,
    top_level_group_ids,
)
from .paths import data_path

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8787
DATA_DIR = Path(os.environ.get('PARSER_2GIS_DATA_DIR', '/data'))
PROFILES_DIR = DATA_DIR / 'profiles'
HTML_PATH = data_path() / 'webui' / 'index.html'
PRESETS_PATH = data_path() / 'rubric_presets.json'
MAX_LOG_LINES = 400

COUNTRY_NAMES = {
    'ae': 'ОАЭ',
    'az': 'Азербайджан',
    'bh': 'Бахрейн',
    'by': 'Беларусь',
    'cl': 'Чили',
    'cy': 'Кипр',
    'cz': 'Чехия',
    'eg': 'Египет',
    'iq': 'Ирак',
    'it': 'Италия',
    'kg': 'Кыргызстан',
    'kw': 'Кувейт',
    'kz': 'Казахстан',
    'om': 'Оман',
    'qa': 'Катар',
    'ru': 'Россия',
    'sa': 'Саудовская Аравия',
    'uz': 'Узбекистан',
}

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def safe_slug(value: str, default: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', ' ', value).strip()
    cleaned = re.sub(r'\s+', '-', cleaned)
    cleaned = cleaned.strip('.-')
    return cleaned or default


def timestamp_suffix() -> str:
    return time.strftime('%Y%m%d-%H%M%S')


def normalize_match_text(value: str) -> str:
    return ' '.join(value.lower().replace('ё', 'е').split())


def load_rubric_preset_definitions() -> list[dict[str, Any]]:
    if not PRESETS_PATH.exists():
        return []

    payload = json.loads(PRESETS_PATH.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise SystemExit(f'Файл {PRESETS_PATH} должен содержать список пресетов.')

    return payload


def rubric_matches_preset(rubric: dict[str, Any], preset_definition: dict[str, Any]) -> bool:
    search_text = normalize_match_text(
        f'{rubric["label"]} {rubric["path"]} {rubric["top_group_label"]}'
    )
    include_terms = [
        normalize_match_text(term)
        for term in preset_definition.get('include_terms', [])
        if str(term).strip()
    ]
    exclude_terms = [
        normalize_match_text(term)
        for term in preset_definition.get('exclude_terms', [])
        if str(term).strip()
    ]
    if not include_terms:
        return False

    if not any(term in search_text for term in include_terms):
        return False

    return not any(term in search_text for term in exclude_terms)


def build_preset_records(rubrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    presets: list[dict[str, Any]] = []
    for preset_definition in load_rubric_preset_definitions():
        matched_rubrics = [
            rubric for rubric in rubrics
            if rubric_matches_preset(rubric, preset_definition)
        ]
        presets.append({
            'id': preset_definition['id'],
            'label': preset_definition['label'],
            'description': preset_definition.get('description', ''),
            'group_ids': sorted({rubric['top_group_id'] for rubric in matched_rubrics}),
            'rubric_ids': [rubric['code'] for rubric in matched_rubrics],
            'rubrics_count': len(matched_rubrics),
        })

    return presets


def find_top_group_id(rubrics: dict[str, dict[str, Any]], node_id: str) -> str:
    current_id = node_id
    while True:
        node = rubrics[current_id]
        parent_id = node['parentCode']
        if parent_id == '0':
            return current_id
        current_id = parent_id


def build_rubric_path(rubrics: dict[str, dict[str, Any]], node_id: str) -> str:
    parts: list[str] = []
    current_id = node_id
    while current_id in rubrics:
        node = rubrics[current_id]
        parts.append(rubric_label(node))
        parent_id = node['parentCode']
        if parent_id == '0':
            break
        current_id = parent_id
    return ' / '.join(reversed(parts))


def build_leaf_rubric_records(rubrics: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for group_id in top_level_group_ids(rubrics):
        for node in iter_leaf_rubrics(rubrics, [group_id]):
            top_group_id = find_top_group_id(rubrics, node['code'])
            top_group = rubrics[top_group_id]
            records.append({
                'code': node['code'],
                'label': rubric_label(node),
                'path': build_rubric_path(rubrics, node['code']),
                'top_group_id': top_group_id,
                'top_group_label': rubric_label(top_group),
                'is_russian': bool(node.get('isRussian', True)),
                'is_non_russian': bool(node.get('isNonRussian', True)),
            })

    return sorted(records, key=lambda item: (item['top_group_label'], item['path']))


def build_group_records(rubrics: dict[str, dict[str, Any]],
                        leaf_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for group_id in top_level_group_ids(rubrics):
        grouped[group_id] = {
            'code': group_id,
            'label': rubric_label(rubrics[group_id]),
            'leaf_count': 0,
            'ru_leaf_count': 0,
            'non_ru_leaf_count': 0,
        }

    for record in leaf_records:
        group = grouped[record['top_group_id']]
        group['leaf_count'] += 1
        if record['is_russian']:
            group['ru_leaf_count'] += 1
        if record['is_non_russian']:
            group['non_ru_leaf_count'] += 1

    return sorted(grouped.values(), key=lambda item: item['label'])


def build_country_records(cities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for city in cities:
        country_code = city['country_code']
        bucket = grouped.setdefault(country_code, {
            'code': country_code,
            'label': COUNTRY_NAMES.get(country_code, country_code.upper()),
            'city_count': 0,
        })
        bucket['city_count'] += 1

    countries = sorted(grouped.values(), key=lambda item: (item['code'] != 'ru', item['label']))
    return countries


def build_city_records(cities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(city) for city in cities],
        key=lambda item: (item['country_code'] != 'ru', item['name']),
    )


@lru_cache(maxsize=1)
def get_catalogs() -> dict[str, Any]:
    cities = load_cities()
    rubrics = load_rubrics(is_russian=None)
    leaf_records = build_leaf_rubric_records(rubrics)
    presets = build_preset_records(leaf_records)
    return {
        'cities': build_city_records(cities),
        'countries': build_country_records(cities),
        'groups': build_group_records(rubrics, leaf_records),
        'presets': presets,
        'rubrics': leaf_records,
        'rubrics_tree': rubrics,
    }


def list_profile_summaries() -> list[dict[str, Any]]:
    ensure_runtime_dirs()
    profiles: list[dict[str, Any]] = []
    for path in sorted(PROFILES_DIR.glob('*.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            continue

        profiles.append({
            'name': path.stem,
            'display_name': payload.get('display_name', path.stem),
            'cities_count': len(payload.get('cities', [])),
            'rubrics_count': len(payload.get('rubric_ids', [])),
            'updated_at': int(path.stat().st_mtime),
        })

    return sorted(profiles, key=lambda item: (-item['updated_at'], item['display_name']))


def load_saved_profile(profile_name: str) -> dict[str, Any]:
    path = PROFILES_DIR / f'{profile_name}.json'
    if not path.exists():
        raise FileNotFoundError(profile_name)
    return json.loads(path.read_text(encoding='utf-8'))


def resolve_selection(selection: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    catalogs = get_catalogs()
    city_codes = [str(code) for code in selection.get('city_codes', []) if str(code).strip()]
    rubric_ids = [str(code) for code in selection.get('rubric_ids', []) if str(code).strip()]

    if not city_codes:
        raise ValueError('Выберите хотя бы один город.')
    if not rubric_ids:
        raise ValueError('Выберите хотя бы одну рубрику.')

    city_map = {city['code']: city for city in catalogs['cities']}
    rubric_map = {rubric['code']: rubric for rubric in catalogs['rubrics']}

    missing_cities = [code for code in city_codes if code not in city_map]
    missing_rubrics = [code for code in rubric_ids if code not in rubric_map]
    if missing_cities:
        raise ValueError(f'Не найдены города: {", ".join(missing_cities)}')
    if missing_rubrics:
        raise ValueError(f'Не найдены рубрики: {", ".join(missing_rubrics)}')

    selected_cities = [city_map[code] for code in city_codes]
    selected_rubrics = [rubric_map[code] for code in rubric_ids]
    selected_group_ids = sorted({rubric['top_group_id'] for rubric in selected_rubrics})
    selected_leaf_rubrics = [
        {'code': rubric['code'], 'label': rubric['label']}
        for rubric in selected_rubrics
    ]
    return selected_cities, selected_group_ids, selected_leaf_rubrics


def build_profile_for_selection(selection: dict[str, Any],
                                display_name: str | None = None) -> dict[str, Any]:
    selected_cities, selected_group_ids, selected_leaf_rubrics = resolve_selection(selection)
    payload = build_profile_payload(
        selected_cities=selected_cities,
        selected_group_ids=selected_group_ids,
        selected_leaf_rubrics=selected_leaf_rubrics,
    )
    if display_name:
        payload['display_name'] = display_name
    payload['country_codes'] = sorted({city['country_code'] for city in selected_cities})
    return payload


def default_output_name(selected_cities: list[dict[str, Any]], file_format: str) -> str:
    if len(selected_cities) == 1:
        prefix = selected_cities[0]['code']
    else:
        prefix = f'multi-city-{len(selected_cities)}'
    return f'{prefix}-{timestamp_suffix()}.{file_format}'


def bulk_command_prefix() -> list[str]:
    cli_path = shutil.which('parser-2gis-bulk')
    if cli_path:
        return [cli_path]
    return [sys.executable, '-c', 'from parser_2gis.bulk_export import main; main()']


def public_job_state(job: dict[str, Any]) -> dict[str, Any]:
    output_path = Path(job['output_path'])
    data = {
        'id': job['id'],
        'status': job['status'],
        'return_code': job.get('return_code'),
        'created_at': job['created_at'],
        'updated_at': job['updated_at'],
        'finished_at': job.get('finished_at'),
        'command': job['command'],
        'log': ''.join(job['log']),
        'output_name': output_path.name,
        'output_exists': output_path.exists(),
        'output_size': output_path.stat().st_size if output_path.exists() else 0,
        'download_url': f'/download/{job["id"]}' if output_path.exists() else None,
    }
    return data


def update_job(job_id: str, **changes: Any) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job.update(changes)
        job['updated_at'] = time.time()


def append_job_log(job_id: str, line: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        job['log'].append(line)
        if len(job['log']) > MAX_LOG_LINES:
            job['log'] = job['log'][-MAX_LOG_LINES:]
        job['updated_at'] = time.time()


def run_job(job_id: str, command: list[str], output_path: Path) -> None:
    update_job(job_id, status='running')
    try:
        process = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
        )
    except Exception as exc:
        update_job(job_id, status='failed', return_code=-1, finished_at=time.time())
        append_job_log(job_id, f'Не удалось запустить процесс: {exc}\n')
        return

    assert process.stdout is not None
    for line in process.stdout:
        append_job_log(job_id, line)

    return_code = process.wait()
    status = 'completed' if return_code == 0 and output_path.exists() else 'failed'
    update_job(
        job_id,
        status=status,
        return_code=return_code,
        finished_at=time.time(),
    )


def start_job(*, command: list[str], output_path: Path) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    job = {
        'id': job_id,
        'status': 'queued',
        'created_at': time.time(),
        'updated_at': time.time(),
        'command': ' '.join(command),
        'output_path': str(output_path),
        'log': [],
    }
    with JOBS_LOCK:
        JOBS[job_id] = job

    thread = threading.Thread(
        target=run_job,
        args=(job_id, command, output_path),
        daemon=True,
    )
    thread.start()
    return public_job_state(job)


def create_app() -> Flask:
    ensure_runtime_dirs()
    app = Flask(__name__)

    @app.get('/')
    def index() -> Any:
        return send_file(HTML_PATH)

    @app.get('/api/bootstrap')
    def api_bootstrap() -> Any:
        catalogs = get_catalogs()
        return jsonify({
            'countries': catalogs['countries'],
            'cities': catalogs['cities'],
            'groups': catalogs['groups'],
            'presets': catalogs['presets'],
            'rubrics': catalogs['rubrics'],
            'profiles': list_profile_summaries(),
            'defaults': {
                'country_codes': ['ru'],
                'format': 'xlsx',
                'remove_duplicates': True,
                'parser_max_records': '',
            },
        })

    @app.get('/api/profiles')
    def api_profiles() -> Any:
        return jsonify({'profiles': list_profile_summaries()})

    @app.get('/api/profiles/<path:profile_name>')
    def api_profile(profile_name: str) -> Any:
        try:
            payload = load_saved_profile(profile_name)
        except FileNotFoundError:
            return jsonify({'error': f'Профиль {profile_name} не найден.'}), 404
        return jsonify(payload)

    @app.post('/api/profiles')
    def api_save_profile() -> Any:
        payload = request.get_json(silent=True) or {}
        display_name = str(payload.get('name', '')).strip()
        if not display_name:
            return jsonify({'error': 'Укажите имя профиля.'}), 400

        try:
            profile_payload = build_profile_for_selection(payload.get('selection') or {}, display_name)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        profile_name = safe_slug(display_name, f'profile-{timestamp_suffix()}')
        save_profile(str(PROFILES_DIR / f'{profile_name}.json'), profile_payload)
        return jsonify({
            'ok': True,
            'profile': {
                'name': profile_name,
                'display_name': display_name,
                'cities_count': len(profile_payload.get('cities', [])),
                'rubrics_count': len(profile_payload.get('rubric_ids', [])),
            },
        })

    @app.post('/api/jobs')
    def api_create_job() -> Any:
        payload = request.get_json(silent=True) or {}
        selection = payload.get('selection') or {}
        file_format = str(payload.get('format') or 'xlsx').strip().lower()
        if file_format not in {'xlsx', 'csv', 'json'}:
            return jsonify({'error': 'Поддерживаются только xlsx, csv и json.'}), 400

        try:
            selected_cities, _, _ = resolve_selection(selection)
            profile_payload = build_profile_for_selection(selection)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        output_name = str(payload.get('output_name') or '').strip()
        if output_name:
            output_name = safe_slug(output_name, f'export-{timestamp_suffix()}')
            if '.' not in output_name:
                output_name = f'{output_name}.{file_format}'
        else:
            output_name = default_output_name(selected_cities, file_format)

        output_path = DATA_DIR / output_name
        profile_path = PROFILES_DIR / f'_job_{timestamp_suffix()}_{uuid.uuid4().hex[:8]}.json'
        save_profile(str(profile_path), profile_payload)

        command = bulk_command_prefix() + [
            '--profile-path',
            str(profile_path),
            '--non-interactive',
            '--output-path',
            str(output_path),
            '--format',
            file_format,
        ]

        parser_max_records = str(payload.get('parser_max_records') or '').strip()
        if parser_max_records:
            command.extend(['--parser-max-records', parser_max_records])

        remove_duplicates = bool(payload.get('remove_duplicates', True))
        if not remove_duplicates:
            command.append('--keep-duplicates')

        job = start_job(command=command, output_path=output_path)
        return jsonify(job), 202

    @app.get('/api/jobs/<job_id>')
    def api_job(job_id: str) -> Any:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return jsonify({'error': f'Задача {job_id} не найдена.'}), 404
            return jsonify(public_job_state(job))

    @app.get('/download/<job_id>')
    def api_download(job_id: str) -> Any:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                return jsonify({'error': f'Задача {job_id} не найдена.'}), 404
            output_path = Path(job['output_path'])

        if not output_path.exists():
            return jsonify({'error': 'Файл результата пока недоступен.'}), 404

        return send_file(output_path, as_attachment=True, download_name=output_path.name)

    return app


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='parser-2gis-webui',
        description='Веб-интерфейс для пакетного экспорта 2GIS по городам и рубрикам',
    )
    parser.add_argument('--host', default=DEFAULT_HOST, help='Хост для запуска Flask-сервера')
    parser.add_argument('--port', default=DEFAULT_PORT, type=int, help='Порт для запуска Flask-сервера')
    parser.add_argument('--debug', action='store_true', help='Включить debug-режим Flask')
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
