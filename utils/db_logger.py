
import uuid
from typing import Optional
from models.database import get_db_session
from models.orm_models import LogMessage

def log_to_db(task_id: Optional[str], agent_name: str, message: str):
    """
    Writes a log message to the database.

    Args:
        task_id: The ID of the current task. If None, generates a fallback ID.
        agent_name: The name of the agent logging the message.
        message: The log message.
    """
    # Handle None task_id by generating a fallback
    if task_id is None:
        task_id = f"unknown-{uuid.uuid4()}"

    with get_db_session() as db:
        log_entry = LogMessage(
            task_id=task_id,
            agent_name=agent_name,
            message=message,
        )
        db.add(log_entry)
        db.commit()
