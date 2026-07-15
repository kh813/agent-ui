@echo off
rem Windows wrapper for build-skills.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-skills.ps1"
