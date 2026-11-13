import os
from PIL import Image, ImageDraw, ImageFont
import customtkinter as ctk

try:
    import win32gui
    import win32ui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

class IconManager:
    _cache = {}       # {exe_name_lower: CTkImage}
    _path_cache = {}  # {exe_name_lower: full_path}

    @classmethod
    def register_path(cls, exe_name: str, exe_path: str):
        """Caches full exe path directly without scanning process list."""
        if exe_name and exe_path and os.path.exists(exe_path):
            cls._path_cache[exe_name.lower()] = exe_path

    @classmethod
    def extract_win_icon(cls, file_path: str, size: int = 22) -> Image.Image:
        """Extracts native HICON from Windows .exe using pywin32."""
        if not HAS_WIN32 or not file_path or not os.path.exists(file_path):
            return None
        try:
            large, small = win32gui.ExtractIconEx(file_path, 0)
            hicon = small[0] if small else (large[0] if large else None)
            if not hicon:
                return None

            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, size, size)
            memdc = hdc.CreateCompatibleDC()
            memdc.SelectObject(hbmp)

            win32gui.DrawIconEx(memdc.GetSafeHdc(), 0, 0, hicon, size, size, 0, 0, win32con.DI_NORMAL)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)

            # Cleanup handles
            if small:
                for h in small: win32gui.DestroyIcon(h)
            if large:
                for h in large: win32gui.DestroyIcon(h)
            win32gui.DeleteObject(hbmp.GetHandle())
            memdc.DeleteDC()
            hdc.DeleteDC()
            return img
        except Exception:
            return None

    @classmethod
    def generate_fallback_icon(cls, name: str, size: int = 22) -> Image.Image:
        """Generates a sleek, high-quality modern badge icon with initial letter."""
        img = Image.new('RGBA', (size * 2, size * 2), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        colors = [
            ("#6366f1", "#4338ca"),  # Indigo
            ("#06b6d4", "#0891b2"),  # Cyan
            ("#10b981", "#059669"),  # Emerald
            ("#f59e0b", "#d97706"),  # Amber
            ("#ec4899", "#db2777"),  # Pink
            ("#8b5cf6", "#7c3aed"),  # Purple
        ]
        color_idx = sum(ord(c) for c in name) % len(colors)
        fill_col, stroke_col = colors[color_idx]

        draw.rounded_rectangle([(2, 2), (size * 2 - 2, size * 2 - 2)], radius=10, fill=fill_col, outline=stroke_col, width=2)

        letter = name[0].upper() if name else "?"
        try:
            font = ImageFont.truetype("seguiemj.ttf", size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), letter, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size * 2 - text_w) / 2
        y = (size * 2 - text_h) / 2 - 2
        draw.text((x, y), letter, fill="#ffffff", font=font)

        return img.resize((size, size), Image.Resampling.LANCZOS)

    @classmethod
    def get_app_icon(cls, exe_name: str, exe_path: str = None, size: int = 22) -> ctk.CTkImage:
        """Returns cached CTkImage for process with zero CPU overhead."""
        name_lower = exe_name.lower()
        if name_lower in cls._cache:
            return cls._cache[name_lower]

        if exe_path:
            cls.register_path(name_lower, exe_path)

        path = cls._path_cache.get(name_lower)
        img = None
        if path:
            img = cls.extract_win_icon(path, size=size)

        if not img:
            img = cls.generate_fallback_icon(exe_name, size=size)

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        cls._cache[name_lower] = ctk_img
        return ctk_img
