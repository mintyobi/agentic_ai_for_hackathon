"""アプリ全体の logging 初期化."""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """ルートロガーをアプリ標準の format で初期化する.

    api.py の lifespan から一度だけ呼ばれる想定。
    既に basicConfig 済みの場合は何もしない（pytest 等の二重初期化避け）。
    """
    root = logging.getLogger()
    if root.handlers:
        # 既に何かしらの logger が立っているので二重初期化しない
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # ノイズの多いライブラリを抑制
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
