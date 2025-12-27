from botscape.shared.db.caching import read_sql
from datetime import date, timedelta

def get_system_health_kpis():
    return read_sql("SELECT (SELECT COUNT(*) FROM bots WHERE is_active = true) AS active_bots, (SELECT COUNT(*) FROM bots WHERE is_active = false) AS inactive_bots, (SELECT MAX(last_checked_utc) FROM bots) AS last_hunter_check, (SELECT MAX(last_seen) FROM bots) AS last_listener_message;")

def get_new_bots_stats(days: int = 7):
    start_date = (date.today() - timedelta(days=days)).isoformat()
    return read_sql("SELECT token, first_seen_utc, last_seen, AGE(last_seen, first_seen_utc) AS time_to_first_message FROM bots WHERE first_seen_utc >= %(start)s ORDER BY first_seen_utc DESC;", params={"start": start_date})

def get_dead_bots_stats(limit: int = 50):
    return read_sql("SELECT token, last_seen, last_checked_utc FROM bots WHERE is_active = false ORDER BY last_checked_utc DESC LIMIT %(limit)s;", params={"limit": limit})

def get_top_malware_sources(limit: int = 25):
    return read_sql("SELECT ho.sample_sha256, COUNT(DISTINCT b.token) AS active_bots_found, MAX(ho.first_seen) AS last_bot_found_date FROM hash_origin ho JOIN bots b ON ho.token = b.token WHERE b.is_active = true GROUP BY ho.sample_sha256 ORDER BY active_bots_found DESC, last_bot_found_date DESC LIMIT %(limit)s;", params={"limit": limit})