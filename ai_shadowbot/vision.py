"""视觉坐标系统（F005） —— 截图 → 脱敏 → 多模态视觉识别 → 坐标 remap → 返回。

设计（严格依据 docs/PRD-vision.md / docs/consensus-vision.md / docs/wiki-prelude-vision.md）：
  - 方案 A：复用既有 Config.make_llm_client()（OpenAIClient 已支持 image_url + tool_choice），
    VisionLocator 仅做薄封装，零新客户端代码。
  - 强制时序（闭合「屏上诱导」根因）：
      截图 → Observer.mask_sensitive_regions 脱敏(AC5 前置)
           → 多模态 LLM 识别(坐标, 在打码图空间)
           → remap 回原图像素空间(consensus CV5: mask→remap)
           → 返回 {x, y, label, confidence}
  - 信道隔离（AC4/R1）：label 文本只作数据/定位目标，绝不信任为指令；是否驱动动作由
    planner.ground_to_action 过 InjectionClassifier 决定（见 planner.py）。
  - 降级铁律：无 LLM_API_KEY / mock / 异常 → 返回 None，绝不编造坐标、绝不调真实 LLM。
  - dry_run 铁律：视觉重依赖（PIL / openai）全部在方法内 lazy import，
    降级路径（mock/无 key）全程不 import、不触碰屏幕。

坐标空间说明：
  - 视觉输出坐标基于「截图像素空间」，与 pyautogui 坐标空间一致（单屏默认）。
  - 多屏 / DPI 场景由 F002 AC2「元素锚定 + 重试」兜底（重截重定），本模块只保证
    remap 在单屏截图像素↔原图像素间正确。
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict, Optional

from ai_shadowbot.observer import Observer
from ai_shadowbot.config import Config


# ---------------------------------------------------------------------------
# 内部工具（lazy import PIL，避免 dry_run / mock 触碰视觉依赖）
# ---------------------------------------------------------------------------
def _load_image(data: bytes):
    """原始 PNG 字节 → PIL.Image（RGB）。lazy import。

    注意：入参是「原始图像字节」，不是 base64。base64 字符串需先 b64decode。
    """
    from PIL import Image  # type: ignore
    return Image.open(io.BytesIO(data)).convert("RGB")


def _pil_to_bytes(img) -> bytes:
    """PIL.Image → 原始 PNG 字节。lazy import。"""
    from PIL import Image  # type: ignore
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pil_to_b64(img) -> str:
    """PIL.Image → base64 字符串（供 Observer / ground_to_action 传递）。"""
    return base64.b64encode(_pil_to_bytes(img)).decode("ascii")


# ---------------------------------------------------------------------------
# 视觉定位器
# ---------------------------------------------------------------------------
class VisionLocator:
    """视觉坐标系统核心：截图 → 脱敏 → 多模态识别 → 坐标 remap → 返回。

    核心 API：vision_resolve(screenshot_bytes, query) -> Optional[dict]
      成功返回 {x, y, label, confidence}（原图像素空间）；
      降级（无 key / mock / 异常 / 未识别）返回 None。
    """

    def __init__(self, config: Config, observer: Optional[Observer] = None,
                 llm_client: Any = None):
        self.config = config
        self.observer = observer or Observer(
            screen_mask_sensitive=config.screen_mask_sensitive)
        # 可选注入客户端（测试 / 演示桩）。未注入时走 Config.make_llm_client()。
        self._llm = llm_client

    # -- 公共 API ----------------------------------------------------------
    def vision_resolve(self, screenshot_bytes: bytes,
                       query: str) -> Optional[Dict[str, Any]]:
        """对截图识别 query 指定的 UI 元素，返回原图像素空间坐标。

        返回 {x, y, label, confidence} 或 None（降级）。
        """
        # 1) 降级铁律：无 key / mock → 零 LLM 依赖，直接返回 None（不编造坐标）。
        if self.config.mock or not self.config.api_key:
            return None

        # 2) 加载原图（lazy import PIL，仅真实路径触达）
        try:
            orig = _load_image(screenshot_bytes)
        except Exception:
            return None
        ow, oh = orig.size

        # 3) AC5 脱敏前置：发送给视觉模型的图先打码（像素已变，但几何尺寸通常不变）
        try:
            masked = self.observer.mask_sensitive_regions(orig)
        except Exception:
            return None
        mw, mh = masked.size

        # 4) 获取视觉 client（OpenAIClient.vision_locate / 注入 stub / MockLLMClient）
        client = self._llm if self._llm is not None else self._make_client()
        if client is None or not hasattr(client, "vision_locate"):
            # MockLLMClient 无 vision_locate → 降级（mock 路径由降级覆盖）
            return None

        # 5) 多模态识别（在打码图空间返回坐标）；异常 → 受控降级 None
        try:
            masked_b64 = base64.b64encode(_pil_to_bytes(masked)).decode("ascii")
            loc = client.vision_locate(masked_b64, query)
        except Exception:
            return None
        if not loc:
            return None

        # 6) mask→remap：把打码图空间坐标映射回原图像素空间（consensus CV5）
        try:
            sx = ow / mw
            sy = oh / mh
            x = int(round(float(loc["x"]) * sx))
            y = int(round(float(loc["y"]) * sy))
        except (KeyError, TypeError, ZeroDivisionError):
            return None

        return {
            "x": x,
            "y": y,
            "label": str(loc.get("label", "")),
            "confidence": float(loc.get("confidence", 1.0)),
        }

    # -- 内部 --------------------------------------------------------------
    def _make_client(self):
        try:
            return self.config.make_llm_client()
        except Exception:
            return None
