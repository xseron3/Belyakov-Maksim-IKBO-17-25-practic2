"""Анализатор графа зависимостей NuGet."""

import argparse
import sys
import os

# Константы для избежания магических чисел (Правило М1)
DEFAULT_MAX_DEPTH = 3
MIN_MAX_DEPTH = 1


def parse_arguments() -> argparse.Namespace:
    """
    Настраивает и разбирает аргументы командной строки.

    Returns:
        argparse.Namespace: Объект с разобранными аргументами.
    """
    parser = argparse.ArgumentParser(
        description="Анализатор графа зависимостей NuGet"
    )

    parser.add_argument(
        "--package",
        required=True,
        help="Имя анализируемого пакета (например, Newtonsoft.Json)"
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL репозитория или путь к файлу тестового репозитория"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Режим работы с тестовым репозиторием"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help=f"Максимальная глубина анализа (по умолчанию {DEFAULT_MAX_DEPTH})"
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="",
        help="Подстрока для фильтрации пакетов"
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Проверяет корректность переданных аргументов.

    Args:
        args: Разобранные аргументы командной строки.

    Raises:
        SystemExit: Если аргументы некорректны.
    """
    if args.max_depth < MIN_MAX_DEPTH:
        print(f"Ошибка: максимальная глубина должна быть >= {MIN_MAX_DEPTH}")
        sys.exit(1)

    if args.test_mode and not os.path.exists(args.url):
        print(f"Ошибка: в тестовом режиме файл '{args.url}' не найден")
        sys.exit(1)


def print_configuration(args: argparse.Namespace) -> None:
    """
    Выводит все параметры конфигурации в формате ключ-значение.

    Args:
        args: Разобранные аргументы командной строки.
    """
    print("--- Параметры конфигурации ---")
    print(f"package: {args.package}")
    print(f"url: {args.url}")
    print(f"test_mode: {args.test_mode}")
    print(f"max_depth: {args.max_depth}")
    print(f"filter: '{args.filter}'")
    print("------------------------------")


def main() -> None:
    """Главная функция запуска приложения."""
    args = parse_arguments()

    validate_arguments(args)
    print_configuration(args)

    print("Этап 1 успешно завершён.")


if __name__ == "__main__":
    main()