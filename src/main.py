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
    parser = argparse.ArgumentParser(description="Анализатор NuGet")
    parser.add_argument("--package", required=True, help="Имя пакета")
    parser.add_argument("--url", required=True, help="URL или путь к файлу")
    parser.add_argument("--test-mode", action="store_true", help="Тестовый режим")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH, help="Глубина")
    parser.add_argument("--filter", type=str, default="", help="Подстрока фильтра")
    parser.add_argument("--reverse", action="store_true", help="Поиск обратных зависимостей")
    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    if args.max_depth < MIN_MAX_DEPTH:
        print(f"Ошибка: глубина должна быть >= {MIN_MAX_DEPTH}")
        sys.exit(1)
    if args.test_mode and not os.path.exists(args.url):
        print(f"Ошибка: файл '{args.url}' не найден")
        sys.exit(1)


def print_configuration(args: argparse.Namespace) -> None:
    print("Параметры конфигурации")
    print(f"package: {args.package}")
    print(f"url: {args.url}")
    print(f"test_mode: {args.test_mode}")
    print(f"max_depth: {args.max_depth}")
    print(f"filter: '{args.filter}'")
    print(f"reverse: {args.reverse}")


def load_json_from_url(url: str) -> dict:
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
    try:
        with open(path, "r", encoding=ENCODING_UTF8) as file:
            return json.load(file)
    except json.JSONDecodeError:
        print(f"Ошибка: файл '{path}' содержит некорректный JSON")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Ошибка: файл '{path}' не найден")
        sys.exit(1)


def build_inverted_graph(data: dict) -> dict:
    inverted = {pkg: [] for pkg in data}
    for pkg, info in data.items():
        for dep in info.get("dependencies", []):
            if dep in inverted:
                inverted[dep].append(pkg)
    return inverted


def get_dependencies_silent(package_name: str, url: str, test_mode: bool) -> list:
    if test_mode:
        data = load_json_from_file(url)
        return data.get(package_name, {}).get("dependencies", [])

    full_url = f"{NUGET_API_BASE_URL}/{package_name.lower()}/index.json"
    try:
        data = load_json_from_url(full_url)
        items = data.get("items", [])
        if not items:
            return []
        
        last_page = items[-1]
        if "items" in last_page and last_page["items"]:
            latest = last_page["items"][-1]
        elif "@id" in last_page:
            page_data = load_json_from_url(last_page["@id"])
            latest = page_data.get("items", [])[-1]
        else:
            return []

        catalog = latest.get("catalogEntry", {})
        deps = list(catalog.get("dependencies", []))
        for group in catalog.get("dependencyGroups", []):
            for dep in group.get("dependencies", []):
                dep_id = dep.get("id")
                if dep_id and not any(d.get("id") == dep_id for d in deps):
                    deps.append(dep)
        
        return [d.get("id", "неизвестно") for d in deps]
    except SystemExit:
        return []


def build_dependency_graph(
    start_pkg: str, max_depth: int, filter_str: str, get_deps_func
) -> tuple:
    graph = {}
    visited = set()
    cycles = []
    stack = [(start_pkg, 0)]

    while stack:
        pkg, depth = stack.pop()

        if pkg in visited or (filter_str and filter_str.lower() in pkg.lower()):
            continue

        visited.add(pkg)

        if depth < max_depth:
            deps = get_deps_func(pkg)
            filtered_deps = [
                dep for dep in deps 
                if not (filter_str and filter_str.lower() in dep.lower())
            ]
            graph[pkg] = filtered_deps

            for dep in filtered_deps:
                if dep in visited:
                    cycles.append(f"{pkg} -> {dep}")
                else:
                    stack.append((dep, depth + 1))

    return graph, cycles


def print_graph_results(
    graph: dict, cycles: list, start_pkg: str, is_reverse: bool = False
) -> None:

    title = "Обратные зависимости" if is_reverse else "Граф зависимостей"
    print(f"\n{title} (начиная с '{start_pkg}'):")
    
    for pkg, deps in graph.items():
        deps_str = ", ".join(deps) if deps else "нет"
        print(f"  {pkg} -> [{deps_str}]")

    if cycles:
        print("\nОбнаружены циклические зависимости:")
        for cycle in sorted(list(set(cycles))):
            print(f"  ! {cycle}")
    else:
        print("\nЦиклические зависимости не обнаружены.")


def main() -> None:

    args = parse_arguments()
    validate_arguments(args)
    print_configuration(args)

    if args.reverse:
        print("\nЭтап 4: Обратные зависимости")
        if args.test_mode:
            data = load_json_from_file(args.url)
            inverted_graph = build_inverted_graph(data)
            
            def get_reverse_deps(pkg: str) -> list:
                return inverted_graph.get(pkg, [])
            
            graph, cycles = build_dependency_graph(
                args.package, args.max_depth, args.filter, get_reverse_deps
            )
            print_graph_results(graph, cycles, args.package, is_reverse=True)
        else:
            print("\nРежим обратных зависимостей поддерживается в --test-mode")
            print("(так как требует наличия полного графа репозитория для инверсии)")
    else:
        print("\nЭтап 3: Построение графа (DFS без рекурсии)")
        
        def deps_wrapper(pkg: str) -> list:
            return get_dependencies_silent(pkg, args.url, args.test_mode)

        graph, cycles = build_dependency_graph(
            args.package, args.max_depth, args.filter, deps_wrapper
        )
        print_graph_results(graph, cycles, args.package, is_reverse=False)

    print("\nЭтап успешно завершён")


if __name__ == "__main__":
    main()