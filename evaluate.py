"""Проверка на отдельном наборе. Использование: python3 evaluate.py cases_test.json"""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Использование: python3 evaluate.py cases_test.json")
    cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    correct_category = correct_priority = 0
    for case in cases:
        request = Request(
            "http://127.0.0.1:5000/api/classify",
            data=json.dumps({"text": case["text"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=35) as response:
                answer = json.load(response)
            category = answer.get("category", "")
            priority = answer.get("priority", "")
        except (HTTPError, URLError, ValueError, TimeoutError) as error:
            category = priority = "ОШИБКА"
            print(f"  Запрос {case['id']}: {error}")
        category_ok = category == case["category"]
        priority_ok = priority == case["priority"]
        correct_category += category_ok
        correct_priority += priority_ok
        print(f"{case['id']:>2}: категория {category or 'пусто'} {'✓' if category_ok else '✗'}; "
              f"приоритет {priority or 'пусто'} {'✓' if priority_ok else '✗'}")
    total = len(cases)
    print(f"Итог: категория {correct_category}/{total}, приоритет {correct_priority}/{total}")


if __name__ == "__main__":
    main()
