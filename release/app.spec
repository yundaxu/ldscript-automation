# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 模拟器脚本自助 v1.0 打包配置"""

import os as _os

_block_cipher = None

# SPECPATH 是 spec 文件所在目录，项目根是其父目录
_ROOT = _os.path.dirname(SPECPATH)

# easyocr 模型文件 — 从用户目录复制到打包中
_MODEL_DIR = _os.path.join(_os.path.expanduser("~"), ".EasyOCR", "model")
_model_files = []
if _os.path.exists(_MODEL_DIR):
    for _f in _os.listdir(_MODEL_DIR):
        _src = _os.path.join(_MODEL_DIR, _f)
        _model_files.append((_src, _os.path.join("EasyOCR", "model", _f)))

_added = [
    (_os.path.join(_ROOT, "templates"), "templates"),
    (_os.path.join(_ROOT, "configs"), "configs"),
    (_os.path.join(_ROOT, "pipelines"), "pipelines"),
    (_os.path.join(_ROOT, "images"), "images"),
]

a = Analysis(
    [_os.path.join(_ROOT, "panel.py")],
    pathex=[_ROOT],
    binaries=[],
    datas=_added + _model_files,
    hiddenimports=[
        "cv2",
        "numpy",
        "easyocr",
        "flask",
        "yaml",
        "PIL",
        "PIL.Image",
        "auto_ld",
        "auto_ld._compat",
        "auto_ld.log",
        "auto_ld.controller",
        "auto_ld.controller.adb",
        "auto_ld.controller.touch",
        "auto_ld.controller.matcher",
        "auto_ld.controller.ocr",
        "auto_ld.controller.coords",
        "auto_ld.controller.packages",
        "auto_ld.controller.registry",
        "auto_ld.emulator",
        "auto_ld.emulator.ldplayer",
        "auto_ld.runtime",
        "auto_ld.runtime.context",
        "auto_ld.runtime.loader",
        "auto_ld.pipeline",
        "auto_ld.pipeline.engine",
        "auto_ld.scheduler",
        "auto_ld.scheduler.daily",
        "auto_ld.scheduler.schedule_worker",
        "auto_ld.web",
        "auto_ld.web.routes",
        "auto_ld.web.sse",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=_block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=_block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="模拟器脚本自助",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
