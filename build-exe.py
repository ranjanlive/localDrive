# LocalDrive - A file sharing application
# Copyright (C) 2023-2024 Ranjan Developer
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import os
import sys
import subprocess
import shutil
import time
import winreg
import pkg_resources

def get_pyinstaller_path():
    """Get PyInstaller path by checking if it's installed"""
    try:
        # Try to find PyInstaller using package resources
        pyinstaller_spec = pkg_resources.working_set.by_key.get('pyinstaller')
        if pyinstaller_spec:
            pyinstaller_path = os.path.join(os.path.dirname(pyinstaller_spec.location), 'Scripts', 'pyinstaller.exe')
            if os.path.exists(pyinstaller_path):
                print(f"Found PyInstaller at: {pyinstaller_path}")
                return pyinstaller_path
        
        # Try to find pyinstaller using subprocess
        try:
            result = subprocess.run([sys.executable, "-m", "pip", "show", "pyinstaller"], 
                                   capture_output=True, text=True, check=True)
            
            # Successfully found PyInstaller, now let's try to run it with python -m
            print("PyInstaller is installed. Using 'python -m PyInstaller'")
            return [sys.executable, "-m", "PyInstaller"]
        except subprocess.CalledProcessError:
            # PyInstaller not found, let's install it
            print("PyInstaller not found. Installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("PyInstaller installed successfully.")
            return [sys.executable, "-m", "PyInstaller"]
            
    except Exception as e:
        print(f"Error detecting PyInstaller: {e}")
        print("Attempting to install PyInstaller...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            return [sys.executable, "-m", "PyInstaller"]
        except Exception as e:
            print(f"Failed to install PyInstaller: {e}")
            sys.exit(1)

def install_missing_dependencies():
    """Check and install missing dependencies"""
    required_packages = [
        'flask', 'humanize', 'pillow', 'pystray', 
        'pywin32', 'qrcode', 'requests'
    ]
    
    for package in required_packages:
        try:
            # Check if the package is installed using pip
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", package], 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ {package} is installed")
            else:
                print(f"Installing {package}...")
                subprocess.run([sys.executable, "-m", "pip", "install", package], check=True)
                print(f"✓ {package} installed successfully")
        except Exception as e:
            print(f"Error checking/installing {package}: {e}")
            sys.exit(1)
    
    print("All dependencies installed successfully!")

def set_file_version_info():
    """Create a version info file for the executable"""
    version_info = """
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'RANJAN SOFTWARES'),
           StringStruct(u'FileDescription', u'LocalDrive - File Sharing Application'),
           StringStruct(u'FileVersion', u'1.0.0'),
           StringStruct(u'InternalName', u'LocalDrive'),
           StringStruct(u'LegalCopyright', u'(C) RANJAN SOFTWARES'),
           StringStruct(u'OriginalFilename', u'LocalDrive.exe'),
           StringStruct(u'ProductName', u'LocalDrive'),
           StringStruct(u'ProductVersion', u'1.0.0')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    # Write file with explicit UTF-8 encoding to handle special characters
    with open('version_info.txt', 'w', encoding='utf-8') as f:
        f.write(version_info)
    return 'version_info.txt'

def clean_build_files(version_file, keep_exe=True):
    """Clean up all build-related files and folders"""
    print("\nCleaning up build files...")
    
    # Files to clean up
    if os.path.exists(version_file):
        os.remove(version_file)
        print(f"Removed {version_file}")
    
    if os.path.exists('LocalDrive.spec'):
        os.remove('LocalDrive.spec')
        print("Removed LocalDrive.spec")
    
    # Remove PyInstaller build directory
    if os.path.exists('build'):
        shutil.rmtree('build')
        print("Removed build directory")
    
    # Remove PyInstaller cache directories
    for dirname in ('__pycache__', '.pytest_cache'):
        if os.path.exists(dirname):
            shutil.rmtree(dirname)
            print(f"Removed {dirname} directory")
    
    # Clean up any .pyc files
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.pyc'):
                os.remove(os.path.join(root, file))
                print(f"Removed {os.path.join(root, file)}")
    
    # If not keeping the exe, also clean the dist folder
    if not keep_exe and os.path.exists('dist'):
        shutil.rmtree('dist')
        print("Removed dist directory")
    
    print("Cleanup complete!")

def build_executable():
    """Build the executable using PyInstaller"""
    print("\n=== Building LocalDrive Executable ===\n")
    
    # 1. Check PyInstaller
    pyinstaller_command = get_pyinstaller_path()
    
    # 2. Install missing dependencies
    print("Checking dependencies...")
    install_missing_dependencies()
    
    # 3. Create version info file
    print("Creating version information...")
    version_file = set_file_version_info()
    
    # 4. Prepare build directory
    print("Creating build directories...")
    os.makedirs('dist', exist_ok=True)
    
    # 5. Copy resources
    print("Checking resources...")
    required_resources = ['templates', 'static']
    for resource in required_resources:
        if not os.path.exists(resource):
            os.makedirs(resource, exist_ok=True)
            print(f"Created {resource} directory")
    
    # 6. Check for icon
    icon_path = 'icon.ico'
    if not os.path.exists(icon_path):
        print(f"Warning: {icon_path} not found. Using default icon.")
        icon_path = None
    
    # 7. Build command for PyInstaller
    if isinstance(pyinstaller_command, list):
        # Using python -m PyInstaller
        cmd = pyinstaller_command + [
            '--clean',
            '--name=LocalDrive',
            '--onefile',
            '--windowed',
            f'--add-data=templates{os.pathsep}templates',
            f'--add-data=static{os.pathsep}static',
        ]
    else:
        # Using direct pyinstaller command
        cmd = [
            pyinstaller_command,
            '--clean',
            '--name=LocalDrive',
            '--onefile',
            '--windowed',
            f'--add-data=templates{os.pathsep}templates',
            f'--add-data=static{os.pathsep}static',
        ]
    
    # Add icon if available
    if icon_path:
        cmd.append(f'--icon={icon_path}')
    
    # Add version file
    cmd.append(f'--version-file={version_file}')
    
    # Add main script
    cmd.append('launcher_win.py')
    
    # 8. Execute PyInstaller
    print("\nRunning PyInstaller with the following command:")
    print(' '.join(str(c) for c in cmd))
    print("\nBuilding executable (this might take a while)...")
    
    try:
        subprocess.run(cmd, check=True)
        
        # 9. Clean up build files but keep the executable
        clean_build_files(version_file, keep_exe=True)
        
        # Create a settings.json file in the dist folder if it doesn't exist
        dist_settings = os.path.join('dist', 'settings.json')
        if not os.path.exists(dist_settings):
            default_settings = {
                "autostart_server": False,
                "theme": "blue",
                "startup_with_windows": False,
                "context_menu": False,
                "start_minimized": False,
                "exit_behavior": "ask"
            }
            with open(dist_settings, 'w') as f:
                import json
                json.dump(default_settings, f, indent=4)
                print("Created default settings.json in dist folder")
        
        # Copy logo.png to dist folder if it exists
        if os.path.exists('logo.png'):
            shutil.copy('logo.png', os.path.join('dist', 'logo.png'))
            print("Copied logo.png to dist folder")
        
        # Copy icon.ico to dist folder if it exists
        if os.path.exists('icon.ico'):
            shutil.copy('icon.ico', os.path.join('dist', 'icon.ico'))
            print("Copied icon.ico to dist folder")
        
        # Copy LICENSE file to dist folder
        if os.path.exists('LICENSE'):
            shutil.copy('LICENSE', os.path.join('dist', 'LICENSE'))
            print("Copied LICENSE to dist folder")
        else:
            print("WARNING: LICENSE file not found. Please include it in your distribution.")
        
        # Create static and templates folders in dist
        for folder in ['static', 'templates']:
            os.makedirs(os.path.join('dist', folder), exist_ok=True)
            # Copy all files from the folder to the dist folder
            if os.path.exists(folder):
                for file in os.listdir(folder):
                    src_path = os.path.join(folder, file)
                    dst_path = os.path.join('dist', folder, file)
                    if os.path.isfile(src_path):
                        shutil.copy(src_path, dst_path)
                        print(f"Copied {src_path} to {dst_path}")
        
        # 10. Success message
        print("\n✅ Build completed successfully!")
        print(f"Executable is located at: dist/LocalDrive.exe")
        
        # Open the dist folder
        os.startfile(os.path.abspath('dist'))
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed with error: {e}")
        # Clean up even if build failed
        clean_build_files(version_file, keep_exe=True)
        sys.exit(1)

def create_installer():
    """Creates an InnoSetup installer if available"""
    try:
        # Check if InnoSetup is installed
        inno_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        
        inno_path = None
        for i in range(1000):  # Check a reasonable number of subkeys
            try:
                key_name = winreg.EnumKey(inno_key, i)
                key = winreg.OpenKey(inno_key, key_name)
                try:
                    display_name = winreg.QueryValueEx(key, "DisplayName")[0]
                    if "Inno Setup" in display_name:
                        inno_path = os.path.join(
                            os.path.dirname(winreg.QueryValueEx(key, "UninstallString")[0]), 
                            "ISCC.exe"
                        )
                        break
                except (WindowsError, IndexError):
                    pass
            except WindowsError:
                break
        
        if not inno_path or not os.path.exists(inno_path):
            print("\nInnoSetup not found. Skipping installer creation.")
            print("If you want to create an installer, please install InnoSetup from: https://jrsoftware.org/isdl.php")
            return
        
        # Create GPL notice file
        gpl_notice = """LocalDrive is Free Software
==========================

LocalDrive is free software released under the GNU General Public License version 3.0 (GNU GPL).

You have the freedom to:
• Run the program for any purpose
• Study how the program works and modify it
• Redistribute copies of the original program
• Distribute copies of your modified versions

The GNU GPL is a copyleft license, which means that derivative work can only be distributed under the same license.

For more information, see the full GNU GPL license included with this software or visit:
https://www.gnu.org/licenses/gpl-3.0.html

The next page will show the full license text, which you must accept to install the software."""

        with open('gpl_notice.txt', 'w') as f:
            f.write(gpl_notice)
        
        # Create InnoSetup script
        print("\nCreating InnoSetup installation script...")
        inno_script = """
#define MyAppName "LocalDrive"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "RANJAN SOFTWARES"
#define MyAppURL "https://github.com/ranjanlive/localDrive"
#define MyAppExeName "LocalDrive.exe"
#define MyAppLicense "LICENSE"

[Setup]
AppId={{E1393C8B-7936-42E6-BD6C-068C94B682D9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=dist\\{#MyAppLicense}
; Show GNU GPL notice before license
InfoBeforeFile=gpl_notice.txt
; Remove the following line to run in administrative mode
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=LocalDriveSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startmenu"; Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}";
Name: "startup"; Description: "Start LocalDrive when Windows starts"; GroupDescription: "Windows Integration"; Flags: unchecked
Name: "contextmenu"; Description: "Add 'Share with LocalDrive' to Explorer context menu"; GroupDescription: "Windows Integration"; Flags: unchecked

[Files]
Source: "dist\\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\\icon.ico"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\\logo.png"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\\settings.json"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\\LICENSE"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\\static\\*"; DestDir: "{app}\\static\\"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "dist\\templates\\*"; DestDir: "{app}\\templates\\"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
Name: "{group}\\License"; Filename: "{app}\\LICENSE"
Name: "{group}\\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autostartup}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "notepad"; Parameters: "{app}\\LICENSE"; Description: "View GNU GPL License"; Flags: postinstall shellexec skipifsilent unchecked
        """
        
        with open('LocalDrive.iss', 'w') as f:
            f.write(inno_script)
        
        # Create output directory for installer
        os.makedirs('installer_output', exist_ok=True)
        
        # Run InnoSetup Compiler
        print("Running InnoSetup Compiler...")
        subprocess.run([inno_path, '/Q', 'LocalDrive.iss'], check=True)
        
        # Success message
        print("\n✅ Installer created successfully!")
        print("Installer is located in the installer_output folder")
        
        # Open the installer folder
        os.startfile(os.path.abspath('installer_output'))
        
        # Clean up the InnoSetup script and notice file
        for file in ['LocalDrive.iss', 'gpl_notice.txt']:
            if os.path.exists(file):
                os.remove(file)
                print(f"Removed {file}")
        
    except Exception as e:
        print(f"\nCouldn't create installer: {e}")
        print("Skipping installer creation.")

def cleanup_all():
    """Perform a complete cleanup of all temporary files"""
    print("\n=== Final Cleanup ===")
    
    # Ask if the user wants to keep the dist folder
    keep_dist = input("Do you want to keep the 'dist' folder with the executable? (y/n): ").lower() == 'y'
    
    # Clean up build files
    clean_build_files('version_info.txt', keep_exe=keep_dist)
    
    # Additional cleanup
    files_to_remove = ['LocalDrive.iss']
    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
            print(f"Removed {file}")
    
    print("\nAll build-related files have been cleaned up!")

if __name__ == "__main__":
    start_time = time.time()
    
    print("="*50)
    print("LocalDrive Executable Builder")
    print("="*50)
    
    # Build the executable
    build_executable()
    
    # Optionally create an installer
    response = input("\nDo you want to create an installer? (y/n): ")
    if response.lower() == 'y':
        create_installer()
    
    # Final cleanup
    cleanup_all()
    
    # Execution time
    elapsed_time = time.time() - start_time
    minutes = int(elapsed_time // 60)
    seconds = int(elapsed_time % 60)
    print(f"\nProcess completed in {minutes} minutes and {seconds} seconds.")
