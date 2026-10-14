"""Серверный вызов AllTokens. Не переносите этот код и ключ в браузер."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dotenv import load_dotenv

def chat(messages):
    key = os.getenv("API_KEY")
    if not key:
        raise RuntimeError("Ключ AllTokens не настроен. Обратитесь к наставнику.")

    body = json.dumps({
        "model": os.getenv("AI_MODEL"),
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
        "max_tokens": 200,
    }).encode("utf-8")
    request = Request(
        "https://alltokens.ru/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            return json.load(response)
    except HTTPError as error:
        # Не выводим тело ответа: оно может содержать лишние детали запроса.
        raise RuntimeError(f"AllTokens вернул код {error.code}. Сообщите наставнику.") from error
    except URLError as error:
        raise RuntimeError("Нет соединения с AllTokens. Проверьте сеть.") from error
