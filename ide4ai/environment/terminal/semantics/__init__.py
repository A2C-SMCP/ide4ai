"""
终端执行语义层 | Terminal execution semantics layer

提供输出清洗管线（ANSI/OSC/OSC-133 分阶段剥离）与退出码语义解释。
Provides output cleaning pipeline (staged stripping of ANSI/OSC/OSC-133) and exit-code semantic interpretation.
"""

from ide4ai.environment.terminal.semantics.output_pipeline import (
    clean_output,
    strip_ansi_csi,
    strip_ansi_osc,
    strip_osc133,
)

__all__ = [
    "clean_output",
    "strip_ansi_csi",
    "strip_ansi_osc",
    "strip_osc133",
]
