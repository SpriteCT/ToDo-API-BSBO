from datetime import datetime

def is_urgent_from_deadline(deadline_at: datetime) -> bool:
    if deadline_at is None:
        return False
    days_left = (deadline_at.date() - datetime.utcnow().date()).days 
    return days_left <= 3


def calc_quadrant(is_important: bool, deadline_at: datetime) -> str:
    urgent = is_urgent_from_deadline(deadline_at)
    if is_important and urgent:
        return "Q1"
    elif is_important and not urgent:
        return "Q2"
    elif not is_important and urgent:
        return "Q3"
    else:
        return "Q4"
