"""Memory-bounded training process with progress updates and no wall-clock cutoff."""

import multiprocessing as mp
import os
import time


def _run(channel, data, asof, deep, names):
    try:
        from agent1.adaptive.methods import train
        from agent1.adaptive.operating import select_operating
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=2):
            bundle = train(
                data, asof, lambda msg: channel.send(("progress", msg)), names=names
            )
            channel.send(
                ("progress", "Đang kiểm định chuỗi tiền và các phương án học mở rộng")
            )
            bundle["operating"] = select_operating(data, asof, deep)
        channel.send(("progress", "Đang hoàn tất phiên bản và báo cáo"))
        channel.send(("ready", bundle))
    except (MemoryError, ValueError, RuntimeError, ImportError) as exc:
        channel.send(
            (
                "error",
                str(exc)
                if isinstance(exc, ValueError)
                else "Worker không đủ tài nguyên hoặc thiếu phụ thuộc.",
            )
        )
    finally:
        channel.close()


def isolated_train(data, asof, deep, progress, names=None):
    import psutil

    rss = max(128, int(os.environ.get("AGENT1_TRAIN_MIB", "2048"))) * 2**20
    ctx = mp.get_context("spawn")
    reader, writer = ctx.Pipe(duplex=False)
    child = ctx.Process(
        target=_run, args=(writer, data, asof, deep, names), daemon=True
    )
    child.start()
    writer.close()
    start = time.monotonic()
    stage = "Khởi tạo worker"
    last_update = start
    try:
        while True:
            now = time.monotonic()
            if now - last_update >= 15:
                progress(f"{stage} · đã chạy {int(now - start)} giây")
                last_update = now
            if child.is_alive() and psutil.Process(child.pid).memory_info().rss > rss:
                raise ValueError("Tác vụ vượt ngân sách RAM; hãy chia nhỏ dữ liệu.")
            if reader.poll(0.25):
                try:
                    kind, result = reader.recv()
                except EOFError:
                    raise ValueError("Worker bị gián đoạn trước khi hoàn tất.")
                if kind == "ready":
                    result["training_seconds"] = round(time.monotonic() - start, 2)
                    return result
                if kind == "error":
                    raise ValueError(result)
                stage = result
                last_update = time.monotonic()
                progress(result)
            elif not child.is_alive():
                raise ValueError("Worker đã dừng; hãy thử lại.")
    finally:
        reader.close()
        child.join(0.5)
        if child.is_alive():
            child.terminate()
            child.join()
        child.close()
