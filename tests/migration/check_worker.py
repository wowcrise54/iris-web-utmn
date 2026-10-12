"""Read-only worker ping and harmless queued task on the isolated test broker."""
import json

from app import celery

if __name__ == "__main__":
    online = celery.control.inspect(timeout=10).ping()
    assert online and all(reply.get("ok") == "pong" for reply in online.values()), online
    result = celery.send_task("celery.accumulate", args=[1, 2, 3]).get(timeout=20)
    assert list(result) == [1, 2, 3], result
    print(json.dumps({"workers_online": len(online), "queued_task_result": list(result)}))
