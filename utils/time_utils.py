from datetime import datetime
import pytz

def now_est_naive() -> datetime:
    est = pytz.timezone('US/Eastern')
    return datetime.now(est).replace(tzinfo=None)

