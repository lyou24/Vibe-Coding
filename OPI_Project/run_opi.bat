@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   OPI (Ongeki Power Indicator) ランチャー
echo ===================================================

if not exist ".venv\Scripts\activate.bat" (
    echo 仮想環境が見つかりません。自動セットアップを開始します...

    python --version >nul 2>&1
    if errorlevel 1 (
        echo [エラー] Python がインストールされていないか、PATHに登録されていません。
        echo Python 3.10以上をインストールして PATH に追加してから再実行してください。
        pause
        exit /b 1
    )

    echo 仮想環境を作成しています [.venv]...
    python -m venv .venv
    if errorlevel 1 (
        echo [エラー] 仮想環境の作成に失敗しました。
        pause
        exit /b 1
    )

    echo 仮想環境をアクティベートしています...
    call .venv\Scripts\activate.bat

    echo pip を最新版にアップグレードしています...
    python -m pip install --upgrade pip

    echo 必要なライブラリをインストールしています [requirements.txt]...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [エラー] パッケージのインストールに失敗しました。
        pause
        exit /b 1
    )
    echo セットアップが正常に完了しました。
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo OPI Webアプリケーションを起動しています...
echo ブラウザが自動的に開きます...
streamlit run app.py %*
pause
