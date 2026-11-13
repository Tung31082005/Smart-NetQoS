import psutil
import time
import socket
from typing import Dict, List, Any
from collections import deque
from icon_manager import IconManager

def format_speed(bytes_per_sec: float) -> str:
    """Formats bytes/sec into human-readable string."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"

class NetworkMonitor:
    def __init__(self, history_len: int = 45):
        self.last_time = time.time()
        self.last_net_io = psutil.net_io_counters()
        self.last_proc_io = {}  # {pid: (read_bytes, write_bytes, timestamp)}
        self.proc_cache = {}    # {pid: psutil.Process}
        
        self.history_len = history_len
        self.history_down = deque([0.0] * history_len, maxlen=history_len)
        self.history_up = deque([0.0] * history_len, maxlen=history_len)

    def get_system_bandwidth(self) -> Dict[str, Any]:
        """Calculates current system total download and upload rate, updates history."""
        now = time.time()
        dt = max(now - self.last_time, 0.1)
        current_net_io = psutil.net_io_counters()
        
        down_bps = max((current_net_io.bytes_recv - self.last_net_io.bytes_recv) / dt, 0.0)
        up_bps = max((current_net_io.bytes_sent - self.last_net_io.bytes_sent) / dt, 0.0)
        
        self.last_time = now
        self.last_net_io = current_net_io
        
        self.history_down.append(down_bps)
        self.history_up.append(up_bps)
        
        return {
            "down_bps": down_bps,
            "up_bps": up_bps,
            "down_str": format_speed(down_bps),
            "up_str": format_speed(up_bps),
            "history_down": list(self.history_down),
            "history_up": list(self.history_up)
        }

    @staticmethod
    def measure_ping(host: str = "1.1.1.1", port: int = 53, timeout: float = 0.8) -> float:
        """Measures latency in milliseconds via rapid TCP handshake."""
        t0 = time.perf_counter()
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            ms = (time.perf_counter() - t0) * 1000
            s.close()
            return round(ms, 1)
        except Exception:
            return -1.0

    @staticmethod
    def get_process_socket_details(pid: int) -> List[Dict[str, Any]]:
        """Returns active socket details (remote IP, port, status) for a process."""
        details = []
        try:
            proc = psutil.Process(pid)
            for c in proc.net_connections(kind='inet'):
                if c.raddr:
                    details.append({
                        "laddr": f"{c.laddr.ip}:{c.laddr.port}",
                        "raddr": f"{c.raddr.ip}:{c.raddr.port}",
                        "status": c.status
                    })
        except Exception:
            pass
        return details

    def get_process_network_list(self, vip_set: set) -> List[Dict[str, Any]]:
        """
        Ultra-optimized process scanner:
        - ZERO full-system process_iter calls (0% CPU).
        - Queries only active internet connections.
        """
        pid_conns = {}
        try:
            connections = psutil.net_connections(kind='inet')
            for conn in connections:
                if conn.pid:
                    if conn.pid not in pid_conns:
                        pid_conns[conn.pid] = {"count": 0, "established": 0}
                    pid_conns[conn.pid]["count"] += 1
                    if conn.status == psutil.CONN_ESTABLISHED:
                        pid_conns[conn.pid]["established"] += 1
        except Exception:
            pass

        aggregated = {}
        now = time.time()
        
        for pid, stats in pid_conns.items():
            try:
                # Use cached Process instance
                if pid in self.proc_cache:
                    proc = self.proc_cache[pid]
                else:
                    proc = psutil.Process(pid)
                    self.proc_cache[pid] = proc

                name = proc.name()
                name_lower = name.lower()

                # Register path to icon cache once
                if name_lower not in IconManager._path_cache:
                    try:
                        exe_path = proc.exe()
                        IconManager.register_path(name_lower, exe_path)
                    except Exception:
                        pass
                
                io_rate = 0.0
                try:
                    io = proc.io_counters()
                    if pid in self.last_proc_io:
                        old_io, old_t = self.last_proc_io[pid]
                        dt = max(now - old_t, 0.1)
                        io_rate = ((io.read_bytes + io.write_bytes) - (old_io.read_bytes + old_io.write_bytes)) / dt
                    self.last_proc_io[pid] = (io, now)
                except Exception:
                    pass
                
                if name_lower not in aggregated:
                    aggregated[name_lower] = {
                        "name": name,
                        "exe": name_lower,
                        "pids": [pid],
                        "connections": stats["count"],
                        "established": stats["established"],
                        "io_rate": max(io_rate, 0.0),
                        "is_vip": name_lower in vip_set
                    }
                else:
                    aggregated[name_lower]["pids"].append(pid)
                    aggregated[name_lower]["connections"] += stats["count"]
                    aggregated[name_lower]["established"] += stats["established"]
                    aggregated[name_lower]["io_rate"] += max(io_rate, 0.0)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.proc_cache.pop(pid, None)
                continue

        # Add known VIP apps if not in active sockets (without process_iter!)
        for vip_exe in vip_set:
            if vip_exe not in aggregated:
                aggregated[vip_exe] = {
                    "name": vip_exe,
                    "exe": vip_exe,
                    "pids": [],
                    "connections": 0,
                    "established": 0,
                    "io_rate": 0.0,
                    "is_vip": True
                }

        # Cleanup dead pids from cache
        active_pids = set(pid_conns.keys())
        self.proc_cache = {pid: p for pid, p in self.proc_cache.items() if pid in active_pids}
        self.last_proc_io = {pid: v for pid, v in self.last_proc_io.items() if pid in active_pids}

        result = list(aggregated.values())
        for item in result:
            item["io_str"] = format_speed(item["io_rate"])

        # Task Manager Dynamic Sorting:
        # 1. Apps transferring the most data (io_rate > 0) immediately jump to the top!
        # 2. Then by active connections count
        # 3. Then by VIP status
        result.sort(key=lambda x: (
            -x["io_rate"],
            -x["connections"],
            not x["is_vip"],
            x["name"].lower()
        ))
        return result
