@echo off
chcp 65001 >nul 2>&1
title Emare Security OS RMM Agent Kurulumu
color 0B

:: ═══════════════════════════════════════════════════════════════
::  Emare Security OS RMM Agent — Windows Tikla-Calistir Kurulum
:: ═══════════════════════════════════════════════════════════════
::  Cift tiklayarak calistirin.
::  Yonetici yetkisi otomatik istenir.
:: ═══════════════════════════════════════════════════════════════

:: ─── YÖNETİCİ YETKİSİ KONTROLÜ ────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Yonetici yetkisi isteniyor...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: ─── DOSYA KONTROLÜ ────────────────────────────────────
if not exist "%~dp0EmareAgent.ps1" (
    echo.
    echo HATA: EmareAgent.ps1 bu klasorde bulunamadi!
    echo       Kur-EmareAgent.bat ve EmareAgent.ps1 ayni klasorde olmali.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0Install-EmareAgent.ps1" (
    echo.
    echo HATA: Install-EmareAgent.ps1 bu klasorde bulunamadi!
    echo.
    pause
    exit /b 1
)

:: ─── BAŞLIK ────────────────────────────────────────────
cls
echo.
echo ╔══════════════════════════════════════════════════╗
echo ║                                                  ║
echo ║   Emare Security OS RMM Agent Kurulumu               ║
echo ║   Windows — Tikla Calistir                       ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: ─── SUNUCU ADRESİ ─────────────────────────────────────
echo Emare Security OS sunucu adresini girin.
echo Ornek: https://firewall.example.com
echo.
set /p SERVER_URL="Sunucu adresi: "

if "%SERVER_URL%"=="" (
    echo.
    echo HATA: Sunucu adresi bos olamaz.
    pause
    exit /b 1
)

echo.

:: ─── İŞLEM SEÇİMİ ─────────────────────────────────────
echo Ne yapmak istiyorsunuz?
echo.
echo   1) Kur ve baslat  (yeni kurulum)
echo   2) Kaldir
echo   3) Durum kontrol
echo   4) Yeniden baslat
echo   5) Cikis
echo.
set /p CHOICE="Seciminiz [1-5]: "

if "%CHOICE%"=="1" set ACTION=Install
if "%CHOICE%"=="2" set ACTION=Uninstall
if "%CHOICE%"=="3" set ACTION=Status
if "%CHOICE%"=="4" set ACTION=Restart
if "%CHOICE%"=="5" exit /b 0

if "%ACTION%"=="" (
    echo Gecersiz secim.
    pause
    exit /b 1
)

echo.
echo ────────────────────────────────────────────────────
echo.

:: ─── POWERSHELL INSTALLER'I ÇAĞIR ──────────────────────
powershell.exe -ExecutionPolicy Bypass -File "%~dp0Install-EmareAgent.ps1" -ServerUrl "%SERVER_URL%" -Action %ACTION%

echo.
echo ────────────────────────────────────────────────────

if %errorlevel% equ 0 (
    echo Islem basariyla tamamlandi!
) else (
    echo Islem sirasinda hata olustu. (Kod: %errorlevel%)
)

echo.
echo Bu pencereyi kapatabilirsiniz.
pause
