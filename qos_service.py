import subprocess
import json
import os
import re
import ctypes
import winreg

class QoSService:
    AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "SmartNetQoSManager"

    @staticmethod
    def is_admin() -> bool:
        """Checks if current process has Administrator elevation."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    @staticmethod
    def run_powershell(script: str) -> subprocess.CompletedProcess:
        """Executes a PowerShell command safely without showing console."""
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

    @classmethod
    def run_powershell_admin(cls, script: str) -> bool:
        """Executes a PowerShell command with Administrator privileges."""
        if cls.is_admin():
            res = cls.run_powershell(script)
            return res.returncode == 0
        
        try:
            import base64
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            elevate_cmd = (
                f"Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait "
                f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}'"
            )
            res = cls.run_powershell(elevate_cmd)
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def get_vip_policies(cls):
        """Returns dict of active VIP QoS policies: {app_exe_lowercase: policy_info}"""
        ps_cmd = """
        $policies = Get-NetQosPolicy | Where-Object { $_.Name -like 'VIP_*' }
        if ($policies) {
            $policies | Select-Object Name, AppPathName, DSCPValue, PriorityValue | ConvertTo-Json -Compress
        }
        """
        res = cls.run_powershell(ps_cmd)
        output = res.stdout.strip()
        if not output:
            return {}

        try:
            data = json.loads(output)
            if isinstance(data, dict):
                data = [data]
            
            result = {}
            for item in data:
                app = item.get("AppPathName", "")
                if app:
                    result[app.lower()] = item
            return result
        except Exception:
            return {}

    @classmethod
    def add_vip_app(cls, exe_name: str, dscp: int = 46, priority: int = 5):
        """Adds or updates a VIP QoS policy for an executable."""
        exe_clean = os.path.basename(exe_name).strip()
        if not exe_clean.lower().endswith(".exe"):
            exe_clean += ".exe"
            
        policy_base = re.sub(r'[^a-zA-Z0-9]', '', os.path.splitext(exe_clean)[0])
        policy_name = f"VIP_{policy_base}"
        
        ps_cmd = f"""
        $ErrorActionPreference = 'Stop'
        Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false -ErrorAction SilentlyContinue
        New-NetQosPolicy -Name '{policy_name}' `
                         -AppPathNameMatchCondition '{exe_clean}' `
                         -DSCPAction {dscp} `
                         -PriorityValue8021Action {priority} `
                         -NetworkProfile All | Out-Null
        """
        return cls.run_powershell_admin(ps_cmd)

    @classmethod
    def remove_vip_app(cls, exe_name: str):
        """Removes a VIP QoS policy."""
        exe_clean = os.path.basename(exe_name).strip().lower()
        policies = cls.get_vip_policies()
        
        target_policy_name = None
        for app_exe, info in policies.items():
            if app_exe == exe_clean or os.path.basename(app_exe) == exe_clean:
                target_policy_name = info.get("Name")
                break
                
        if not target_policy_name:
            policy_base = re.sub(r'[^a-zA-Z0-9]', '', os.path.splitext(exe_clean)[0])
            target_policy_name = f"VIP_{policy_base}"
            
        ps_cmd = f"""
        $ErrorActionPreference = 'Stop'
        Remove-NetQosPolicy -Name '{target_policy_name}' -Confirm:$false
        """
        return cls.run_powershell_admin(ps_cmd)

    @classmethod
    def apply_preset(cls, preset_type: str):
        """
        Recalibrated Presets (batched into a single elevated command):
        - 'ai': Clears clutter, locks VIP for Antigravity, Chrome, Language Server, Node, Python, VS Code, Git.
        - 'gaming': Clears AI/Download clutter, locks VIP for Games, Discord, Steam, Riot.
        - 'download': Focuses 100% throughput on IDM, Torrent, Steam, Epic, Chrome downloaders.
        """
        presets = {
            "ai": [
                "Antigravity.exe", "chrome.exe", "language_server.exe",
                "node.exe", "python.exe", "code.exe", "git.exe"
            ],
            "gaming": [
                "Valorant.exe", "cs2.exe", "LeagueClientUx.exe", "League of Legends.exe",
                "dota2.exe", "GenshinImpact.exe", "Overwatch.exe",
                "Discord.exe", "TeamSpeak.exe", "Steam.exe", "RiotClientServices.exe"
            ],
            "download": [
                "IDMan.exe", "IDMIntegrator64.exe", "qBittorrent.exe",
                "uTorrent.exe", "Steam.exe", "EpicGamesLauncher.exe", "chrome.exe"
            ]
        }
        apps = presets.get(preset_type, [])
        lines = [
            "$ErrorActionPreference = 'SilentlyContinue'",
            "Get-NetQosPolicy -Name 'VIP_*' | Remove-NetQosPolicy -Confirm:$false"
        ]
        for app in apps:
            exe_clean = os.path.basename(app).strip()
            policy_base = re.sub(r'[^a-zA-Z0-9]', '', os.path.splitext(exe_clean)[0])
            policy_name = f"VIP_{policy_base}"
            lines.append(
                f"New-NetQosPolicy -Name '{policy_name}' -AppPathNameMatchCondition '{exe_clean}' "
                f"-DSCPAction 46 -PriorityValue8021Action 5 -NetworkProfile All | Out-Null"
            )
        script = "\n".join(lines)
        return cls.run_powershell_admin(script)

    @classmethod
    def get_network_connection_status(cls):
        """
        Detects active network interface (Ethernet LAN vs Wi-Fi).
        Works seamlessly whether on Ethernet or Wi-Fi!
        """
        # First check physical Ethernet LAN
        ps_cmd = """
        $eth = Get-NetAdapter | Where-Object { 
            ($_.Name -like '*Ethernet*' -or $_.InterfaceDescription -like '*Ethernet*' -or $_.InterfaceDescription -like '*Gigabit*' -or $_.InterfaceDescription -like '*GbE*') -and 
            $_.Status -eq 'Up' -and 
            $_.InterfaceDescription -notlike '*VMware*' -and 
            $_.InterfaceDescription -notlike '*Virtual*' 
        } | Select-Object -First 1 Name, LinkSpeed
        if ($eth) {
            Write-Output "LAN:$($eth.LinkSpeed)"
        }
        """
        res = cls.run_powershell(ps_cmd)
        out = res.stdout.strip()
        if out.startswith("LAN:"):
            speed = out.split(":", 1)[1].strip() or "1 Gbps"
            return {
                "type": "lan",
                "name": "Cáp LAN",
                "badge": f"🔌 Cáp LAN ({speed})",
                "color": "#38bdf8",
                "bg": "#0c4a6e"
            }

        # Otherwise check Wi-Fi
        ps_wifi = "netsh wlan show interfaces"
        res_wifi = cls.run_powershell(ps_wifi)
        ssid = "Wi-Fi"
        link_speed = "N/A"
        for line in res_wifi.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID") and not line.startswith("BSSID"):
                parts = line.split(":", 1)
                if len(parts) == 2: ssid = parts[1].strip()
            elif line.startswith("Receive rate") or line.startswith("Transmit rate"):
                parts = line.split(":", 1)
                if len(parts) == 2 and link_speed == "N/A": 
                    link_speed = parts[1].strip() + " Mbps"

        return {
            "type": "wifi",
            "name": ssid,
            "badge": f"📶 {ssid} ({link_speed})",
            "color": "#34d399",
            "bg": "#064e3b"
        }

    @classmethod
    def restore_defaults(cls):
        """Removes all VIP policies."""
        ps_cmd = "Get-NetQosPolicy -Name 'VIP_*' -ErrorAction SilentlyContinue | Remove-NetQosPolicy -Confirm:$false"
        return cls.run_powershell_admin(ps_cmd)

    @classmethod
    def get_autostart_status(cls) -> bool:
        """Checks if app is registered in Windows Startup."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.AUTOSTART_KEY, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, cls.APP_NAME)
            winreg.CloseKey(key)
            return bool(val)
        except Exception:
            return False

    @classmethod
    def set_autostart(cls, enable: bool, launcher_path: str):
        """Registers or unregisters app in Windows Startup with --minimized flag."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                cmd = f'wscript.exe "{launcher_path}" --minimized' if launcher_path.endswith('.vbs') else f'"{launcher_path}" --minimized'
                winreg.SetValueEx(key, cls.APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, cls.APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            return False
