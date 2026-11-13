import tkinter as tk
import customtkinter as ctk

def format_speed(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.2f} MB/s"

class TrafficGraph(ctk.CTkFrame):
    """
    High-performance real-time waveform traffic graph widget
    drawn with smooth Canvas lines, area fill, and auto-scaling.
    """
    def __init__(self, master, width=540, height=120, **kwargs):
        super().__init__(master, fg_color="#18181b", corner_radius=10, **kwargs)
        self.width = width
        self.height = height

        self.canvas = tk.Canvas(
            self,
            width=width,
            height=height,
            bg="#18181b",
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)

        # Draw initial empty grid
        self._draw_grid(100 * 1024)

    def _draw_grid(self, max_val: float):
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or self.width
        h = self.canvas.winfo_height() or self.height

        # Grid lines
        for ratio in [0.25, 0.5, 0.75]:
            y = h - (h * ratio)
            self.canvas.create_line(0, y, w, y, fill="#27272a", dash=(2, 4))

        # Max Speed Label
        max_str = format_speed(max_val)
        self.canvas.create_text(10, 12, text=f"Đỉnh: {max_str}", fill="#71717a", anchor="w", font=("Segoe UI", 9))

        # Legend
        self.canvas.create_text(w - 150, 12, text="■ Tải xuống", fill="#38bdf8", anchor="w", font=("Segoe UI", 9, "bold"))
        self.canvas.create_text(w - 75, 12, text="■ Tải lên", fill="#f59e0b", anchor="w", font=("Segoe UI", 9, "bold"))

    def update_graph(self, down_history: list, up_history: list):
        """Redraws the graph with updated rolling history."""
        if not down_history or not up_history:
            return

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            w, h = self.width, self.height

        # Compute dynamic max value (with minimum baseline of 50 KB/s)
        peak = max(max(down_history), max(up_history), 50 * 1024)
        max_val = peak * 1.15  # Add 15% headroom

        self._draw_grid(max_val)

        n = len(down_history)
        if n < 2:
            return

        dx = w / (n - 1)

        # 1. Draw Download Filled Polygon & Line
        down_pts = []
        for i, val in enumerate(down_history):
            x = i * dx
            y = h - (val / max_val) * (h - 20)
            down_pts.extend([x, y])

        # Fill area below download line
        poly_pts = [0, h] + down_pts + [w, h]
        self.canvas.create_polygon(poly_pts, fill="#082f49", outline="")
        self.canvas.create_line(down_pts, fill="#38bdf8", width=2, smooth=True)

        # 2. Draw Upload Line
        up_pts = []
        for i, val in enumerate(up_history):
            x = i * dx
            y = h - (val / max_val) * (h - 20)
            up_pts.extend([x, y])

        self.canvas.create_line(up_pts, fill="#f59e0b", width=2, smooth=True)
