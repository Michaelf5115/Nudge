from datetime import date, datetime


def format_due_date(date_str):
    """Format a date string for SMS display. '2025-03-14' → 'Friday Mar 14'"""
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
        return d.strftime('%A %b %-d')  # %-d = day without leading zero (Linux)
    except ValueError:
        return date_str


def is_overdue(date_str):
    """True if the date string is before today."""
    if not date_str:
        return False
    return date_str < date.today().isoformat()


def is_today(date_str):
    """True if the date string is today."""
    if not date_str:
        return False
    return date_str == date.today().isoformat()
