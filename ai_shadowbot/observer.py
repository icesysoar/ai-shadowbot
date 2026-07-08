"""观测层（F002 截图） —— 屏幕采集，返回 base64 PNG 供 LLM 视觉观测。

真实模式 lazy import pyautogui + PIL；无显示/无库时抛清晰错误，不影响 dry_run。
对应架构的"眼睛"：截图是 planner 视觉闭环（AC4）的输入。

架构说明（T002.6 混合感知）：
  MVP 先用「截图」作为唯一观测源（主理人裁决 + 共识报告：先 Windows、MVP 收窄）。
  后续接 pywinauto/UIAutomation 的无障碍树，形成「无障碍树(语义锚定) + 截图(视觉兜底)」
  混合感知；届时本模块扩展 capture_with_tree() 即可，接口保持不变。

隐私脱敏（T003.6 / AC5）：
  SCREEN_MASK_SENSITIVE=true（或 Observer(screen_mask_sensitive=True)）时，截图外发前对
  敏感区做确定性马赛克打码（mask_sensitive_regions）。MVP 无敏感区检测器时默认对整图打码
  （隐私优先于可用性）；若提供 regions 则只打码指定矩形（密码框/金额/聊天区）。
"""
from __future__ import annotations

import base64
import io
from typing import List, Optional, Tuple

# 敏感区矩形：(x, y, w, h)
Region = Tuple[int, int, int, int]


class Observer:
    def __init__(self, screen_mask_sensitive: bool = False) -> None:
        self.screen_mask_sensitive = screen_mask_sensitive
        self._last_b64: Optional[str] = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def screenshot(self, mask_sensitive: Optional[bool] = None,
                   _image: Optional["object"] = None) -> str:
        """对当前屏幕截图，返回 base64 PNG 字符串。

        mask_sensitive: 是否对敏感区打码后再外发（AC5 隐私脱敏）。
        _image: 测试注入用——直接传入 PIL.Image，跳过真实屏幕抓取（无需显示环境）。
        """
        mask = mask_sensitive if mask_sensitive is not None else self.screen_mask_sensitive
        if _image is not None:
            img = _image
        else:
            try:
                import pyautogui
                from PIL import Image  # type: ignore
            except Exception as e:
                raise RuntimeError(f"截图依赖不可用（需 pyautogui + Pillow）：{e}")
            img = pyautogui.screenshot()
        if mask:
            img = self.mask_sensitive_regions(img)
        b64 = self._image_to_base64(img)
        self._last_b64 = b64
        return b64

    def last_screenshot(self) -> Optional[str]:
        return self._last_b64

    # ------------------------------------------------------------------
    # 脱敏打码（确定性、可复现，便于测试断言）
    # ------------------------------------------------------------------
    @staticmethod
    def mask_sensitive_regions(image: "object",
                               regions: Optional[List[Region]] = None) -> "object":
        """对图像做马赛克打码，返回新图像。

        regions 为空 → 对整图打码（隐私优先，MVP 默认）。
        regions 非空 → 仅对指定矩形区域打码（密码框/金额/聊天区）。
        使用 NEAREST 最近邻缩放，结果确定性可复现。
        """
        from PIL import Image  # type: ignore

        img = image.convert("RGB")
        if not regions:
            w, h = img.size
            # 整图像素化：缩小 12 倍再放大
            small = img.resize((max(1, w // 12), max(1, h // 12)), Image.BILINEAR)
            return small.resize((w, h), Image.NEAREST)

        out = img.copy()
        for (x, y, w, h) in regions:
            x, y, w, h = int(x), int(y), int(w), int(h)
            box = (x, y, x + w, y + h)
            crop = out.crop(box)
            cw, ch = crop.size
            small = crop.resize((max(1, cw // 10), max(1, ch // 10)), Image.BILINEAR)
            pixelated = small.resize((cw, ch), Image.NEAREST)
            out.paste(pixelated, (x, y))
        return out

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _image_to_base64(img: "object") -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
