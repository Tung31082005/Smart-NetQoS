import os
import sys
import threading
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import pystray
from pystray import MenuItem as item

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.append(APP_DIR)

from qos_service import QoSService
from net_monitor import NetworkMonitor
from traffic_graph import TrafficGraph
from config_manager import ConfigManager
from icon_manager import IconManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

ICON_PATH = os.path.join(APP_DIR, "assets", "icon.ico")
ICON_PNG = os.path.join(APP_DIR, "assets", "icon.png")
LAUNCHER_VBS = os.path.join(APP_DIR, "launcher.vbs")

def ensure_admin():
    """Checks admin privilege; QoSService auto-elevates policy modifications on-the-fly."""
    pass

class SocketInspectorDialog(ctk.CTkToplevel):
    """Popup modal showing detailed remote IPs and ports for an application."""
    def __init__(self, master, app_name: str, pids: list):
        super().__init__(master)
        self.title(f"Chi tiết kết nối mạng - {app_name}")
        self.geometry("520x400")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        
        x = master.winfo_x() + 50
        y = master.winfo_y() + 80
        self.geometry(f"+{x}+{y}")

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(16, 6))

        app_icon = IconManager.get_app_icon(app_name, size=24)
        ctk.CTkLabel(header_frame, text="", image=app_icon).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            header_frame, 
            text=f"Kết Nối Đang Mở: {app_name}", 
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        scroll = ctk.CTkScrollableFrame(self, fg_color="#18181b")
        scroll.pack(fill="both", expand=True, padx=16, pady=8)

        all_conns = []
        for pid in pids:
            conns = NetworkMonitor.get_process_socket_details(pid)
            all_conns.extend(conns)

        if not all_conns:
            ctk.CTkLabel(scroll, text="Không có kết nối ngoài nào đang mở.", text_color="#71717a").pack(pady=35)
        else:
            for c in all_conns:
                card = ctk.CTkFrame(scroll, fg_color="#27272a", corner_radius=6)
                card.pack(fill="x", pady=2, padx=2)
                ctk.CTkLabel(card, text=f"Đích: {c['raddr']}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=8, pady=(4, 0))
                ctk.CTkLabel(card, text=f"Nội bộ: {c['laddr']}  |  Trạng thái: {c['status']}", font=ctk.CTkFont(size=10), text_color="#94a3b8").pack(anchor="w", padx=8, pady=(0, 4))

        ctk.CTkButton(self, text="Đóng", width=100, height=28, command=self.destroy).pack(pady=(4, 12))


class SmartNetQoSApp(ctk.CTk):
    def __init__(self, start_minimized: bool = False):
        super().__init__()

        self.title("Smart NetQoS Manager - Giám Sát & Phân Luồng")
        self.width = 620
        self.height = 850
        self.minsize(560, 720)
        
        self.config = ConfigManager.load_config()
        self.is_pinned = self.config.get("always_on_top", False)
        self.attributes("-topmost", self.is_pinned)

        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception:
                pass

        self._position_window_smartly()

        self.monitor = NetworkMonitor(history_len=self.config.get("history_seconds", 45))
        self.vip_policies = QoSService.get_vip_policies()
        self.net_conn = QoSService.get_network_connection_status()
        self.active_mode = self.config.get("active_mode", "ai")
        self.is_running = True
        self.tray_icon = None
        self.active_filter = self.config.get("last_filter", "ALL")
        self.search_query = ""
        self.hotkey_tid = None
        self.last_procs = []

        self._build_ui()
        self._init_tray()
        self._update_mode_buttons_ui(self.active_mode)

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self.ping_thread.start()

        self.hotkey_thread = threading.Thread(target=self._hotkey_loop, daemon=True)
        self.hotkey_thread.start()

        if start_minimized or self.config.get("start_minimized", False):
            self.withdraw()

    def _position_window_smartly(self):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(screen_w - self.width - 24, 40)
        y = max(screen_h - self.height - 70, 40)
        self.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _build_ui(self):
        header = ctk.CTkFrame(self, fg_color="#18181b", corner_radius=12)
        header.pack(fill="x", padx=16, pady=(14, 6))

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(fill="x", padx=14, pady=10)

        title_lbl = ctk.CTkLabel(
            title_box, 
            text="⚡ Smart NetQoS Manager", 
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#f4f4f5"
        )
        title_lbl.pack(side="left")

        right_badges = ctk.CTkFrame(title_box, fg_color="transparent")
        right_badges.pack(side="right")

        self.pin_btn = ctk.CTkButton(
            right_badges,
            text="📌 Ghim" if not self.is_pinned else "📍 Đã ghim",
            width=65, height=26,
            fg_color="#312e81" if self.is_pinned else "#27272a",
            hover_color="#3730a3",
            font=ctk.CTkFont(size=10, weight="bold"),
            corner_radius=6,
            command=self._toggle_pin
        )
        self.pin_btn.pack(side="left", padx=(0, 6))

        self.ping_badge = ctk.CTkLabel(
            right_badges,
            text="🟢 Ping: -- ms",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1e293b",
            text_color="#38bdf8",
            corner_radius=6,
            padx=8, pady=3
        )
        self.ping_badge.pack(side="left", padx=(0, 6))

        self.net_badge = ctk.CTkLabel(
            right_badges,
            text=self.net_conn["badge"],
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=self.net_conn["bg"],
            text_color=self.net_conn["color"],
            corner_radius=6,
            padx=8, pady=3
        )
        self.net_badge.pack(side="left")

        # 2. Live Traffic Waveform Graph
        self.graph = TrafficGraph(self, width=580, height=115)
        self.graph.pack(fill="x", padx=16, pady=4)

        # 3. Recalibrated Presets Bar
        preset_frame = ctk.CTkFrame(self, fg_color="transparent")
        preset_frame.pack(fill="x", padx=16, pady=(6, 4))

        ctk.CTkLabel(
            preset_frame, text="Chế độ:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa"
        ).pack(side="left", padx=(4, 8))

        self.btn_mode_ai = ctk.CTkButton(
            preset_frame, text="⚡ AI Dev Mode", width=125, height=32,
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=7,
            command=lambda: self._select_mode("ai")
        )
        self.btn_mode_ai.pack(side="left", padx=4)

        self.btn_mode_gaming = ctk.CTkButton(
            preset_frame, text="🎮 Gaming Mode", width=125, height=32,
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=7,
            command=lambda: self._select_mode("gaming")
        )
        self.btn_mode_gaming.pack(side="left", padx=4)

        self.btn_mode_download = ctk.CTkButton(
            preset_frame, text="🚀 Max Download", width=125, height=32,
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=7,
            command=lambda: self._select_mode("download")
        )
        self.btn_mode_download.pack(side="left", padx=4)

        # 4. Search & Filter Bar
        search_frame = ctk.CTkFrame(self, fg_color="#27272a", corner_radius=8)
        search_frame.pack(fill="x", padx=16, pady=6)

        self.search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="🔍 Tìm kiếm app đang chạy...", height=32, corner_radius=6
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(8, 6), pady=6)
        self.search_entry.bind("<KeyRelease>", self._on_search_change)

        self.btn_filter_all = ctk.CTkButton(
            search_frame, text="Tất cả", width=55, height=30, 
            fg_color="#4f46e5" if self.active_filter == "ALL" else "#3f3f46", corner_radius=6,
            command=lambda: self._set_filter("ALL")
        )
        self.btn_filter_all.pack(side="left", padx=2)

        self.btn_filter_vip = ctk.CTkButton(
            search_frame, text="VIP", width=50, height=30, 
            fg_color="#4f46e5" if self.active_filter == "VIP" else "#3f3f46", corner_radius=6,
            command=lambda: self._set_filter("VIP")
        )
        self.btn_filter_vip.pack(side="left", padx=2)

        self.btn_filter_active = ctk.CTkButton(
            search_frame, text="Có mạng", width=65, height=30, 
            fg_color="#4f46e5" if self.active_filter == "ACTIVE" else "#3f3f46", corner_radius=6,
            command=lambda: self._set_filter("ACTIVE")
        )
        self.btn_filter_active.pack(side="left", padx=(2, 8))

        # 5. Quick Add App Input
        add_frame = ctk.CTkFrame(self, fg_color="transparent")
        add_frame.pack(fill="x", padx=16, pady=2)

        self.add_entry = ctk.CTkEntry(
            add_frame, placeholder_text="Nhập tên .exe để thêm VIP (vd: discord.exe)...", height=32, corner_radius=6
        )
        self.add_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            add_frame, text="+ Thêm VIP", width=85, height=32, fg_color="#6366f1", hover_color="#4f46e5",
            font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6, command=self._on_add_vip
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            add_frame, text="📁 Chọn File", width=75, height=32, fg_color="#3f3f46", hover_color="#52525b",
            font=ctk.CTkFont(size=11), corner_radius=6, command=self._on_browse_file
        ).pack(side="right")

        # 6. Scrollable Process List
        self.proc_scroll = ctk.CTkScrollableFrame(self, fg_color="#18181b", corner_radius=10)
        self.proc_scroll.pack(fill="both", expand=True, padx=16, pady=6)

        # 7. Status Toast Bar
        self.toast_lbl = ctk.CTkLabel(
            self, text="⚡ Đang chạy chế độ: " + self._get_mode_desc(self.active_mode), 
            font=ctk.CTkFont(size=11), text_color="#10b981"
        )
        self.toast_lbl.pack(fill="x", padx=18, pady=(2, 2))

        # 8. Footer Frame
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(2, 12))

        is_autostart = QoSService.get_autostart_status()
        self.autostart_switch = ctk.CTkSwitch(
            footer, text="Khởi động cùng Windows", font=ctk.CTkFont(size=11),
            command=self._on_autostart_toggle
        )
        if is_autostart:
            self.autostart_switch.select()
        self.autostart_switch.pack(side="left")

        ctk.CTkButton(
            footer, text="Ẩn vào khay", width=110, height=30, fg_color="#3f3f46", hover_color="#52525b",
            font=ctk.CTkFont(size=11), corner_radius=6, command=self.hide_to_tray
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            footer, text="🔄 Đặt lại mặc định", width=125, height=30, fg_color="#dc2626", hover_color="#b91c1c",
            font=ctk.CTkFont(size=11), corner_radius=6, command=self._on_restore_defaults
        ).pack(side="right")

        self.row_widgets = {}

    def _get_mode_desc(self, mode: str) -> str:
        descs = {
            "ai": "⚡ AI Dev Mode (Ưu tiên Antigravity, Chrome, Node, Python)",
            "gaming": "🎮 Gaming Mode (Ưu tiên Game, Discord, Siêu thấp ping)",
            "download": "🚀 Max Download (Mở van 100% cho IDM, Torrent, Steam)",
            "custom": "🔧 Tùy chỉnh cá nhân"
        }
        return descs.get(mode, "Tùy chỉnh")

    def _get_mode_short_title(self, mode: str) -> str:
        titles = {
            "ai": "⚡ AI Dev Mode",
            "gaming": "🎮 Gaming Mode",
            "download": "🚀 Max Download",
            "custom": "🔧 Tùy chỉnh"
        }
        return titles.get(mode, "Tùy chỉnh")

    def _update_mode_buttons_ui(self, mode: str):
        if mode == "ai":
            self.btn_mode_ai.configure(
                text="● ⚡ AI Dev Mode", fg_color="#4f46e5", hover_color="#4338ca",
                border_width=2, border_color="#818cf8", text_color="#ffffff"
            )
        else:
            self.btn_mode_ai.configure(
                text="⚡ AI Dev Mode", fg_color="#27272a", hover_color="#3f3f46",
                border_width=0, text_color="#a1a1aa"
            )

        if mode == "gaming":
            self.btn_mode_gaming.configure(
                text="● 🎮 Gaming Mode", fg_color="#059669", hover_color="#047857",
                border_width=2, border_color="#34d399", text_color="#ffffff"
            )
        else:
            self.btn_mode_gaming.configure(
                text="🎮 Gaming Mode", fg_color="#27272a", hover_color="#3f3f46",
                border_width=0, text_color="#a1a1aa"
            )

        if mode == "download":
            self.btn_mode_download.configure(
                text="● 🚀 Max Download", fg_color="#d97706", hover_color="#b45309",
                border_width=2, border_color="#fbbf24", text_color="#ffffff"
            )
        else:
            self.btn_mode_download.configure(
                text="🚀 Max Download", fg_color="#27272a", hover_color="#3f3f46",
                border_width=0, text_color="#a1a1aa"
            )

    def _select_mode(self, mode: str, show_notification: bool = True):
        self.active_mode = mode
        self.config["active_mode"] = mode
        ConfigManager.save_config(self.config)
        self._update_mode_buttons_ui(mode)

        if self.tray_icon:
            try:
                self.tray_icon.update_menu()
                if show_notification:
                    self.tray_icon.notify(
                        self._get_mode_desc(mode),
                        f"Đã chuyển sang {self._get_mode_short_title(mode)}"
                    )
            except Exception:
                pass

        def task():
            QoSService.apply_preset(mode)
            self.vip_policies = QoSService.get_vip_policies()
            desc = self._get_mode_desc(mode)
            self.after(0, self._force_refresh_ui)
            self.after(0, lambda: self.show_toast(f"✓ Đã kích hoạt: {desc}!", "#34d399"))

        threading.Thread(target=task, daemon=True).start()

    def show_toast(self, message: str, color: str = "#10b981"):
        self.toast_lbl.configure(text=message, text_color=color)
        def reset():
            time.sleep(3.5)
            if self.is_running:
                self.after(0, lambda: self.toast_lbl.configure(
                    text="⚡ Đang chạy chế độ: " + self._get_mode_desc(self.active_mode), 
                    text_color="#10b981"
                ))
        threading.Thread(target=reset, daemon=True).start()

    def _toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.attributes("-topmost", self.is_pinned)
        self.pin_btn.configure(
            text="📌 Ghim" if not self.is_pinned else "📍 Đã ghim",
            fg_color="#312e81" if self.is_pinned else "#27272a"
        )
        self.config["always_on_top"] = self.is_pinned
        ConfigManager.save_config(self.config)

    def _build_tray_menu(self):
        return pystray.Menu(
            item("⚡ Mở Trình Quản Lý Mạng", self.show_from_tray, default=True),
            pystray.Menu.SEPARATOR,
            item(
                "⚡ Chế độ AI Dev Mode",
                lambda icon, it: self._select_mode("ai"),
                checked=lambda it: self.active_mode == "ai",
                radio=True
            ),
            item(
                "🎮 Chế độ Gaming Mode",
                lambda icon, it: self._select_mode("gaming"),
                checked=lambda it: self.active_mode == "gaming",
                radio=True
            ),
            item(
                "🚀 Chế độ Max Download",
                lambda icon, it: self._select_mode("download"),
                checked=lambda it: self.active_mode == "download",
                radio=True
            ),
            pystray.Menu.SEPARATOR,
            item("🔄 Đặt Lại Mặc Định", self._on_restore_defaults),
            pystray.Menu.SEPARATOR,
            item("❌ Thoát Ứng Dụng", self.quit_app)
        )

    def _init_tray(self):
        if not os.path.exists(ICON_PNG):
            return

        tray_img = Image.open(ICON_PNG)
        self.tray_icon = pystray.Icon(
            "SmartNetQoS", 
            tray_img, 
            "Smart NetQoS Manager - Giám Sát & Phân Luồng", 
            self._build_tray_menu()
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.withdraw()

    def show_from_tray(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _toggle_window_visibility(self):
        if self.state() == "withdrawn":
            self._restore_window()
        else:
            self.hide_to_tray()

    def quit_app(self, icon=None, item=None):
        self.is_running = False
        if self.tray_icon:
            self.tray_icon.stop()
        if self.hotkey_tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(self.hotkey_tid, 0x0012, 0, 0)
            except Exception:
                pass
        self.after(0, self.destroy)

    def _hotkey_loop(self):
        """Zero-CPU blocking Win32 message loop for Global Hotkeys."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.hotkey_tid = kernel32.GetCurrentThreadId()

        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        MOD_NOREPEAT = 0x4000

        user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x31)
        user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x32)
        user32.RegisterHotKey(None, 3, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x33)
        user32.RegisterHotKey(None, 4, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x51)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if not self.is_running:
                break
            if msg.message == 0x0312:
                hid = msg.wParam
                if hid == 1:
                    self.after(0, lambda: self._select_mode("ai"))
                elif hid == 2:
                    self.after(0, lambda: self._select_mode("gaming"))
                elif hid == 3:
                    self.after(0, lambda: self._select_mode("download"))
                elif hid == 4:
                    self.after(0, self._toggle_window_visibility)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, 1)
        user32.UnregisterHotKey(None, 2)
        user32.UnregisterHotKey(None, 3)
        user32.UnregisterHotKey(None, 4)

    def _ping_loop(self):
        while self.is_running:
            is_visible = (self.state() != "withdrawn")
            sleep_time = 4.0 if is_visible else 12.0

            if is_visible:
                ms = NetworkMonitor.measure_ping("1.1.1.1", 53)
                if ms > 0:
                    color = "#34d399" if ms < 50 else ("#fbbf24" if ms < 100 else "#f87171")
                    bg = "#064e3b" if ms < 50 else ("#451a03" if ms < 100 else "#450a0a")
                    text = f"🟢 Ping: {ms} ms"
                else:
                    color = "#f87171"
                    bg = "#450a0a"
                    text = "🔴 Mất kết nối"
                
                self.after(0, self._update_ping_badge, text, color, bg)

            time.sleep(sleep_time)

    def _update_ping_badge(self, text, fg, bg):
        self.ping_badge.configure(text=text, text_color=fg, fg_color=bg)

    def _monitor_loop(self):
        counter = 0
        while self.is_running:
            try:
                is_visible = (self.state() != "withdrawn")

                if not is_visible:
                    self.monitor.get_system_bandwidth()
                    time.sleep(3.0)
                    continue

                bw = self.monitor.get_system_bandwidth()
                vip_set = set(self.vip_policies.keys())
                procs = self.monitor.get_process_network_list(vip_set)
                self.last_procs = procs

                # Check connection type (LAN vs Wi-Fi) occasionally
                if counter % 10 == 0:
                    self.net_conn = QoSService.get_network_connection_status()

                self.after(0, self._update_ui_data, bw, procs, len(vip_set))
                counter += 1
                time.sleep(1.5)
            except Exception:
                time.sleep(2.0)

    def _force_refresh_ui(self):
        vip_set = set(self.vip_policies.keys())
        for exe, row in list(self.row_widgets.items()):
            is_vip = exe.lower() in vip_set
            row["is_vip"] = is_vip
            row["frame"].configure(fg_color="#1e1b4b" if is_vip else "#27272a")
            row["btn"].configure(
                text="⭐ VIP" if is_vip else "Đặt VIP",
                fg_color="#6366f1" if is_vip else "#3f3f46",
                hover_color="#4f46e5" if is_vip else "#52525b"
            )

    def _update_ui_data(self, bw, procs, vip_count):
        self.graph.update_graph(bw["history_down"], bw["history_up"])
        self.net_badge.configure(
            text=self.net_conn["badge"],
            fg_color=self.net_conn["bg"],
            text_color=self.net_conn["color"]
        )

        filtered = []
        q = self.search_query.lower()
        for p in procs:
            if q and q not in p["name"].lower():
                continue
            if self.active_filter == "VIP" and not p["is_vip"]:
                continue
            if self.active_filter == "ACTIVE" and p["connections"] == 0:
                continue
            filtered.append(p)

        display_procs = filtered[:25]
        current_exes = {p["exe"] for p in display_procs}

        for exe in list(self.row_widgets.keys()):
            if exe not in current_exes:
                self.row_widgets[exe]["frame"].destroy()
                del self.row_widgets[exe]

        for p in display_procs:
            exe = p["exe"]
            is_vip = p["is_vip"]

            if exe not in self.row_widgets:
                row_frame = ctk.CTkFrame(self.proc_scroll, fg_color="#1e1b4b" if is_vip else "#27272a", corner_radius=8)
                row_frame.pack(fill="x", pady=2, padx=2)

                app_icon = IconManager.get_app_icon(exe, size=24)
                icon_lbl = ctk.CTkLabel(row_frame, text="", image=app_icon, width=28)
                icon_lbl.pack(side="left", padx=(10, 2), pady=6)

                info_col = ctk.CTkFrame(row_frame, fg_color="transparent")
                info_col.pack(side="left", fill="x", expand=True, padx=4, pady=6)

                name_lbl = ctk.CTkLabel(
                    info_col, text=f"{p['name']} 🔍", font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#f4f4f5", cursor="hand2"
                )
                name_lbl.pack(anchor="w")
                name_lbl.bind("<Button-1>", lambda e, name=p['name'], pids=p['pids']: self._open_socket_inspector(name, pids))

                stats_lbl = ctk.CTkLabel(
                    info_col, 
                    text=f"Sockets: {p['connections']} kết nối | Lưu lượng: {p['io_str']}", 
                    font=ctk.CTkFont(size=10), text_color="#94a3b8"
                )
                stats_lbl.pack(anchor="w")

                btn = ctk.CTkButton(
                    row_frame,
                    text="⭐ VIP" if is_vip else "Đặt VIP",
                    width=80, height=28,
                    fg_color="#6366f1" if is_vip else "#3f3f46",
                    hover_color="#4f46e5" if is_vip else "#52525b",
                    font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                    command=lambda e=exe: self._toggle_vip(e)
                )
                btn.pack(side="right", padx=10, pady=6)

                self.row_widgets[exe] = {
                    "frame": row_frame,
                    "name_lbl": name_lbl,
                    "stats_lbl": stats_lbl,
                    "btn": btn,
                    "is_vip": is_vip,
                    "pids": p["pids"]
                }
            else:
                row = self.row_widgets[exe]
                row["frame"].configure(fg_color="#1e1b4b" if is_vip else "#27272a")
                row["stats_lbl"].configure(text=f"Sockets: {p['connections']} kết nối | Lưu lượng: {p['io_str']}")
                row["pids"] = p["pids"]
                
                if row["is_vip"] != is_vip:
                    row["is_vip"] = is_vip
                    row["btn"].configure(
                        text="⭐ VIP" if is_vip else "Đặt VIP",
                        fg_color="#6366f1" if is_vip else "#3f3f46",
                        hover_color="#4f46e5" if is_vip else "#52525b"
                    )

        # Dynamic Task Manager Re-ordering:
        # Repack widgets in exact sorted order so the app actively transferring the most bandwidth JUMPS TO TOP!
        for p in display_procs:
            exe = p["exe"]
            if exe in self.row_widgets:
                frame = self.row_widgets[exe]["frame"]
                frame.pack_forget()
                frame.pack(fill="x", pady=2, padx=2)

    def _open_socket_inspector(self, name, pids):
        SocketInspectorDialog(self, name, pids)

    def _set_filter(self, filter_type):
        self.active_filter = filter_type
        self.config["last_filter"] = filter_type
        ConfigManager.save_config(self.config)
        self.btn_filter_all.configure(fg_color="#4f46e5" if filter_type == "ALL" else "#3f3f46")
        self.btn_filter_vip.configure(fg_color="#4f46e5" if filter_type == "VIP" else "#3f3f46")
        self.btn_filter_active.configure(fg_color="#4f46e5" if filter_type == "ACTIVE" else "#3f3f46")

    def _on_search_change(self, event):
        self.search_query = self.search_entry.get().strip()

    def _toggle_vip(self, exe: str):
        exe_lower = exe.lower()
        is_vip_now = (exe_lower in self.vip_policies)

        self.active_mode = "custom"
        self._update_mode_buttons_ui("custom")
        if self.tray_icon:
            try: self.tray_icon.update_menu()
            except Exception: pass

        def task():
            if is_vip_now:
                success = QoSService.remove_vip_app(exe)
                msg = f"✓ Đã gỡ cờ VIP cho {exe}" if success else f"❌ Không thể gỡ VIP cho {exe} (Thiếu quyền Admin)"
            else:
                success = QoSService.add_vip_app(exe)
                msg = f"✓ Đã cấp làn ưu tiên VIP cho {exe}!" if success else f"❌ Không thể cấp VIP cho {exe} (Thiếu quyền Admin)"
            
            self.vip_policies = QoSService.get_vip_policies()
            self.after(0, self._force_refresh_ui)
            self.after(0, lambda: self.show_toast(msg, "#10b981" if success else "#ef4444"))

        threading.Thread(target=task, daemon=True).start()

    def _on_add_vip(self):
        exe = self.add_entry.get().strip()
        if not exe:
            messagebox.showwarning("Thông báo", "Vui lòng nhập tên file thực thi (.exe)!")
            return

        self.active_mode = "custom"
        self._update_mode_buttons_ui("custom")
        if self.tray_icon:
            try: self.tray_icon.update_menu()
            except Exception: pass

        def task():
            success = QoSService.add_vip_app(exe)
            self.vip_policies = QoSService.get_vip_policies()
            self.after(0, self._force_refresh_ui)
            self.after(0, lambda: self.add_entry.delete(0, "end"))
            if success:
                self.after(0, lambda: self.show_toast(f"✓ Đã thêm {exe} vào danh sách VIP!", "#10b981"))
            else:
                self.after(0, lambda: self.show_toast(f"❌ Không thể thêm {exe} (Thiếu quyền Admin)", "#ef4444"))

        threading.Thread(target=task, daemon=True).start()

    def _on_browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn Ứng Dụng Cần Ưu Tiên VIP",
            filetypes=[("Executable Files", "*.exe")]
        )
        if file_path:
            exe_name = os.path.basename(file_path)
            self.add_entry.delete(0, "end")
            self.add_entry.insert(0, exe_name)
            self._on_add_vip()

    def _on_autostart_toggle(self):
        enable = bool(self.autostart_switch.get())
        QoSService.set_autostart(enable, LAUNCHER_VBS)
        status = "BẬT" if enable else "TẮT"
        self.show_toast(f"✓ Đã {status} tính năng khởi động cùng Windows!")

    def _on_restore_defaults(self, icon=None, item=None):
        confirm = messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa toàn bộ chính sách VIP để khôi phục mặc định?")
        if confirm:
            self.active_mode = "custom"
            self._update_mode_buttons_ui("custom")
            if self.tray_icon:
                try: self.tray_icon.update_menu()
                except Exception: pass
            def task():
                QoSService.restore_defaults()
                self.vip_policies = QoSService.get_vip_policies()
                self.after(0, self._force_refresh_ui)
                self.after(0, lambda: self.show_toast("✓ Đã khôi phục mạng về mặc định!", "#f59e0b"))
            threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    ensure_admin()
    start_min = "--minimized" in sys.argv
    app = SmartNetQoSApp(start_minimized=start_min)
    app.mainloop()
