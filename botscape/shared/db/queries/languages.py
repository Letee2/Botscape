from botscape.shared.db.caching import read_sql

def get_aggregated_languages(start_iso: str, end_iso: str):
    return read_sql("SELECT language, SUM(count) as count FROM metrics_language_daily WHERE date >= %(start)s AND date <= %(end)s GROUP BY language ORDER BY count DESC;", params={"start": start_iso, "end": end_iso})

def get_aggregated_words(start_iso: str, end_iso: str):
    return read_sql("SELECT word, SUM(count) as count FROM metrics_word_daily WHERE date >= %(start)s AND date <= %(end)s GROUP BY word ORDER BY count DESC LIMIT 200;", params={"start": start_iso, "end": end_iso})

def get_word_timeline(word: str, start_iso: str, end_iso: str):
    df = read_sql("SELECT date, SUM(count) as count FROM metrics_word_daily WHERE word = %(word)s AND date >= %(start)s AND date <= %(end)s GROUP BY date ORDER BY date ASC;", params={"word": word, "start": start_iso, "end": end_iso})
    return df.rename(columns={"date": "day"})

def get_bots_for_word(word: str, start_iso: str, end_iso: str):
    return read_sql("SELECT token, COUNT(*) as count FROM messages WHERE text LIKE %(word_like)s AND date_utc >= %(start)s AND date_utc < %(end)s GROUP BY token ORDER BY count DESC LIMIT 15;", params={"word_like": f"%{word}%", "start": start_iso, "end": end_iso})