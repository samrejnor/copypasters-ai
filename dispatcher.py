import json
import os
from pathlib import Path

from alltokens import chat

CATEGORIES = {"техника", "сеть", "помещение", "другое"}
PRIORITIES = {"высокий", "обычный"}
JSON_FILE_NAME = "cases_training.json"


def load_knowledge_base():
    file_path = Path(__file__).resolve().parent / JSON_FILE_NAME

    if not file_path.exists():
        raise FileNotFoundError(f"Не найден файл базы примеров: {file_path}")

    with file_path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(f"{JSON_FILE_NAME} должен содержать JSON-массив.")

    return data


def _extract_content(response):
    """Извлекает текст из распространённых форматов ответа chat API."""
    if not isinstance(response, dict):
        raise ValueError("API вернул ответ неожиданного формата.")

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("В ответе API отсутствует choices.")

    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("В ответе API отсутствует текст классификации.")

    return content.strip()


def _parse_json(content):
    # Принимаем JSON как есть, а также ответ, случайно обёрнутый в Markdown.
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError("Ответ модели должен быть JSON-объектом.")

    category = result.get("category")
    priority = result.get("priority")
    question = result.get("question", "")

    if category not in CATEGORIES:
        raise ValueError(f"Неизвестная категория в ответе модели: {category!r}")
    if priority not in PRIORITIES:
        raise ValueError(f"Неизвестный приоритет в ответе модели: {priority!r}")
    if not isinstance(question, str):
        raise ValueError("Поле question в ответе модели должно быть строкой.")

    return {
        "category": category,
        "priority": priority,
        "question": question,
    }


def classify(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Текст обращения пуст.")

    # Режим для демонстрации интерфейса без обращения к модели.
    if os.environ.get("DISPATCHER\_DEMO", "0") == "1":
        return {
            "category": "другое",
            "priority": "обычный",
            "question": "",
        }

    examples = load_knowledge_base()

    system_instruction = (
        "Ты — классификатор школьных заявок техподдержки.\n"
        "Верни только JSON без Markdown в формате:\n"
        '{"category":"...","priority":"...","question":"..."}\n'
        "category должна быть одной из: техника, сеть, помещение, другое.\n"
        "priority должна быть одной из: высокий, обычный.\n"
        "question — короткий уточняющий вопрос, если для классификации "
        "не хватает важной информации; иначе пустая строка.\n\n"
        "Высокий приоритет ставь, когда из обращения ясно, что проблема прямо "
        "сейчас мешает идущему занятию, выступлению или другой текущей работе. "
        "Также он подходит, если мероприятие начинается прямо сейчас и проблема "
        "мешает ему.\n"
        "Фразы «урока не будет» и «урок не состоится» сами по себе не означают "
        "высокий приоритет: неясно, идёт ли занятие сейчас или оно отменено. "
        "В таком случае поставь обычный приоритет и уточни срочность.\n"
        "Если не указано место проблемы, уточни кабинет или помещение. "
        "Не спрашивай повторно то, что уже указано.\n\n"
        "Примеры:\n"
    )

    for item in examples:
        if not isinstance(item, dict):
            continue

        example = {
            "category": item.get("category"),
            "priority": item.get("priority"),
            "question": item.get("question", ""),
        }
        system_instruction += (
            f"Текст: {item.get('text', '')}\n"
            f"Ответ: {json.dumps(example, ensure_ascii=False)}\n\n"
        )

    response = chat([
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": text.strip()},
    ])

    try:
        return _parse_json(_extract_content(response))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Некорректный ответ классификатора: {error}") from error
