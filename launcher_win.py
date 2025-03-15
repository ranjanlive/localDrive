# LocalDrive - A file sharing application
# Copyright (C) 2023-2024 Ranjan Developer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import os
import socket
import qrcode
import webbrowser
from PIL import Image, ImageTk
from threading import Thread, Event
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import subprocess
from datetime import datetime
import signal
import platform
import ctypes
import json
import winreg as reg
import requests  # For GitHub API requests
import threading  # For background update check
import re  # For version comparison

# For system tray functionality
import pystray
from pystray import MenuItem as item
from io import BytesIO
from datetime import datetime, timedelta

# Flask imports
from flask import Flask, request, render_template, send_from_directory, jsonify, Response
import shutil
import humanize
import mimetypes
import re
from werkzeug.serving import make_server
import time

# Register signal handlers for clean shutdown globally
def setup_signal_handlers():
    def signal_handler(sig, frame):
        print("\nShutting down server...")
        sys.exit(0)
        
    # Register signal handler for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

# Set up signal handlers when imported
setup_signal_handlers()

# Flask server class to manage the server in the same process
class FlaskServerThread:
    def __init__(self, upload_folder='.'):
        self.upload_folder = os.path.abspath(upload_folder)
        self.server = None
        self.ctx = None
        self.app = None
        self.thread = None
        self.shutdown_event = Event()  # Event to signal shutdown
        self.setup_app()

    def setup_app(self):
        # Determine if we're running as a PyInstaller bundle
        if getattr(sys, 'frozen', False):
            # Get the PyInstaller bundle path
            template_folder = os.path.join(sys._MEIPASS, 'templates')
            static_folder = os.path.join(sys._MEIPASS, 'static')
            self.app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
        else:
            self.app = Flask(__name__)

        self.app.config['UPLOAD_FOLDER'] = self.upload_folder
        
        # Register all the routes
        @self.app.route('/')
        def index():
            path = request.args.get('path', '')
            current_path = os.path.join(self.upload_folder, path.lstrip('/'))
            
            if not os.path.exists(current_path):
                os.makedirs(current_path)
            
            items = []
            for item in os.listdir(current_path):
                # Skip Python files and system files
                if item.startswith('.') or item.endswith('.py') or item == '__pycache__' or item == 'static':
                    continue
                    
                full_path = os.path.join(current_path, item)
                items.append({
                    'name': item,
                    'type': 'folder' if os.path.isdir(full_path) else 'file',
                    'path': os.path.relpath(full_path, self.upload_folder).replace('\\', '/')
                })
            return render_template('index.html', items=items, current_path=path)

        @self.app.route('/create_folder', methods=['POST'])
        def create_folder():
            path = request.form.get('path', '')
            folder_name = request.form.get('name', '')
            new_folder = os.path.join(self.upload_folder, path.lstrip('/'), folder_name)
            if not os.path.exists(new_folder):
                os.makedirs(new_folder)
            return jsonify({'status': 'success'})

        @self.app.route('/rename', methods=['POST'])
        def rename_item():
            old_path = os.path.join(self.upload_folder, request.form.get('old_path', '').lstrip('/'))
            new_name = request.form.get('new_name', '')
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            os.rename(old_path, new_path)
            return jsonify({'status': 'success'})

        @self.app.route('/delete', methods=['POST'])
        def delete_item():
            path = os.path.join(self.upload_folder, request.form.get('path', '').lstrip('/'))
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return jsonify({'status': 'success'})

        @self.app.route('/upload', methods=['POST'])
        def upload_file():
            if 'file' not in request.files:
                return 'No file selected'
            file = request.files['file']
            if file.filename == '':
                return 'No file selected'
            
            # Get current path and create full upload path
            current_path = request.form.get('path', '').lstrip('/')
            upload_path = os.path.join(self.app.config['UPLOAD_FOLDER'], current_path)
            
            # Ensure the directory exists
            if not os.path.exists(upload_path):
                os.makedirs(upload_path)
            
            if file:
                filename = file.filename
                file.save(os.path.join(upload_path, filename))
                return 'File uploaded successfully'

        @self.app.route('/download/<path:filename>')
        def download_file(filename):
            # Ensure the file path is correct and secure
            safe_path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
            try:
                directory = os.path.dirname(safe_path)
                file_name = os.path.basename(safe_path)
                return send_from_directory(directory, file_name)
            except:
                return "File not found", 404

        @self.app.route('/stream/<path:filename>')
        def stream_file(filename):
            path = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
            
            # Get file size
            file_size = os.path.getsize(path)
            
            # Parse range header
            range_header = request.headers.get('Range', None)
            byte1, byte2 = 0, None
            
            if range_header:
                match = re.search(r'(\d+)-(\d*)', range_header)
                groups = match.groups()
                
                if groups[0]: byte1 = int(groups[0])
                if groups[1]: byte2 = int(groups[1])
            
            # Calculate chunk length
            if byte2 is None:
                byte2 = file_size - 1
            length = byte2 - byte1 + 1
            
            # Get content type
            content_type, _ = mimetypes.guess_type(path)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Create response
            def generate():
                with open(path, 'rb') as f:
                    f.seek(byte1)
                    remaining = length
                    chunk_size = 8192  # 8KB chunks
                    
                    while remaining:
                        chunk_size = min(chunk_size, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data
            
            headers = {
                'Content-Type': content_type,
                'Accept-Ranges': 'bytes',
                'Content-Range': f'bytes {byte1}-{byte2}/{file_size}',
                'Content-Length': length
            }
            
            return Response(generate(), 206, headers)
            
        def get_dir_size(path):
            total = 0
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        total += get_dir_size(entry.path)
            return total

        @self.app.route('/details', methods=['POST'])
        def get_item_details():
            path = os.path.join(self.upload_folder, request.form.get('path', '').lstrip('/'))
            stats = os.stat(path)
            
            details = {
                'name': os.path.basename(path),
                'type': 'Folder' if os.path.isdir(path) else 'File',
                'size': humanize.naturalsize(get_dir_size(path) if os.path.isdir(path) else stats.st_size),
                'created': datetime.datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                'modified': datetime.datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'path': request.form.get('path', '')
            }
            
            return jsonify(details)

    def start(self, host='0.0.0.0', port=5000):
        """Start the Flask server in a separate thread"""
        if self.thread and self.thread.is_alive():
            return True
        
        # Reset shutdown event
        self.shutdown_event.clear()
        
        def run_server():
            print(f"LocalDrive serving files from: {self.upload_folder}")
            try:
                self.server = make_server(host, port, self.app)
                self.ctx = self.app.app_context()
                self.ctx.push()
                # Use a timeout to allow checking for shutdown_event
                while not self.shutdown_event.is_set():
                    self.server.handle_request()
            except Exception as e:
                print(f"Server error: {e}")
            finally:
                # Clean up resources
                try:
                    if hasattr(self, 'ctx') and self.ctx:
                        self.ctx.pop()
                except Exception as e:
                    print(f"Error cleaning up app context: {e}")
                self.server = None
                self.ctx = None
                print("Server shutdown complete")
            
        self.thread = Thread(target=run_server)
        self.thread.daemon = True
        self.thread.start()
        # Give the server a moment to start
        time.sleep(0.5)
        return True
        
    def stop(self):
        """Stop the Flask server"""
        if not self.server:
            return True  # Already stopped
        
        try:
            # Signal the thread to stop
            self.shutdown_event.set()
            
            # If we have a server, try to shut it down
            if self.server:
                try:
                    # Simulate a request to unblock handle_request()
                    try:
                        requests_available = True
                        import requests
                    except ImportError:
                        requests_available = False
                    
                    if requests_available:
                        try:
                            requests.get(f"http://localhost:5000/", timeout=1)
                        except:
                            pass
                except:
                    pass
                
                # Wait for thread to finish (with timeout)
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=2.0)
                
                # If it's still running, we'll have to force it
                if self.thread and self.thread.is_alive():
                    print("Server thread didn't exit cleanly, forcing shutdown")
                    # Just reset our references and return
                    self.server = None
                    self.ctx = None
                    self.thread = None
                    
            return True
        except Exception as e:
            print(f"Error stopping server: {e}")
            # Reset state even on error
            self.server = None
            self.ctx = None
            self.thread = None
            return False
        
    def is_running(self):
        """Check if server is running"""
        return self.thread is not None and self.thread.is_alive() and not self.shutdown_event.is_set()
        
    def set_folder(self, folder_path):
        """Change the upload folder"""
        self.upload_folder = os.path.abspath(folder_path)
        if self.app:
            self.app.config['UPLOAD_FOLDER'] = self.upload_folder
            
    def run_standalone(self, host='0.0.0.0', port=5000):
        """Run the server in standalone mode (blocking)"""
        print(f"LocalDrive standalone mode serving files from: {self.upload_folder}")
        print(f"Server running at http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        print("Press Ctrl+C to stop")
        
        # Start the Flask application directly (not in a thread)
        try:
            self.app.run(host=host, port=port, debug=False, use_reloader=False)
        except KeyboardInterrupt:
            print("\nServer shutting down...")
        finally:
            # Ensure clean shutdown
            print("Goodbye!")

# Settings management
class AppSettings:
    def __init__(self, settings_file='settings.json'):
        self.settings_file = settings_file
        self.default_settings = {
            'autostart_server': False,
            'theme': 'blue',
            'startup_with_windows': False,
            'start_minimized': False,
            'exit_behavior': 'ask',  # Options: 'ask', 'minimize', 'exit'
            'context_menu': False    # Add new setting for context menu
        }
        self.settings = self.load_settings()
    
    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            return self.default_settings.copy()
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self.default_settings.copy()
    
    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def get(self, key, default=None):
        return self.settings.get(key, default)
    
    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()
        
    def toggle_windows_startup(self, enable):
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_path = os.path.abspath(sys.argv[0])
            
            key = reg.HKEY_CURRENT_USER
            registry_key = reg.OpenKey(key, key_path, 0, reg.KEY_WRITE)
            
            if enable:
                reg.SetValueEx(registry_key, "LocalDrive", 0, reg.REG_SZ, app_path)
            else:
                try:
                    reg.DeleteValue(registry_key, "LocalDrive")
                except FileNotFoundError:
                    pass
                
            reg.CloseKey(registry_key)
            self.set('startup_with_windows', enable)
            return True
        except Exception as e:
            print(f"Failed to set startup registry: {e}")
            return False

    def toggle_context_menu(self, enable):
        """Enable or disable the LocalDrive context menu in Windows Explorer"""
        if enable:
            success, message = install_context_menu()
        else:
            success, message = uninstall_context_menu()
            
        if success:
            # Save setting
            self.set('context_menu', enable)
        return success, message
        
# Context menu installation functions moved from context_menu_installer.py
def install_context_menu():
    """Install LocalDrive context menu for Windows Explorer"""
    try:
        # Get the path to the current executable
        exe_path = os.path.abspath(sys.argv[0])
        script_dir = os.path.dirname(exe_path)
        
        # Command to execute when menu item is clicked
        if exe_path.endswith('.py'):
            cmd = f'"{sys.executable}" "{exe_path}" --folder "%V"'
        else:
            cmd = f'"{exe_path}" --folder "%V"'
        
        # Define registry keys
        context_menu_key = r"Directory\\shell\\LocalDrive"
        context_command_key = r"Directory\\shell\\LocalDrive\\command"
        
        # Create the context menu entry
        key = reg.CreateKey(reg.HKEY_CLASSES_ROOT, context_menu_key)
        reg.SetValue(key, "", reg.REG_SZ, "Share with LocalDrive")
        
        # Set the icon (if icon.ico exists)
        icon_path = os.path.join(script_dir, 'icon.ico')
        if os.path.exists(icon_path):
            reg.SetValueEx(key, "Icon", 0, reg.REG_SZ, icon_path)
        
        # Create the command key
        cmd_key = reg.CreateKey(reg.HKEY_CLASSES_ROOT, context_command_key)
        reg.SetValue(cmd_key, "", reg.REG_SZ, cmd)
        
        # Close registry keys
        reg.CloseKey(cmd_key)
        reg.CloseKey(key)
        
        return True, "Context menu installed successfully!"
    except Exception as e:
        return False, f"Error installing context menu: {str(e)}"

def uninstall_context_menu():
    """Remove LocalDrive context menu from Windows Explorer"""
    try:
        # Define registry keys
        context_menu_key = r"Directory\\shell\\LocalDrive"
        context_command_key = r"Directory\\shell\\LocalDrive\\command"
        
        # Remove the context menu entries
        try:
            reg.DeleteKey(reg.HKEY_CLASSES_ROOT, context_command_key)
            reg.DeleteKey(reg.HKEY_CLASSES_ROOT, context_menu_key)
        except WindowsError:
            pass
            
        return True, "Context menu removed successfully!"
    except Exception as e:
        return False, f"Error removing context menu: {str(e)}"

class ModernStyle:
    # Krishna-inspired theme colors
    PRIMARY = "#2850A0"       # Krishna Blue
    PEACOCK = "#116D4B"       # Peacock Green
    GOLD = "#FFD700"          # Flute Gold
    LOTUS = "#FF9999"         # Lotus Pink
    BG_LIGHT = "#F0F5FF"      # Light background
    BG_DARK = "#1A2238"       # Dark background
    
    # Theme gradients
    HEADER_GRADIENT = [(PRIMARY, 0), (PEACOCK, 1)]
    BUTTON_GRADIENT = [(GOLD, 0), ("#FFA500", 1)]
    
    @staticmethod
    def apply_theme(root):
        style = ttk.Style(root)
        style.theme_use('clam')
        
        # Configure progress bar
        style.configure("TProgressbar", 
                      thickness=10,
                      troughcolor=ModernStyle.BG_LIGHT,
                      background=ModernStyle.GOLD,
                      borderwidth=0)
        
        # Configure buttons
        style.configure('Krishna.TButton', 
                      font=('Segoe UI', 12), 
                      background=ModernStyle.GOLD,
                      foreground=ModernStyle.PRIMARY)

class SplashScreen(tk.Tk):
    def __init__(self):
        super().__init__()

        # Hide window decorations
        self.overrideredirect(True)
        self.configure(bg=ModernStyle.PRIMARY)
        
        # Set icon
        try:
            if os.path.exists('icon.ico'):
                self.iconbitmap('icon.ico')
        except:
            pass

        # Set up background canvas for gradient
        width = 500
        height = 400
        self.canvas = tk.Canvas(self, width=width, height=height, 
                             highlightthickness=0, bg=ModernStyle.PRIMARY)
        self.canvas.pack(fill="both", expand=True)
        
        # Create gradient background
        for i in range(height):
            # Gradient from Krishna blue to peacock green
            r = int(((40 - 17) * i / height) + 17)
            g = int(((80 - 109) * i / height) + 109)
            b = int(((160 - 75) * i / height) + 75)
            color = f'#{r:02x}{g:02x}{b:02x}'
            self.canvas.create_line(0, i, width, i, fill=color)
        
        # Add decorative lotus pattern
        lotus_img = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
        lotus_img = lotus_img.resize((120, 120), Image.Resampling.LANCZOS)
        self.lotus = ImageTk.PhotoImage(lotus_img)
        self.canvas.create_image(width//2, 100, image=self.lotus)
        
        # Add peacock feather decorations
        self.canvas.create_text(width//2, 190, text="LocalDrive", 
                             fill=ModernStyle.GOLD, 
                             font=('Segoe UI', 32, 'bold'))
        
        self.canvas.create_text(width//2, 230, text="श्री कृष्णार्पणमस्तु", 
                             fill=ModernStyle.GOLD, 
                             font=('Arial Unicode MS', 16))

        # Center window
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # Progress frame
        progress_frame = tk.Frame(self.canvas, bg=ModernStyle.PRIMARY)
        self.canvas.create_window(width//2, 300, window=progress_frame)
        
        # Progress bar
        ModernStyle.apply_theme(self)
        self.progress = ttk.Progressbar(progress_frame, length=300, mode='determinate', style="TProgressbar")
        self.progress.pack(pady=10)
        
        # Loading text
        self.loading_text = tk.Label(progress_frame, text="Loading...", 
                                  font=('Segoe UI', 10), bg=ModernStyle.PRIMARY,
                                  fg=ModernStyle.GOLD)
        self.loading_text.pack()

        # Start progress
        self.progress_value = 0
        self.update_progress()

    def update_progress(self):
        if self.progress_value < 100:
            self.progress_value += 1
            self.progress['value'] = self.progress_value
            self.after(20, self.update_progress)
        else:
            self.after(500, self.launch_main)

    def launch_main(self):
        self.destroy()
        settings = AppSettings()
        app = MainWindow(show_window=not (settings.get('startup_with_windows', False) and 
                                         settings.get('start_minimized', False)))
        app.mainloop()

class UpdateManager:
    """Manages application updates and version checking"""
    def __init__(self, settings_file='settings.json'):
        self.settings_file = settings_file
        self.github_repo = "ranjanlive/localDrive"
        self.current_version = "1.0.0"  # Application's current version
        self.update_settings = self._load_update_settings()
        
    def _load_update_settings(self):
        """Load update-related settings or create defaults"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    # Initialize update settings if not present
                    if 'update_settings' not in settings:
                        settings['update_settings'] = {
                            'last_check': None,
                            'skipped_versions': [],
                            'check_frequency': 'daily',  # daily, weekly, never
                            'remind_later_time': None
                        }
                    return settings.get('update_settings')
            
            # Default update settings
            return {
                'last_check': None,
                'skipped_versions': [],
                'check_frequency': 'daily',
                'remind_later_time': None
            }
        except Exception as e:
            print(f"Error loading update settings: {e}")
            return {
                'last_check': None,
                'skipped_versions': [],
                'check_frequency': 'daily',
                'remind_later_time': None
            }
    
    def save_update_settings(self):
        """Save update settings to the settings file"""
        try:
            # Load current settings
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
            else:
                settings = {}
                
            # Update the update_settings section
            settings['update_settings'] = self.update_settings
            
            # Save back to file
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
                
        except Exception as e:
            print(f"Error saving update settings: {e}")
    
    def check_for_updates(self, silent=False):
        """Check GitHub for new releases
        
        Args:
            silent (bool): If True, don't show message if no updates available
            
        Returns:
            dict: Update information or None if no update available
        """
        # Don't check if frequency is set to 'never'
        if self.update_settings['check_frequency'] == 'never':
            return None
            
        # Skip if 'remind_later_time' is set and hasn't expired yet
        if self.update_settings['remind_later_time']:
            remind_time = datetime.fromisoformat(self.update_settings['remind_later_time'])
            if datetime.now() < remind_time:
                return None
        
        try:
            # Current time for last_check record
            now = datetime.now().isoformat()
            
            # Call GitHub API
            response = requests.get(
                f"https://api.github.com/repos/{self.github_repo}/releases/latest",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=5  # Timeout after 5 seconds
            )
            
            if response.status_code != 200:
                print(f"Error checking for updates: {response.status_code}")
                return None
                
            release_info = response.json()
            latest_version = release_info.get('tag_name', '').lstrip('v')
            
            # Update last check time
            self.update_settings['last_check'] = now
            self.save_update_settings()
            
            # Compare versions
            if self._compare_versions(latest_version, self.current_version) > 0:
                # Check if this version was skipped
                if latest_version in self.update_settings['skipped_versions']:
                    return None
                    
                # Return update info
                return {
                    'version': latest_version,
                    'description': release_info.get('body', 'No description available'),
                    'download_url': release_info.get('html_url'),
                    'published_date': release_info.get('published_at')
                }
            elif not silent:
                print("You're running the latest version!")
                
            return None
            
        except Exception as e:
            print(f"Error checking for updates: {e}")
            return None
    
    def _compare_versions(self, version1, version2):
        """Compare two version strings
        
        Returns:
            int: 1 if version1 > version2, -1 if version1 < version2, 0 if equal
        """
        # Extract version numbers using regex to handle various formats
        v1_parts = [int(x) for x in re.findall(r'\d+', version1)]
        v2_parts = [int(x) for x in re.findall(r'\d+', version2)]
        
        # Pad with zeros to make equal length
        while len(v1_parts) < len(v2_parts):
            v1_parts.append(0)
        while len(v2_parts) < len(v1_parts):
            v2_parts.append(0)
            
        # Compare version numbers
        for i in range(len(v1_parts)):
            if v1_parts[i] > v2_parts[i]:
                return 1
            elif v1_parts[i] < v2_parts[i]:
                return -1
                
        return 0
    
    def skip_version(self, version):
        """Add a version to the skipped_versions list"""
        if version not in self.update_settings['skipped_versions']:
            self.update_settings['skipped_versions'].append(version)
            self.save_update_settings()
    
    def remind_later(self, hours=24):
        """Set a remind_later_time for 'hours' in the future"""
        remind_time = datetime.now() + timedelta(hours=hours)
        self.update_settings['remind_later_time'] = remind_time.isoformat()
        self.save_update_settings()
    
    def download_update(self, url):
        """Open the download page in the default browser"""
        webbrowser.open(url)

class AboutWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("About LocalDrive")
        self.geometry("600x550")  # Adjusted height
        self.resizable(False, False)
        self.parent = parent
        
        # Create update manager
        self.update_manager = UpdateManager()
        
        # Set icon
        try:
            if os.path.exists('icon.ico'):
                self.iconbitmap('icon.ico')
            else:
                # Fallback to logo.png
                logo = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
                logo = logo.resize((32, 32), Image.Resampling.LANCZOS)
                logo_icon = ImageTk.PhotoImage(logo)
                self.iconphoto(True, logo_icon)
        except:
            pass
            
        # Main container
        container = tk.Frame(self, bg=ModernStyle.BG_LIGHT)
        container.pack(fill="both", expand=True)
        
        # Header with gradient
        header = tk.Canvas(container, bg=ModernStyle.PRIMARY, height=100, highlightthickness=0)
        header.pack(fill="x")
        
        # Create gradient in header
        width = 600
        for i in range(100):
            # Gradient from Krishna blue to peacock green
            r = int(((40 - 17) * i / 100) + 17)
            g = int(((80 - 109) * i / 100) + 109)
            b = int(((160 - 75) * i / 100) + 75)
            color = f'#{r:02x}{g:02x}{b:02x}'
            header.create_line(0, i, width, i, fill=color)

        # Load logo
        logo = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
        logo = logo.resize((60, 60), Image.Resampling.LANCZOS)
        self.logo_img = ImageTk.PhotoImage(logo)
        
        header.create_image(50, 50, image=self.logo_img)
        header.create_text(130, 50, text="LocalDrive", fill=ModernStyle.GOLD, 
                        font=('Segoe UI', 24, 'bold'), anchor="w")
        
        # Content area
        content = tk.Frame(container, bg=ModernStyle.BG_LIGHT, padx=30, pady=20)
        content.pack(fill="both", expand=True)
        
        # App description
        tk.Label(content, text="About LocalDrive", font=('Segoe UI', 16, 'bold'), 
               bg=ModernStyle.BG_LIGHT, fg=ModernStyle.PRIMARY).pack(anchor="w", pady=(0, 10))
        
        description = ("LocalDrive is a file sharing application inspired by Lord Krishna's "
                    "divine quality of connectivity. Just as Krishna connected with everyone, "
                    "LocalDrive connects all your devices on the same network.")
        
        tk.Label(content, text=description, font=('Segoe UI', 11), bg=ModernStyle.BG_LIGHT, 
               fg=ModernStyle.BG_DARK, wraplength=540, justify="left").pack(anchor="w", pady=(0, 15))
        
        # Update button section
        update_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        update_frame.pack(fill="x", pady=5)
        
        check_updates_btn = tk.Button(
            update_frame, 
            text="Check for Updates", 
            bg=ModernStyle.PRIMARY,
            fg="white",
            font=('Segoe UI', 10, 'bold'),
            padx=15, pady=5,
            bd=0,
            command=self.check_for_updates
        )
        check_updates_btn.pack(side="left")
        
        # Update status container (initially hidden)
        self.update_container = tk.Frame(content, bg=ModernStyle.BG_LIGHT, pady=10)
        
        # Update status label
        self.update_status = tk.Label(self.update_container, 
                                   text="",
                                   font=('Segoe UI', 10), 
                                   bg=ModernStyle.BG_LIGHT)
        self.update_status.pack(anchor="w")
        
        # Update actions frame (initially empty, will be populated if update found)
        self.update_actions = tk.Frame(self.update_container, bg=ModernStyle.BG_LIGHT, pady=5)
        
        # Update description text (will be shown if update found)
        self.update_description = tk.Text(self.update_container, 
                                       height=5, width=50, 
                                       wrap="word",
                                       font=('Segoe UI', 9),
                                       bg="#f5f5f5",
                                       relief="flat")
        
        # License Information
        license_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        license_frame.pack(fill="x", pady=10)
        
        tk.Label(license_frame, text="License:", font=('Segoe UI', 12, 'bold'), 
                bg=ModernStyle.BG_LIGHT, fg=ModernStyle.PRIMARY).pack(anchor="w")
                
        license_text = ("LocalDrive is free software: you can redistribute it and/or modify "
                      "it under the terms of the GNU General Public License as published by "
                      "the Free Software Foundation, either version 3 of the License, or "
                      "(at your option) any later version.")
        
        tk.Label(content, text=license_text, font=('Segoe UI', 10), bg=ModernStyle.BG_LIGHT,
               wraplength=540, justify="left").pack(anchor="w", pady=(0, 10))
        
        def open_gpl():
            webbrowser.open("https://www.gnu.org/licenses/gpl-3.0.html")
            
        license_btn = tk.Button(content, text="View Full GNU GPL License", 
                              bg=ModernStyle.PEACOCK, fg="white",
                              font=('Segoe UI', 10), bd=0, padx=10, pady=5,
                              command=open_gpl)
        license_btn.pack(anchor="w", pady=(0, 15))
        
        # Divider
        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=10)
        
        # Developer information
        # ...existing code with developer info...
        
        # Version and copyright
        version_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        version_frame.pack(fill="x", side="bottom", pady=10)
        
        year = datetime.now().year
        tk.Label(version_frame, text=f"LocalDrive v{self.update_manager.current_version}", 
               font=('Segoe UI', 10), bg=ModernStyle.BG_LIGHT).pack(side="left")
        
        tk.Label(version_frame, text=f"© {year} - GNU GPL v3", 
               font=('Segoe UI', 10), bg=ModernStyle.BG_LIGHT).pack(side="right")
    
    def check_for_updates(self):
        """Manual check for updates when button is clicked"""
        # Show checking status
        self.update_status.configure(text="Checking for updates...")
        self.update_container.pack(fill="x")
        
        # Schedule update check to avoid UI freeze
        self.after(100, self._do_update_check)
    
    def _do_update_check(self):
        """Perform the actual update check"""
        update_info = self.update_manager.check_for_updates(silent=False)
        self.update_ui(update_info)
    
    def update_ui(self, update_info):
        """Update the UI based on update check results"""
        if not update_info:
            # No update found or error occurred
            self.update_status.configure(text="You're running the latest version!")
            return
            
        # Update found - update UI
        self.update_status.configure(
            text=f"New version available: {update_info['version']}",
            fg=ModernStyle.PEACOCK,
            font=('Segoe UI', 11, 'bold')
        )
        
        # Show description
        self.update_description.delete(1.0, tk.END)
        self.update_description.insert(tk.END, update_info['description'])
        self.update_description.pack(fill="x", pady=10, padx=5)
        
        # Show action buttons
        self.update_actions.pack(fill="x")
        
        # Remove previous buttons if they exist
        for widget in self.update_actions.winfo_children():
            widget.destroy()
        
        # Create action buttons
        download_btn = tk.Button(self.update_actions, 
                               text="Download Update",
                               bg=ModernStyle.PRIMARY,
                               fg="white",
                               font=('Segoe UI', 10, 'bold'),
                               padx=10, pady=5,
                               bd=0,
                               command=lambda: self.handle_update_action('download', update_info))
        download_btn.pack(side="left", padx=(0, 10))
        
        remind_btn = tk.Button(self.update_actions, 
                             text="Remind Later",
                             bg="#6c757d",
                             fg="white",
                             font=('Segoe UI', 10),
                             padx=10, pady=5,
                             bd=0,
                             command=lambda: self.handle_update_action('remind', update_info))
        remind_btn.pack(side="left", padx=(0, 10))
        
        skip_btn = tk.Button(self.update_actions, 
                           text="Skip This Version",
                           bg="#6c757d",
                           fg="white",
                           font=('Segoe UI', 10),
                           padx=10, pady=5,
                           bd=0,
                           command=lambda: self.handle_update_action('skip', update_info))
        skip_btn.pack(side="left")
    
    def handle_update_action(self, action, update_info):
        """Handle user actions regarding updates"""
        if action == 'download':
            self.update_manager.download_update(update_info['download_url'])
            
        elif action == 'remind':
            self.update_manager.remind_later(hours=24)  # Remind after 24 hours
            self.update_status.configure(
                text=f"You'll be reminded about the update tomorrow",
                fg=ModernStyle.BG_DARK,
                font=('Segoe UI', 10)
            )
            self.update_actions.pack_forget()
            
        elif action == 'skip':
            self.update_manager.skip_version(update_info['version'])
            self.update_status.configure(
                text="You won't be notified about this version again",
                fg=ModernStyle.BG_DARK,
                font=('Segoe UI', 10)
            )
            self.update_actions.pack_forget()
            
        # Remove description
        if action in ('remind', 'skip'):
            self.update_description.pack_forget()

class SettingsWindow(tk.Toplevel):
    def __init__(self, parent, settings):
        super().__init__(parent)
        
        self.parent = parent
        self.settings = settings
        self.title("Settings")
        self.geometry("500x500")  # Increased height to accommodate new context menu buttons
        self.resizable(False, False)
        
        # Set icon
        try:
            if os.path.exists('icon.ico'):
                self.iconbitmap('icon.ico')
        except:
            pass
            
        # Main container
        container = tk.Frame(self, bg=ModernStyle.BG_LIGHT)
        container.pack(fill="both", expand=True)
        
        # Header with gradient
        header = tk.Canvas(container, bg=ModernStyle.PRIMARY, height=80, highlightthickness=0)
        header.pack(fill="x")
        
        # Create gradient in header
        width = 500
        for i in range(80):
            # Gradient from Krishna blue to peacock green
            r = int(((40 - 17) * i / 80) + 17)
            g = int(((80 - 109) * i / 80) + 109)
            b = int(((160 - 75) * i / 80) + 75)
            color = f'#{r:02x}{g:02x}{b:02x}'
            header.create_line(0, i, width, i, fill=color)

        header.create_text(30, 40, text="Settings", fill=ModernStyle.GOLD, 
                        font=('Segoe UI', 22, 'bold'), anchor="w")
        
        # Content area - Changed to use pack instead of grid
        content = tk.Frame(container, bg=ModernStyle.BG_LIGHT, padx=30, pady=20)
        content.pack(fill="both", expand=True)
        
        # Server Options Section
        self.create_setting_section(content, "Server Options")
        
        # Autostart server option
        self.autostart_var = tk.BooleanVar(value=self.settings.get('autostart_server', False))
        self.create_toggle_option(content, 
                                "Auto-start server when application launches", 
                                self.autostart_var, 
                                lambda: self.settings.set('autostart_server', self.autostart_var.get()))
        
        # Windows Options Section
        self.create_setting_section(content, "Windows Integration")
        
        # Add to Windows startup
        self.startup_var = tk.BooleanVar(value=self.settings.get('startup_with_windows', False))
        self.create_toggle_option(content, 
                                "Start with Windows", 
                                self.startup_var, 
                                lambda: self.settings.toggle_windows_startup(self.startup_var.get()))
        
        # Start minimized in system tray
        self.minimized_var = tk.BooleanVar(value=self.settings.get('start_minimized', False))
        self.create_toggle_option(content, 
                                "Start minimized to system tray", 
                                self.minimized_var, 
                                lambda: self.settings.set('start_minimized', self.minimized_var.get()))
                                
        # Add Windows Explorer context menu
        self.context_var = tk.BooleanVar(value=self.settings.get('context_menu', False))
        self.create_toggle_option(content, 
                                "Add 'Share with LocalDrive' to Explorer context menu", 
                                self.context_var, 
                                lambda: self.handle_context_menu(self.context_var.get()))
                                
        # Context menu direct actions
        context_buttons_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        context_buttons_frame.pack(fill="x", padx=30, pady=5)
        
        install_ctx_btn = tk.Button(context_buttons_frame, 
                                   text="Install Context Menu", 
                                   bg=ModernStyle.PRIMARY, fg="white",
                                   font=('Segoe UI', 9), padx=10, pady=3, bd=0,
                                   command=lambda: self.direct_context_menu_action(True))
        install_ctx_btn.pack(side="left", padx=(0, 10))
        
        remove_ctx_btn = tk.Button(context_buttons_frame, 
                                  text="Remove Context Menu", 
                                  bg="#B0B0B0", fg="white",
                                  font=('Segoe UI', 9), padx=10, pady=3, bd=0,
                                  command=lambda: self.direct_context_menu_action(False))
        remove_ctx_btn.pack(side="left")
        
        # Exit behavior
        self.create_setting_section(content, "Application Behavior")
        
        exit_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        exit_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(exit_frame, text="When closing window:", 
               font=('Segoe UI', 11), 
               bg=ModernStyle.BG_LIGHT).pack(side="left")
               
        self.exit_var = tk.StringVar(value=self.settings.get('exit_behavior', 'ask'))
        exit_options = [
            ("Ask every time", "ask"),
            ("Minimize to system tray", "minimize"),
            ("Exit application", "exit")
        ]
        
        exit_option_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT, padx=30)
        exit_option_frame.pack(fill="x", pady=5)
        
        for text, value in exit_options:
            tk.Radiobutton(exit_option_frame, text=text, variable=self.exit_var, 
                        value=value, bg=ModernStyle.BG_LIGHT,
                        font=('Segoe UI', 10),
                        command=lambda val=value: self.settings.set('exit_behavior', val)).pack(anchor="w", pady=2)
        
        # Advanced Options Section
        self.create_setting_section(content, "Advanced Options")
        
        # Theme selection
        theme_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT, pady=5)
        theme_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(theme_frame, text="Theme:", 
               font=('Segoe UI', 11), 
               bg=ModernStyle.BG_LIGHT).pack(side="left")
               
        theme_options = ["Krishna Blue", "Dark", "Light"]
        theme_var = tk.StringVar(value=theme_options[0])
        theme_dropdown = ttk.Combobox(theme_frame, textvariable=theme_var, 
                                    values=theme_options, state="readonly", width=15)
        theme_dropdown.pack(side="left", padx=10)
        
        # Button frame at the bottom
        button_frame = tk.Frame(content, bg=ModernStyle.BG_LIGHT)
        button_frame.pack(fill="x", side="bottom", pady=20)
        
        tk.Button(button_frame, text="Save", bg=ModernStyle.PRIMARY, fg="white",
               font=('Segoe UI', 10, 'bold'), padx=15, pady=5, bd=0,
               command=self.save_settings).pack(side="right", padx=10)
               
        tk.Button(button_frame, text="Cancel", bg="#B0B0B0", fg="white",
               font=('Segoe UI', 10), padx=15, pady=5, bd=0,
               command=self.destroy).pack(side="right")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def create_setting_section(self, parent, title):
        # Add some space before each section
        tk.Frame(parent, height=10, bg=ModernStyle.BG_LIGHT).pack(fill="x")
        
        # Section header
        section_frame = tk.Frame(parent, bg=ModernStyle.BG_LIGHT)
        section_frame.pack(fill="x", pady=(5, 0))
        
        tk.Label(section_frame, text=title, 
               font=('Segoe UI', 14, 'bold'), 
               bg=ModernStyle.BG_LIGHT, 
               fg=ModernStyle.PRIMARY).pack(anchor="w")
        
        # Separator
        separator = ttk.Separator(parent, orient="horizontal")
        separator.pack(fill="x", pady=5)
    
    def create_toggle_option(self, parent, text, var, callback):
        option_frame = tk.Frame(parent, bg=ModernStyle.BG_LIGHT)
        option_frame.pack(fill="x", padx=20, pady=5)
        
        cb = tk.Checkbutton(option_frame, text=text, variable=var, 
                         font=('Segoe UI', 11), 
                         bg=ModernStyle.BG_LIGHT,
                         command=callback)
        cb.pack(anchor="w")
    
    def handle_context_menu(self, enable):
        """Handle the context menu toggle from UI"""
        success, message = self.settings.toggle_context_menu(enable)
        if not success:
            messagebox.showerror("Context Menu Error", message)
            # Reset the checkbox if failed
            self.context_var.set(not enable)
    
    def direct_context_menu_action(self, install):
        """Handle direct install/remove context menu actions"""
        if install:
            success, message = install_context_menu()
            if success:
                self.context_var.set(True)
                self.settings.set('context_menu', True)
        else:
            success, message = uninstall_context_menu()
            if success:
                self.context_var.set(False)
                self.settings.set('context_menu', False)
                
        messagebox.showinfo("Context Menu", message)
    
    def save_settings(self):
        self.settings.save_settings()
        # Notify parent about settings changes
        self.parent.apply_settings()
        self.destroy()
        
    def on_closing(self):
        # Discard changes by reloading settings
        self.settings.load_settings()
        self.destroy()

class SystemTrayIcon:
    def __init__(self, app_instance):
        self.app = app_instance
        self.server_url = None
        self.is_server_running = False
        
        # Create and start the tray icon
        self.setup_tray_icon()
    
    def setup_tray_icon(self):
        # Define our menu with current state
        menu_items = self.create_menu_items()
        
        # Load icon
        self.icon_image = self.load_icon()
        
        # Create tray icon - only create a new one if not already running
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon is not None:
                self.tray_icon.stop()
        except:
            pass
            
        # Create and start the icon
        self.tray_icon = pystray.Icon("localDrive", self.icon_image, "LocalDrive", menu_items)
        
        # Start the tray icon in a separate thread
        self.thread = Thread(target=self.tray_icon.run)
        self.thread.daemon = True
        self.thread.start()
        
    def create_menu_items(self):
        # Create menu based on current state
        status_text = "Status: Server Online" if self.is_server_running else "Status: Server Offline"
        server_action_text = "Stop Server" if self.is_server_running else "Start Server"
        
        # Create menu items
        menu = [
            item(status_text, lambda: None, enabled=False),
        ]
        
        # Add URL item if server is running
        if self.is_server_running and self.server_url:
            menu.append(item(f"Server URL: {self.server_url}", lambda: None, enabled=False))
        
        # Add remaining items
        menu.extend([
            item(server_action_text, self.toggle_server),
            item('Open LocalDrive', self.show_window),
            item('Open in Browser', self.open_in_browser, enabled=self.is_server_running),
            item('Quit', self.quit_app)
        ])
        
        return menu
    
    def load_icon(self):
        if os.path.exists('icon.ico'):
            from PIL import Image
            return Image.open('icon.ico')
        elif os.path.exists('logo.png'):
            from PIL import Image
            return Image.open('logo.png')
        else:
            # Create a default icon if needed
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (64, 64), color=(40, 80, 160))
            d = ImageDraw.Draw(img)
            d.text((10, 10), "LD", fill=(255, 215, 0))
            return img
    
    def show_window(self):
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()
    
    def toggle_server(self):
        # Call the app's toggle_server method
        self.app.toggle_server()
        
    def open_in_browser(self):
        if self.server_url:
            webbrowser.open(self.server_url)
    
    def quit_app(self):
        # Stop server if running
        if self.app.is_server_running:
            self.app.stop_server()
            
        # Stop the icon
        self.tray_icon.stop()
        
        # Destroy the app
        self.app.destroy()
    
    def update_server_status(self, is_running, url=None):
        # Update internal state
        self.is_server_running = is_running
        self.server_url = url if is_running else None
        
        # Recreate the menu and update the icon
        try:
            # Recreate tray icon with new menu items
            self.setup_tray_icon()
        except Exception as e:
            print(f"Error updating system tray: {e}")

class MainWindow(tk.Tk):
    def __init__(self, show_window=True, start_folder=None):
        super().__init__()

        self.title('LocalDrive')
        self.configure(bg=ModernStyle.BG_LIGHT)
        self.is_server_running = False
        self.start_folder = start_folder
        
        # Initialize Flask server
        self.flask_server = FlaskServerThread(upload_folder=start_folder if start_folder else '.')
        
        # Load settings
        self.settings = AppSettings()

        # Set window icon using .ico file
        try:
            if os.path.exists('icon.ico'):
                self.iconbitmap('icon.ico')
            else:
                # Fallback to logo.png with PhotoImage
                logo = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
                logo_small = logo.resize((32, 32), Image.Resampling.LANCZOS)
                self.icon = ImageTk.PhotoImage(logo_small)
                self.iconphoto(True, self.icon)
        except Exception as e:
            print(f"Error loading icon: {e}")

        # Window size and position
        width = 900
        height = 650
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f'{width}x{height}+{x}+{y}')
        self.minsize(700, 550)

        # Make window DPI aware for better scaling
        try:
            if platform.system() == "Windows":
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        # Load high quality logo for window icon
        try:
            logo = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
            # Use high quality resizing
            logo_small = logo.resize((32, 32), Image.Resampling.LANCZOS)
            self.icon = ImageTk.PhotoImage(logo_small)
            self.iconphoto(True, self.icon)
        except Exception as e:
            print(f"Error loading logo: {e}")

        # Create main container with grid layout for better scaling
        self.container = tk.Frame(self, bg=ModernStyle.BG_LIGHT)
        self.container.pack(fill="both", expand=True)
        
        # Configure grid weights for responsive layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Content
        self.grid_rowconfigure(2, weight=0) # Footer
        
        # Create header with gradient background
        header_frame = tk.Frame(self.container, height=120)
        header_frame.pack(fill="x")
        
        header = tk.Canvas(header_frame, height=120, highlightthickness=0)
        header.pack(fill="x", expand=True)
        
        # Create gradient in header
        for i in range(120):
            # Gradient from Krishna blue to peacock green
            r = int(((40 - 17) * i / 120) + 17)
            g = int(((80 - 109) * i / 120) + 109)
            b = int(((160 - 75) * i / 120) + 75)
            color = f'#{r:02x}{g:02x}{b:02x}'
            header.create_line(0, i, 3000, i, fill=color) # Extra wide for different resolutions
        
        # Load logo with high quality for header
        try:
            logo = Image.open('logo.png' if os.path.exists('logo.png') else 'static/logo.png')
            # Use higher resolution for header logo
            logo_header = logo.resize((80, 80), Image.Resampling.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(logo_header)
            
            # Add logo and title to header
            header.create_image(60, 60, image=self.logo_img)
        except:
            pass
            
        header.create_text(150, 50, text="LocalDrive", 
                        fill=ModernStyle.GOLD, font=('Segoe UI', 28, 'bold'), anchor="w")
        header.create_text(150, 85, text="Share files across your devices with divine simplicity", 
                        fill="white", font=('Segoe UI', 12), anchor="w")
        
        # Settings and About buttons in header
        settings_btn = tk.Button(header, text="Settings", bg=ModernStyle.GOLD, fg=ModernStyle.PRIMARY,
                              font=('Segoe UI', 10, 'bold'), bd=0, padx=15, pady=5,
                              command=self.show_settings)
        settings_btn_window = header.create_window(width-170, 30, window=settings_btn)
        
        about_btn = tk.Button(header, text="About", bg=ModernStyle.GOLD, fg=ModernStyle.PRIMARY,
                           font=('Segoe UI', 10, 'bold'), bd=0, padx=15, pady=5,
                           command=self.show_about)
        about_btn_window = header.create_window(width-80, 30, window=about_btn)
        
        # Update button position on window resize
        def update_buttons(event):
            header.coords(settings_btn_window, event.width-170, 30)
            header.coords(about_btn_window, event.width-80, 30)
            
        header.bind("<Configure>", update_buttons)

        # Create content area with pack_propagate False to maintain size
        content = tk.Frame(self.container, bg=ModernStyle.BG_LIGHT, padx=30, pady=20)
        content.pack(fill="both", expand=True)

        # Server controls - Make it more modern with card layout
        control_card = tk.Frame(content, bg="white", padx=20, pady=20, 
                              bd=0, highlightthickness=1, highlightbackground="#DDD")
        control_card.pack(fill="x", pady=(0, 20))
        
        # Server heading
        tk.Label(control_card, text="Server Control", font=('Segoe UI', 16, 'bold'), 
               bg="white", fg=ModernStyle.PRIMARY).pack(anchor="w")
        
        # Server status and controls
        status_frame = tk.Frame(control_card, bg="white")
        status_frame.pack(fill="x", pady=15)
        
        self.status_indicator = tk.Canvas(status_frame, width=15, height=15, bg="white", 
                                       highlightthickness=0)
        self.status_indicator.create_oval(2, 2, 13, 13, fill="gray", outline="")
        self.status_indicator.pack(side="left")
        
        self.status_text = tk.Label(status_frame, text="Server is offline", 
                                  font=('Segoe UI', 12), bg="white")
        self.status_text.pack(side="left", padx=10)
        
        # Server button with gradient effect
        self.server_btn = tk.Button(
            status_frame, text="Start Server", command=self.toggle_server,
            font=('Segoe UI', 11, 'bold'), bg=ModernStyle.PRIMARY, fg="white", 
            padx=20, pady=8, bd=0, activebackground=ModernStyle.PEACOCK
        )
        self.server_btn.pack(side="right")
        
        # URL info
        self.url_frame = tk.Frame(control_card, bg="white")
        self.url_frame.pack(fill="x", pady=10)
        
        self.url_label = tk.Label(self.url_frame, text="", font=('Segoe UI', 12), 
                                bg="white", fg=ModernStyle.PEACOCK)
        self.url_label.pack(anchor="w")

        # Quick actions row
        quick_actions = tk.Frame(control_card, bg="white", pady=10)
        quick_actions.pack(fill="x")
        
        self.copy_url_btn = tk.Button(
            quick_actions, text="Copy URL", command=self.copy_url,
            font=('Segoe UI', 10), bg="#f0f0f0", fg=ModernStyle.PRIMARY, 
            padx=10, pady=5, bd=0, state="disabled"
        )
        self.copy_url_btn.pack(side="left", padx=(0, 10))
        
        self.open_browser_btn = tk.Button(
            quick_actions, text="Open in Browser", command=self.open_in_browser,
            font=('Segoe UI', 10), bg="#f0f0f0", fg=ModernStyle.PRIMARY, 
            padx=10, pady=5, bd=0, state="disabled"
        )
        self.open_browser_btn.pack(side="left")

        # QR Code section with card style and proper height
        qr_card = tk.Frame(content, bg="white", padx=20, pady=20, 
                         bd=0, highlightthickness=1, highlightbackground="#DDD")
        qr_card.pack(fill="both", expand=True, pady=(0, 10))
        
        # Set a minimum height for QR container
        qr_card.update()
        min_height = max(250, qr_card.winfo_height() - 100)
        
        # QR Heading
        tk.Label(qr_card, text="Scan to Connect", font=('Segoe UI', 16, 'bold'), 
               bg="white", fg=ModernStyle.PRIMARY).pack(anchor="w", pady=(0, 10))
        
        # QR Frame with fixed height
        self.qr_container = tk.Frame(qr_card, bg="white", height=min_height)
        self.qr_container.pack(fill="x", expand=True)
        self.qr_container.pack_propagate(False)  # Prevent size changes
        
        self.qr_placeholder = tk.Label(
            self.qr_container, 
            text="QR code will appear here\nwhen server is started",
            font=('Segoe UI', 12),
            fg="gray",
            bg="white"
        )
        self.qr_placeholder.pack(expand=True)
        
        self.qr_frame = tk.Frame(self.qr_container, bg="white", bd=0)
        
        self.qr_label = tk.Label(self.qr_frame, bg="white")
        self.qr_label.pack(pady=(20, 10))
        
        # Instruction when QR is shown
        self.qr_instruction = tk.Label(
            self.qr_frame,
            text="Scan with your mobile device to connect",
            font=('Segoe UI', 10),
            fg=ModernStyle.PRIMARY,
            bg="white"
        )
        self.qr_instruction.pack()

        # Footer with Krishna theme
        footer = tk.Frame(self.container, bg=ModernStyle.PRIMARY, pady=10)
        footer.pack(fill="x", side="bottom")
        
        year = datetime.now().year
        footer_text = f"Made with ❤️ in Bihar, India • {year} • Open Source"
        tk.Label(footer, text=footer_text, fg="white", bg=ModernStyle.PRIMARY, 
               font=('Segoe UI', 10)).pack()

        # Create system tray icon
        self.tray_icon = SystemTrayIcon(self)
        
        # Protocol for closing
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Bind resize event to adjust layout
        self.bind("<Configure>", self.on_resize)
        
        # Apply settings after UI creation
        self.server_url = None
        
        # Show window or minimize to tray based on settings
        if not show_window:
            self.withdraw()
        
        # Apply autostart if enabled or if start_folder is specified
        self.apply_settings()

        # Add update manager instance without auto-checking
        self.update_manager = UpdateManager()

    def apply_settings(self):
        # If folder was specified, start server pointing to that folder
        if self.start_folder:
            self.after(500, lambda: self.toggle_server(folder_path=self.start_folder))
        # Otherwise check if autostart is enabled
        elif self.settings.get('autostart_server', False) and not self.is_server_running:
            self.after(1000, self.toggle_server)  # Start server after a delay

    def on_resize(self, event):
        # Adjust QR container height based on window size
        if hasattr(self, 'qr_container'):
            # Calculate proportional height
            window_height = self.winfo_height()
            new_height = max(250, int(window_height * 0.4))
            self.qr_container.configure(height=new_height)

    def show_about(self):
        about_window = AboutWindow(self)
        about_window.focus_force()
        about_window.grab_set()
        about_window.transient(self)
        
    def show_settings(self):
        settings_window = SettingsWindow(self, self.settings)
        settings_window.focus_force()

    def copy_url(self):
        if self.server_url:
            self.clipboard_clear()
            self.clipboard_append(self.server_url)
            messagebox.showinfo("URL Copied", f"Server URL has been copied to clipboard:\n{self.server_url}")

    def open_in_browser(self):
        if self.server_url:
            webbrowser.open(self.server_url)

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return 'localhost'

    def generate_qr(self, url):
        # Create a QR code with Krishna blue fill
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Increased error correction
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        qr_image = qr.make_image(fill_color=ModernStyle.PRIMARY, back_color="white")
        
        # Determine appropriate size based on container
        self.qr_container.update()
        container_height = self.qr_container.winfo_height()
        qr_size = min(container_height - 40, 300)  # Leave space for instruction text
        
        # Resize for display with high quality
        qr_image = qr_image.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        
        # Convert to PhotoImage
        qr_photo = ImageTk.PhotoImage(qr_image)
        
        # Update UI
        self.qr_placeholder.pack_forget()
        self.qr_frame.pack(expand=True)
        self.qr_label.configure(image=qr_photo)
        self.qr_label.image = qr_photo  # Keep a reference

    def toggle_server(self, folder_path=None):
        if not self.is_server_running:
            # Start server
            try:
                # Update folder path if specified
                if folder_path and os.path.exists(folder_path):
                    self.flask_server.set_folder(folder_path)
                    
                # Start the Flask server
                if self.flask_server.start(host='0.0.0.0', port=5000):
                    self.is_server_running = True
                    self.server_btn.configure(text='Stop Server', bg='#DC3545')
                    self.status_indicator.itemconfig(1, fill="#4CAF50")  # Green
                    
                    # Update status text to show folder
                    current_folder = self.flask_server.upload_folder
                    path_text = current_folder if len(current_folder) < 30 else f"...{current_folder[-30:]}"
                    self.status_text.configure(text=f"Server is online (Folder: {path_text})")
                    
                    # Update URL and QR code
                    ip = self.get_local_ip()
                    self.server_url = f'http://{ip}:5000'
                    self.url_label.configure(text=f'Server address: {self.server_url}')
                    self.generate_qr(self.server_url)
                    
                    # Update system tray with delayed call to avoid threading issues
                    self.after(100, lambda: self.tray_icon.update_server_status(True, self.server_url))
                    
                    # Enable URL buttons
                    self.copy_url_btn.configure(state="normal")
                    self.open_browser_btn.configure(state="normal")
                    
                    messagebox.showinfo("Server Status", f"Server started successfully!\nAccess at: {self.server_url}")
                else:
                    messagebox.showerror("Server Error", "Could not start server")
                
            except Exception as e:
                messagebox.showerror('Error', f'Failed to start server: {str(e)}')
        else:
            # Stop server
            try:
                self.flask_server.stop()
                # Reset UI
                self.is_server_running = False
                self.server_btn.configure(text='Start Server', bg=ModernStyle.PRIMARY)
                self.status_indicator.itemconfig(1, fill="gray")
                self.status_text.configure(text="Server is offline")
                self.url_label.configure(text='')
                
                # Update system tray with delayed call to avoid threading issues
                self.after(100, lambda: self.tray_icon.update_server_status(False))
                
                # Disable URL buttons
                self.copy_url_btn.configure(state="disabled")
                self.open_browser_btn.configure(state="disabled")
                self.server_url = None
                
                # Reset QR code
                self.qr_frame.pack_forget()
                self.qr_placeholder.pack(expand=True)
            except Exception as e:
                messagebox.showerror("Server Error", f"Error stopping server: {str(e)}")

    def stop_server(self):
        """Stop the Flask server"""
        if self.is_server_running:
            try:
                self.flask_server.stop()
                self.is_server_running = False
            except Exception as e:
                print(f"Error stopping server: {e}")
                # Even on error, mark as not running to allow clean exit
                self.is_server_running = False

    def on_closing(self):
        exit_behavior = self.settings.get('exit_behavior', 'ask')
        
        if exit_behavior == 'ask':
            if self.is_server_running:
                action = messagebox.askyesnocancel(
                    "Quit", 
                    "Server is running. What would you like to do?\n\n"
                    "Yes = Exit and stop server\n"
                    "No = Minimize to system tray\n"
                    "Cancel = Do nothing"
                )
                if action is None:  # Cancel
                    return
                elif action:  # Yes
                    self.stop_server()
                    self.tray_icon.tray_icon.stop()
                    self.destroy()
                else:  # No
                    self.withdraw()
            else:
                action = messagebox.askyesno(
                    "Quit", 
                    "Do you want to exit LocalDrive?\n\n"
                    "Yes = Exit application\n"
                    "No = Minimize to system tray"
                )
                if action:
                    self.tray_icon.tray_icon.stop()
                    self.destroy()
                else:
                    self.withdraw()
        elif exit_behavior == 'minimize':
            self.withdraw()
        else:  # exit behavior
            if self.is_server_running:
                if messagebox.askyesno("Quit", "Server is running. Do you want to stop it and exit?"):
                    self.stop_server()
                    self.tray_icon.tray_icon.stop()
                    self.destroy()
            else:
                self.tray_icon.tray_icon.stop()
                self.destroy()

if __name__ == '__main__':
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='LocalDrive Server')
    parser.add_argument('--folder', help='Start server with specified folder')
    parser.add_argument('--server-only', action='store_true', help='Run in server-only mode without GUI')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the server to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Port to run the server on (default: 5000)')
    args = parser.parse_args()
    
    # Get upload folder
    upload_folder = args.folder if args.folder else '.'
    upload_folder = os.path.abspath(upload_folder)
    
    # Decide which mode to run in
    if args.server_only:
        # Run in standalone server mode (no GUI)
        print(f"Starting LocalDrive in server-only mode")
        print(f"Serving files from: {upload_folder}")
        server = FlaskServerThread(upload_folder=upload_folder)
        server.run_standalone(host=args.host, port=args.port)
    else:
        # Check if UPLOAD_FOLDER environment variable is set (compatibility with old app.py)
        env_folder = os.environ.get('UPLOAD_FOLDER')
        if env_folder and not args.folder:
            upload_folder = os.path.abspath(env_folder)
            print(f"Using folder from environment variable: {upload_folder}")
            
        # Run in GUI mode
        if args.folder:
            app = MainWindow(show_window=True, start_folder=upload_folder)
            app.mainloop()
        else:
            # Normal startup with splash screen
            splash = SplashScreen()
            splash.mainloop()
