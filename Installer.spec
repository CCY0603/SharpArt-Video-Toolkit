# -*- mode: python ; coding: utf-8 -*-
"""安装程序：单文件 EXE，内嵌已完成的主程序目录（含 ffmpeg/ffprobe）。"""

a = Analysis(
    ['installer.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('dist/SharpArtVideo', 'app_payload'),
    ],
    hiddenimports=[],
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
    name='SharpArtVideoInstaller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    manifest='app/win_manifest.manifest',
)
