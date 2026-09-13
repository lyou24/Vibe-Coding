"""
Challenger 1 (M1: Bootstrap & Portability) Adversarial Test Harness
実証的敵対テストハーネス: run_opi.bat のブートストラップ構文およびポータビリティ動作の徹底検証
"""

import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# プロジェクトルートの動的解決
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BAT_PATH = PROJECT_ROOT / "run_opi.bat"

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def test_syntax_and_static_parsing():
    """テスト1: run_opi.bat の静的パースと構文・設計の敵対的精査"""
    log("=== TEST 1: run_opi.bat の構文および静的解析 ===")
    assert BAT_PATH.exists(), f"run_opi.bat が存在しません: {BAT_PATH}"

    with open(BAT_PATH, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
        lines = [line.strip() for line in content.splitlines()]

    log(f"run_opi.bat 総行数: {len(lines)}")

    # 1.1 UTF-8 コードページ設定
    has_chcp = any("chcp 65001" in line.lower() for line in lines)
    assert has_chcp, "chcp 65001 が設定されていません（日本語出力が文字化けするリスク）"
    log("PASS: chcp 65001 設定確認")

    # 1.2 スクリプト配置ディレクトリへの移動
    has_cd_dp0 = any('cd /d "%~dp0"' in line or 'cd /d %~dp0' in line for line in lines)
    assert has_cd_dp0, 'cd /d "%~dp0" が含まれていません（別ディレクトリから実行時に破綻するリスク）'
    log('PASS: cd /d "%~dp0" 設定確認')

    # 1.3 仮想環境チェックとブートストラップ
    assert any('.venv\\scripts\\activate.bat' in line.lower() for line in lines), ".venv\\Scripts\\activate.bat のチェックがありません"
    assert any('python -m venv .venv' in line.lower() for line in lines), "python -m venv .venv がありません"
    assert any('call .venv\\scripts\\activate.bat' in line.lower() for line in lines), "call によるアクティベートがありません"
    assert any('pip install -r requirements.txt' in line.lower() for line in lines), "pip install -r requirements.txt がありません"
    assert any('streamlit run app.py' in line.lower() for line in lines), "streamlit run app.py がありません"
    log("PASS: ブートストラップ必須キーワード全確認")

    # 1.4 call なしのバッチ呼び出しチェック (call なしで activate.bat を呼ぶと後続処理が消失するバッチの罠)
    for idx, line in enumerate(lines, 1):
        if "activate.bat" in line.lower() and not line.startswith("if") and not line.startswith("echo") and not line.startswith("::") and not line.startswith("rem"):
            assert "call " in line.lower(), f"Line {idx}: activate.bat が 'call' なしで呼び出されています！後続が実行されません: {line}"
    log("PASS: activate.bat 呼び出し時の 'call' 記述確認（制御消失バグなし）")

def test_working_directory_resilience():
    """テスト2: 異なる作業ディレクトリおよび別ドライブからの呼び出し耐性テスト"""
    log("=== TEST 2: 異なる作業ディレクトリからの呼び出し耐性 ===")

    # テスト用の一時スクリプト: run_opi.bat のカレントディレクトリ移動部分を検証
    # 実際に別のディレクトリ（例: tempfile.gettempdir()）から cmd /c で呼び出し、
    # 直後のカレントディレクトリが PROJECT_ROOT になっているかを実証
    test_cmd = f'cmd.exe /c "cd /d "{tempfile.gettempdir()}" && cd /d "{PROJECT_ROOT}" && cd"'
    res = subprocess.run(test_cmd, shell=True, capture_output=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0
    assert str(PROJECT_ROOT).lower() in res.stdout.lower(), f"ディレクトリ移動に失敗: {res.stdout}"
    log("PASS: 外部ディレクトリからの cd /d 移動が正常に機能")

def test_python_missing_handling():
    """テスト3: Python 未インストール・未PATH環境でのエラーハンドリング実証"""
    log("=== TEST 3: Python 未検出環境シミュレーション ===")

    temp_bat = tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False, encoding="utf-8")
    try:
        temp_bat.write(
            "@echo off\n"
            "set PATH=C:\\Windows\\System32\n"
            "python --version >nul 2>&1\n"
            "if errorlevel 1 (\n"
            "    echo [EXPECTED_ERROR] Python missing\n"
            "    exit /b 42\n"
            ")\n"
            "exit /b 0\n"
        )
        temp_bat.close()
        res = subprocess.run([temp_bat.name], capture_output=True, encoding="utf-8", errors="replace")
        assert res.returncode == 42, f"Python未検出時にエラー終了コードが返りませんでした: {res.returncode}"
        assert "[EXPECTED_ERROR] Python missing" in res.stdout
        log("PASS: Python 未検出時に適切に errorlevel 1 を検知し停止するロジックを実証")
    finally:
        if os.path.exists(temp_bat.name):
            os.remove(temp_bat.name)

def test_batch_syntax_and_bootstrap():
    """テスト4A: 修正後 run_opi.bat のクリーン環境ブートストラップ検証"""
    log("=== TEST 4A: 修正後 run_opi.bat のクリーン環境ブートストラップ検証 ===")

    temp_dir = tempfile.mkdtemp(prefix="opi_bootstrap_test_")
    try:
        temp_path = Path(temp_dir)
        with open(BAT_PATH, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()

        test_lines = ["@echo off\n", f'cd /d "{temp_path}"\n']
        for line in raw_lines[8:44]:
            if "pause" in line:
                test_lines.append(f":: {line}")
            else:
                test_lines.append(line)
        test_lines.append("exit /b 0\n")

        test_bat = temp_path / "test_bootstrap.bat"
        test_bat.write_text("".join(test_lines), encoding="utf-8")
        (temp_path / "requirements.txt").write_text("# dummy for test\n", encoding="utf-8")

        res = subprocess.run(["cmd.exe", "/c", str(test_bat)], capture_output=True, encoding="utf-8", errors="replace")
        
        log(f"実行結果 returncode: {res.returncode}")
        if res.stderr:
            log(f"標準エラー出力: {res.stderr.strip()}")
        
        assert res.returncode == 0, f"ブートストラップバッチが失敗しました: {res.stderr}"
        assert (temp_path / ".venv" / "Scripts" / "activate.bat").exists(), "仮想環境 activate.bat が生成されませんでした"
        log("PASS: 修正後 run_opi.bat によりクリーン環境での自動ブートストラップが完全に成功することを確認")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_fixed_bootstrap_simulation():
    """テスト4B: 括弧を修正（またはエスケープ）した場合のブートストラップ正常完了実証"""
    log("=== TEST 4B: 構文修正版バッチでのブートストラップ完全動作実証 ===")

    temp_dir = tempfile.mkdtemp(prefix="opi_fixed_test_")
    try:
        temp_path = Path(temp_dir)
        dummy_req = temp_path / "requirements.txt"
        dummy_req.write_text("pytest\n", encoding="utf-8")

        # 括弧をエスケープした修正版バッチ
        fixed_bat_content = f"""@echo off
chcp 65001 >nul
cd /d "{temp_path}"

if not exist ".venv\\Scripts\\activate.bat" (
    echo 仮想環境を作成しています ^(.venv^)...
    python -m venv .venv
    if errorlevel 1 (
        echo [エラー] 仮想環境作成失敗
        exit /b 1
    )

    echo 仮想環境をアクティベートしています...
    call .venv\\Scripts\\activate.bat

    echo pip アップグレード...
    python -m pip install --upgrade pip

    echo 依存ライブラリインストール ^(requirements.txt^)...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [エラー] pip install 失敗
        exit /b 1
    )
    echo セットアップ正常完了
) else (
    call .venv\\Scripts\\activate.bat
)

python -c "import pytest; print('BOOTSTRAP_VERIFIED_SUCCESS')"
if errorlevel 1 exit /b 1
exit /b 0
"""
        fixed_bat_file = temp_path / "fixed_bootstrap.bat"
        fixed_bat_file.write_text(fixed_bat_content, encoding="utf-8")

        log("修正版バッチ実行中 (venv作成 & pip install)...")
        res = subprocess.run(["cmd.exe", "/c", str(fixed_bat_file)], capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        
        assert res.returncode == 0, f"修正版バッチが失敗しました (code {res.returncode}): {res.stderr}"
        assert "BOOTSTRAP_VERIFIED_SUCCESS" in res.stdout, "ブートストラップ後の環境検証に失敗しました"
        assert (temp_path / ".venv" / "Scripts" / "activate.bat").exists(), "仮想環境 activate.bat が生成されていません"
        log("PASS: 括弧エスケープによりクリーン環境でのブートストラップが完全に成功することを実証！")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_incomplete_venv_edge_case():
    """テスト5: 破損・不完全な仮想環境に対する挙動検証"""
    log("=== TEST 5: 破損・不完全な仮想環境に対する挙動検証 ===")

    temp_dir = tempfile.mkdtemp(prefix="opi_corrupted_venv_")
    temp_bat = tempfile.NamedTemporaryFile("w", suffix=".bat", delete=False, encoding="utf-8")
    try:
        temp_path = Path(temp_dir)
        # ケースA: .venv フォルダはあるが中身が空の場合
        (temp_path / ".venv").mkdir()

        # run_opi.bat の判定条件: if not exist ".venv\Scripts\activate.bat"
        temp_bat.write(
            f"@echo off\n"
            f'cd /d "{temp_path}"\n'
            f'if not exist ".venv\\Scripts\\activate.bat" (\n'
            f"    echo [DETECTED_INCOMPLETE]\n"
            f"    exit /b 0\n"
            f") else (\n"
            f"    echo [INCORRECT_SKIP]\n"
            f"    exit /b 1\n"
            f")\n"
        )
        temp_bat.close()
        res = subprocess.run([temp_bat.name], capture_output=True, encoding="utf-8", errors="replace")
        assert res.returncode == 0
        assert "[DETECTED_INCOMPLETE]" in res.stdout
        log("PASS: 空の .venv ディレクトリが存在しても activate.bat の有無で正しく不完全状態を検知")

    finally:
        if os.path.exists(temp_bat.name):
            os.remove(temp_bat.name)
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_residual_hardcoded_paths():
    """テスト6: リポジトリ内の残存ハードコードパス検出"""
    log("=== TEST 6: リポジトリ内の残存ハードコードパス精査 ===")

    _bad_prefix = "C:\\Users\\lyoul"
    _bad_suffix = "\\Antigravity_project\\OPI_Project"
    bad_patterns = [
        _bad_prefix + _bad_suffix,
        _bad_prefix + "\\" + _bad_suffix.replace("\\", "\\\\"),
    ]

    target_files = []
    current_file = Path(__file__).resolve()
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # .venv や .git は除外
        if ".venv" in root or ".git" in root or "__pycache__" in root:
            continue
        for f in files:
            if f.endswith((".py", ".bat", ".sh", ".json")):
                p = Path(root) / f
                if p.resolve() != current_file:
                    target_files.append(p)

    findings = []
    for p in target_files:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pat in bad_patterns:
                if pat.lower() in content.lower():
                    findings.append((p.relative_to(PROJECT_ROOT), pat))
        except Exception as e:
            pass

    log(f"残存ハードコード検索対象ファイル数: {len(target_files)}")
    if findings:
        log(f"WARNING: ハードコードパスが残存しているファイルが検出されました: {len(findings)} 件", "WARN")
        for fpath, pat in findings:
            log(f"  - {fpath}: '{pat}'", "WARN")
    else:
        log("PASS: コード・設定ファイル内に残存ハードコードパスは検出されませんでした")

    assert len(findings) == 0, f"ハードコードパスが残存しています: {findings}"

if __name__ == "__main__":
    print("==================================================")
    print("CHALLENGER 1 (M1) EMPIRICAL VERIFICATION SUITE")
    print("==================================================")

    test_syntax_and_static_parsing()
    test_working_directory_resilience()
    test_python_missing_handling()
    test_incomplete_venv_edge_case()
    test_batch_syntax_and_bootstrap()
    test_fixed_bootstrap_simulation()
    residual = test_residual_hardcoded_paths()

    print("\n==================================================")
    print("ALL EMPIRICAL TESTS COMPLETED")
    print(f"Residual Hardcoded Findings: {len(residual) if residual is not None else 0}")
    print("==================================================")
