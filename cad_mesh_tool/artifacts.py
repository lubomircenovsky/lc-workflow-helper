"""Atomic progress checkpoints shared with a polling UI on Windows."""
import json
import time


def publish_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf8')
    # Windows readers may briefly hold a handle without FILE_SHARE_DELETE.
    # Retry only that sharing failure; never overwrite via a non-atomic fallback.
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)
