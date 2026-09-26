import os
from typing import Optional, Dict, Any
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "frontend")
_user_cache_func = components.declare_component("user_cache", path=_COMPONENT_DIR)

def render_user_cache(save_user_id: Optional[str] = None, key: str = "user_cache_comp") -> Optional[Dict[str, Any]]:
    """
    端末ブラウザの localStorage から直近のユーザーIDを取得・保存するコンポーネント。
    - save_user_id: 保存したいユーザーID（数値文字列など）。指定時は端末に永続化される。
    - 戻り値: {"user_id": str | None} または None（初期化前）
    """
    return _user_cache_func(save_user_id=save_user_id, key=key, default=None)
