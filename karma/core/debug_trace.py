"""按文档保存带编号的各阶段输入和输出快照。"""

import json
import logging
import time
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

def snapshot(value):
    """复制数据，避免智能体原地修改共享实体或三元组后改变历史记录。"""
    if is_dataclass(value):
        return snapshot(asdict(value))
    if isinstance(value, dict):
        return {str(key): snapshot(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [snapshot(item) for item in value]
    if isinstance(value, set):
        return sorted(snapshot(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value


class DebugTrace:
    """每步完成或失败后立即写入记录，不序列化接口凭据配置。"""

    def __init__(self, root, parameters):
        self.directory = None
        self.parameters = parameters
        self.previous_file = None
        if root is not None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            self.directory = Path(root) / (run_id + "_" + uuid4().hex[:8])
            self.directory.mkdir(parents=True, exist_ok=False)

    def run(self, number, name, inputs, operation, output_names, agent=None):
        if self.directory is None:
            return operation()

        filename = f"{number:02d}_{name}.json"
        metrics_before = agent.get_metrics() if agent is not None else {}
        record = {
            "step": number,
            "name": name,
            "previous_file": self.previous_file,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "parameters": self.parameters,
            "inputs": snapshot(inputs),
        }
        start = time.perf_counter()
        try:
            result = operation()
        except Exception as exc:
            record.update(status="failed", outputs=None, error={
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            })
            raise
        else:
            values = (result,) if len(output_names) == 1 else result
            record.update(status="completed", outputs=snapshot(dict(zip(output_names, values))))
            return result
        finally:
            record["elapsed_seconds"] = time.perf_counter() - start
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            metrics_after = agent.get_metrics() if agent is not None else {}
            record["agent_metrics_delta"] = {
                key: value - metrics_before.get(key, 0)
                for key, value in metrics_after.items()
            }
            # 使用原子替换，避免读取到未写完的 JSON。
            path = self.directory / filename
            temporary = path.with_suffix(".json.tmp")
            try:
                temporary.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                temporary.replace(path)
                self.previous_file = filename
            except OSError:
                logger.exception("无法写入逐步调试文件： %s", path)
                # 追踪写入失败时保留原 Agent 异常。
                if record["status"] != "failed":
                    raise
