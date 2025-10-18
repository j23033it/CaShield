"""ASR パッケージエントリーポイント。

単一段 ASR エンジンを公開し、他モジュールからインポートしやすくする。
"""

from .single_engine import SingleASREngine

__all__ = ["SingleASREngine"]


