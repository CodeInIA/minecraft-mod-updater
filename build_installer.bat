@echo off
REM Build the executable and the Windows installer locally.
REM Requires: Python, "pip install -r requirements.txt pyinstaller" and Inno Setup 6.
pyinstaller --noconfirm mod_updater.spec || goto :error
"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer-script.iss || goto :error
echo.
echo Installer created in the "installer" folder.
pause
exit /b 0
:error
echo Build failed.
pause
exit /b 1
