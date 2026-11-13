"""Анализатор графа зависимостей NuGet."""

import argparse
import gzip
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MAX_DEPTH = 3
MIN_MAX_DEPTH = 1
NUGET_API_BASE_URL = "https://api.nuget.org/v3/registration5-gz-semver2"
HTTP_SUCCESS_STATUS = 200
ENCODING_UTF8 = "utf-8"
GZIP_SIGNATURE = b'\x1f\x8b'


def parse_arguments() -> argparse.Namespace:
    """Настраивает и разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Анализатор NuGet")
    parser.add_argument("--package", required=True, help="Имя пакета")
    parser.add_argument("--url", required=True, help="URL или путь к файлу")
    parser.add_argument("--test-mode", action="store_true", help="Тестовый режим")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help="Глубина")
    parser.add_argument("--filter", type=str, default="", help="Подстрока фильтра")
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """Проверяет корректность переданных аргументов."""
    if args.max_depth < MIN_MAX_DEPTH:
        print(f"Ошибка: глубина должна быть >= {MIN_MAX_DEPTH}")
        sys.exit(1)
    if args.test_mode and not os.path.exists(args.url):
        print(f"Ошибка: файл '{args.url}' не найден")
        sys.exit(1)


def print_configuration(args: argparse.Namespace) -> None:
    """Выводит параметры конфигурации в формате ключ-значение."""
    print("Параметры конфигурации")
    print(f"package: {args.package}")
    print(f"url: {args.url}")
    print(f"test_mode: {args.test_mode}")
    print(f"max_depth: {args.max_depth}")
    print(f"filter: '{args.filter}'")


def load_json_from_url(url: str) -> dict:
    """Загружает JSON по HTTP с поддержкой gzip и User-Agent."""
    try:
        headers = {"User-Agent": "Python-NuGet-Analyzer/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            if response.status != HTTP_SUCCESS_STATUS:
                print(f"Ошибка: сервер вернул статус {response.status}")
                sys.exit(1)
            raw_bytes = response.read()
            if raw_bytes.startswith(GZIP_SIGNATURE):
                raw_bytes = gzip.decompress(raw_bytes)
            return json.loads(raw_bytes.decode(ENCODING_UTF8))
    except urllib.error.HTTPError as error:
        print(f"Ошибка HTTP {error.code}: пакет не найден")
        sys.exit(1)
    except urllib.error.URLError as error:
        print(f"Ошибка сети: {error.reason}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Ошибка: некорректный JSON в ответе")
        sys.exit(1)


def load_json_from_file(path: str) -> dict:
    """Загружает JSON из локального файла."""
    try:
        with open(path, "r", encoding=ENCODING_UTF8) as file:
            return json.load(file)
    except json.JSONDecodeError:
        print(f"Ошибка: файл '{path}' содержит некорректный JSON")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Ошибка: файл '{path}' не найден")
        sys.exit(1)


def get_latest_version_data(data: dict, package_name: str) -> dict:
    """Возвращает данные о последней версии, обходя пагинацию NuGet."""
    items = data.get("items", [])
    if not items:
        print(f"Ошибка: пакет '{package_name}' не найден")
        sys.exit(1)

    last_page = items[-1]
    page_items = last_page.get("items", [])
    if page_items:
        return page_items[-1]

    if "@id" in last_page:
        print(f"  [Загрузка деталей страницы для {package_name}...]")
        page_data = load_json_from_url(last_page["@id"])
        nested_items = page_data.get("items", [])
        if nested_items:
            return nested_items[-1]

    print(f"Ошибка: не удалось получить версии для '{package_name}'")
    sys.exit(1)


def collect_dependencies(catalog_entry: dict) -> list:
    """Собирает уникальные зависимости из двух форматов NuGet API."""
    dependencies = list(catalog_entry.get("dependencies", []))
    for group in catalog_entry.get("dependencyGroups", []):
        for dep in group.get("dependencies", []):
            dep_id = dep.get("id")
            is_new = dep_id and not any(d.get("id") == dep_id for d in dependencies)
            if is_new:
                dependencies.append(dep)
    return dependencies


def print_dependencies(package_name: str, version: str, dependencies: list) -> list:
    """Выводит список прямых зависимостей и возвращает их имена."""
    print(f"\nПакет: {package_name} (версия {version})")
    print("Прямые зависимости:")
    if not dependencies:
        print("  (нет зависимостей)")
        return []

    result = []
    for dep in dependencies:
        dep_id = dep.get("id", "неизвестно")
        dep_range = dep.get("range", "")
        result.append(dep_id)
        print(f"  - {dep_id} {dep_range}")
    return result


def extract_dependencies_nuget(data: dict, package_name: str) -> list:
    """Извлекает и выводит прямые зависимости из NuGet-формата."""
    latest_version = get_latest_version_data(data, package_name)
    catalog_entry = latest_version.get("catalogEntry", {})
    version = catalog_entry.get("version", "неизвестно")
    dependencies = collect_dependencies(catalog_entry)
    return print_dependencies(package_name, version, dependencies)


def extract_dependencies_test(data: dict, package_name: str) -> list:
    """Извлекает прямые зависимости из тестового формата."""
    if package_name not in data:
        print(f"Ошибка: пакет '{package_name}' не найден в тестовых данных")
        sys.exit(1)

    dependencies = data[package_name].get("dependencies", [])
    print(f"\nПакет: {package_name}")
    print("Прямые зависимости:")
    if not dependencies:
        print("  (нет зависимостей)")
        return []

    for dep in dependencies:
        print(f"  - {dep}")
    return dependencies


def get_direct_dependencies(package_name: str, url: str, test_mode: bool) -> list:
    """Получает прямые зависимости из NuGet или тестового файла."""
    if test_mode:
        data = load_json_from_file(url)
        return extract_dependencies_test(data, package_name)

    full_url = f"{NUGET_API_BASE_URL}/{package_name.lower()}/index.json"
    data = load_json_from_url(full_url)
    return extract_dependencies_nuget(data, package_name)


def main() -> None:
    """Главная функция запуска приложения."""
    args = parse_arguments()
    validate_arguments(args)
    print_configuration(args)

    print("\n=== Этап 2: Сбор данных ===")
    get_direct_dependencies(args.package, args.url, args.test_mode)
    print("\nЭтап 2 успешно завершён.")


if __name__ == "__main__":
    main()