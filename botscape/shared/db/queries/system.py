from botscape.shared.db.caching import read_sql

def get_host_health_metrics():
    return read_sql("SELECT metric_name, value_numeric, last_updated FROM system_health;")

def get_database_size(db_name: str):
    return read_sql("SELECT pg_size_pretty(pg_database_size(%(db_name)s)) AS size;", params={"db_name": db_name})

def get_tables_size_breakdown(limit: int = 10):
    return read_sql("SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS total_size_pretty FROM information_schema.tables WHERE table_schema = 'public' ORDER BY pg_total_relation_size(quote_ident(table_name)) DESC LIMIT %(limit)s;", params={"limit": limit})