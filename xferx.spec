# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import os

# Define path to VERSION file
version_file_path = os.path.join('xferx', 'VERSION')

# Main build steps
a = Analysis(
    ['xferx.py'],  # Entry point
    pathex=[],
    binaries=[],
    datas=[(version_file_path, 'xferx')],
    hiddenimports=collect_submodules('xferx'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='xferx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon=None,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
