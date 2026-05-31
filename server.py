"""MCP Notes server.

Простий, але повноцінний MCP-сервер для нотаток. Нотатки зберігаються у
локальному JSON-файлі (реальна персистентна логіка, без зовнішніх API).

Tools:
    - create_note(title, content, tags=None)  -> required args (title, content)
    - search_notes(query="", tag="")          -> optional args (обидва)
    - update_note(note_id, ...)               -> mix
    - delete_note(note_id)                     -> required arg

Resources:
    - notes://all            -> усі нотатки
    - notes://stats          -> статистика
    - notes://{note_id}      -> конкретна нотатка (resource template)

Transport: stdio.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("notes")

# Шлях до сховища можна перевизначити змінною середовища (зручно для тестів),
# інакше — файл поряд із цим скриптом.
DATA_FILE = Path(
    os.environ.get("NOTES_DATA_FILE", Path(__file__).parent / "notes_data.json")
)


# --- Сховище -----------------------------------------------------------------


def _now() -> str:
    """Поточний момент у ISO-8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict[str, Any]:
    """Прочитати сховище. Якщо файлу нема або він пошкоджений — порожня структура."""
    if not DATA_FILE.exists():
        return {"next_id": 1, "notes": []}
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"next_id": 1, "notes": []}
    data.setdefault("next_id", 1)
    data.setdefault("notes", [])
    return data


def _save(data: dict[str, Any]) -> None:
    """Атомарно записати сховище на диск."""
    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def _find(notes: list[dict[str, Any]], note_id: str) -> dict[str, Any] | None:
    return next((n for n in notes if n["id"] == note_id), None)


def _format_note(note: dict[str, Any]) -> str:
    """Людиночитабельне представлення нотатки."""
    tags = ", ".join(note["tags"]) if note["tags"] else "—"
    return (
        f"[{note['id']}] {note['title']}\n"
        f"Теги: {tags}\n"
        f"Створено: {note['created_at']} | Оновлено: {note['updated_at']}\n"
        f"---\n{note['content']}"
    )


# --- Tools -------------------------------------------------------------------


@mcp.tool()
def create_note(title: str, content: str, tags: list[str] | None = None) -> str:
    """Створити нову нотатку.

    Args:
        title: Заголовок нотатки (обов'язково).
        content: Текст нотатки (обов'язково).
        tags: Необов'язковий список тегів.
    """
    title = title.strip()
    if not title:
        return "Помилка: заголовок не може бути порожнім."

    data = _load()
    note = {
        "id": f"note-{data['next_id']}",
        "title": title,
        "content": content,
        "tags": [t.strip() for t in (tags or []) if t.strip()],
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["notes"].append(note)
    data["next_id"] += 1
    _save(data)
    return f"Нотатку створено: {note['id']} — «{note['title']}»."


@mcp.tool()
def search_notes(query: str = "", tag: str = "") -> str:
    """Знайти нотатки за текстом і/або тегом.

    Обидва аргументи необов'язкові. Якщо обидва порожні — повертає всі нотатки.

    Args:
        query: Підрядок для пошуку в заголовку чи тексті (необов'язково).
        tag: Точний тег для фільтрації (необов'язково).
    """
    data = _load()
    notes = data["notes"]
    q = query.strip().lower()
    t = tag.strip().lower()

    def matches(note: dict[str, Any]) -> bool:
        ok_q = (not q) or q in note["title"].lower() or q in note["content"].lower()
        ok_t = (not t) or t in [tg.lower() for tg in note["tags"]]
        return ok_q and ok_t

    found = [n for n in notes if matches(n)]
    if not found:
        return "Нотаток за заданими критеріями не знайдено."

    header = f"Знайдено нотаток: {len(found)}\n\n"
    return header + "\n\n".join(_format_note(n) for n in found)


@mcp.tool()
def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Оновити наявну нотатку. Передаються лише ті поля, які треба змінити.

    Args:
        note_id: Ідентифікатор нотатки (обов'язково).
        title: Новий заголовок (необов'язково).
        content: Новий текст (необов'язково).
        tags: Новий список тегів (необов'язково).
    """
    data = _load()
    note = _find(data["notes"], note_id)
    if note is None:
        return f"Помилка: нотатку «{note_id}» не знайдено."

    if title is not None:
        note["title"] = title.strip()
    if content is not None:
        note["content"] = content
    if tags is not None:
        note["tags"] = [t.strip() for t in tags if t.strip()]
    note["updated_at"] = _now()
    _save(data)
    return f"Нотатку оновлено: {note['id']} — «{note['title']}»."


@mcp.tool()
def delete_note(note_id: str) -> str:
    """Видалити нотатку за ідентифікатором.

    Args:
        note_id: Ідентифікатор нотатки (обов'язково).
    """
    data = _load()
    note = _find(data["notes"], note_id)
    if note is None:
        return f"Помилка: нотатку «{note_id}» не знайдено."

    data["notes"] = [n for n in data["notes"] if n["id"] != note_id]
    _save(data)
    return f"Нотатку видалено: {note_id} — «{note['title']}»."


# --- Resources ---------------------------------------------------------------


@mcp.resource("notes://all")
def all_notes() -> str:
    """Усі збережені нотатки."""
    data = _load()
    if not data["notes"]:
        return "Сховище порожнє — нотаток ще немає."
    return "\n\n".join(_format_note(n) for n in data["notes"])


@mcp.resource("notes://stats")
def notes_stats() -> str:
    """Статистика сховища: кількість нотаток і розподіл за тегами."""
    data = _load()
    notes = data["notes"]
    tag_counter: Counter[str] = Counter(t for n in notes for t in n["tags"])
    lines = [f"Усього нотаток: {len(notes)}"]
    if tag_counter:
        lines.append("Теги:")
        for tag, count in tag_counter.most_common():
            lines.append(f"  - {tag}: {count}")
    else:
        lines.append("Тегів ще немає.")
    return "\n".join(lines)


@mcp.resource("notes://{note_id}")
def get_note(note_id: str) -> str:
    """Конкретна нотатка за ідентифікатором."""
    data = _load()
    note = _find(data["notes"], note_id)
    if note is None:
        return f"Нотатку «{note_id}» не знайдено."
    return _format_note(note)


if __name__ == "__main__":
    mcp.run(transport="stdio")
