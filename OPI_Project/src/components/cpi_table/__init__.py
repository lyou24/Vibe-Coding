import os
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "frontend")
_cpi_table_func = components.declare_component("cpi_table", path=_COMPONENT_DIR)

def render_cpi_table(html_content: str, key: str = None):
    """
    CPI風HTMLテーブルをレンダリングし、曲名タップ時にノンリロードで
    選択された chart_id と timestamp を返すコンポーネント。
    """
    return _cpi_table_func(html_content=html_content, key=key, default=None)
