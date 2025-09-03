@echo off
set FileVersion=1.0.0.0
set ProductVersion=1.6.0.0

python -m nuitka --onefile --standalone --enable-plugins=pyqt5 --remove-output --windows-console-mode=disable --output-dir=dist --output-filename=Scratchpad.exe --follow-imports --windows-icon-from-ico=ICON.ico --include-data-files=style.css=style.css --include-data-files=scratchpad.png=scratchpad.png --product-name="Scratchpad" --company-name="Raven Development Team" --file-description="Simple, professional plaintext editor." --file-version=%FileVersion% --product-version=%ProductVersion% --copyright="Copyright (c) 2025 Raven Development Team" --onefile-tempdir-spec="{CACHE_DIR}\RavenDevelopmentTeam\Scratchpad\{VERSION}" scratchpad.py
pause