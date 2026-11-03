PROMPT $g
rem ---------------------------------------------------------------------
rem This file executes the build command for the windows executable file.
rem It is here because I am lazy
rem ---------------------------------------------------------------------
del *.pyc
rmdir /S /Q dist
rmdir /S /Q dist64

rem rmdir /S /Q dist32
rem PATH = %PATH%;D:\Python27_64\DLLs;D:\Python27_64\libs;D:\Python27_32\DLLs;D:\Python27_32\libs;D:\windows\System32
rem D:\Python27_32\python.exe py2exe_setup.py py2exe
rem rmdir /S /Q build
rem move dist dist32
rem pause

del *.pyc
PATH = %PATH%;D:\Python27_32\DLLs;D:\Python27_32\libs;D:\windows\System32;D:\Python27_32;D:\windows\System;D:\Python27_64\DLLs;D:\Python27_64\libs
D:\Python27_64\python.exe py2exe_setup.py py2exe
rmdir /S /Q build
move dist dist64
pause

