"""RAG quality scoring service."""
import re

from sqlalchemy.orm import Session

from models import FileTask, TaskStatus


def score_text_quality(content: str) -> dict:
    text = content or ""
    words = re.findall(r"[\w一-鿿]+", text)
    headings = len(re.findall(r"^#{1,6}\s+", text, re.M))
    tables = text.count("\n|")
    images = len(re.findall(r"!\[[^\]]*\]\([^)]*\)", text))
    score = 0
    if len(text) >= 500:
        score += 35
    elif len(text) >= 100:
        score += 20
    if len(words) >= 100:
        score += 25
    elif len(words) >= 30:
        score += 15
    score += min(headings * 5, 20)
    score += min((tables + images) * 2, 20)
    return {
        "score": min(score, 100),
        "characters": len(text),
        "tokens_estimate": len(words),
        "headings": headings,
        "tables": tables,
        "images": images,
    }


def get_quality_score_impl(db: Session, task_id: int, read_content_fn) -> dict:
    task = db.query(FileTask).filter(FileTask.id == task_id).first()
    if not task:
        return {"score": 0, "error": "Task not found"}
    if task.status != TaskStatus.COMPLETED or not task.output_path:
        return {"score": 0, "error": "Result not ready"}
    content = read_content_fn(task.output_path)
    return {"task_id": task_id, **score_text_quality(content)}
