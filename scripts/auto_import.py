"""
ALK 工場停止管理システム - 自動インポートデーモン

動作の流れ:
  1. Outlook受信トレイを監視 → 1c_alk@rfpgroup.ru からの未読メールを検出
  2. XLSX添付ファイルを Desktop/１C生産データ/ に保存 → 既読にする
  3. そのファイルを自動解析 → operative_data.csv に取込
  4. Windowsトースト通知でお知らせ

起動方法: scripts/start.bat をダブルクリック
"""

import sys
import time
import json
import logging
import io
import re
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from utils.operative_parser import is_operative_format, parse_operative_file
from utils.data_store import add_operative

# ═══════════════════════════════════════════════════════════
#  設定
# ═══════════════════════════════════════════════════════════
TARGET_SENDER = "1c_alk@rfpgroup.ru"          # 監視する送信者メールアドレス
WATCH_DIR     = Path(r"C:\Users\r-akiyama\Desktop\１C生産データ")
STATUS_FILE   = BASE / "data" / "auto_import_status.json"
LOG_FILE      = BASE / "logs" / "auto_import.log"
POLL_SECONDS  = 60    # メール＆フォルダチェック間隔（秒）

# ── アラートメール設定（空欄なら送信しない） ──────────────────
ALERT_EMAIL_TO   = ""       # 例: "r-akiyama@example.com"
ALERT_EMAIL_FROM = ""       # 例: "alk-system@example.com"
ALERT_SMTP_HOST  = ""       # 例: "smtp.office365.com"
ALERT_SMTP_PORT  = 587
ALERT_SMTP_USER  = ""
ALERT_SMTP_PASS  = ""
# 停止時間がこの値（時間）を超えたらメール通知
ALERT_THRESHOLD_HOURS = 2.0
# ═══════════════════════════════════════════════════════════

LOG_FILE.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── ファイル名の使用不可文字を除去 ──────────────────────────
def _clean(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


# ── Windows トースト通知 ──────────────────────────────────────
def _notify(title: str, msg: str) -> None:
    try:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            f'$n.BalloonTipTitle = "{title}"; '
            f'$n.BalloonTipText  = "{msg}"; '
            "$n.BalloonTipIcon  = 'Info'; "
            "$n.Visible = $true; "
            "$n.ShowBalloonTip(5000); "
            "Start-Sleep -Milliseconds 5500; "
            "$n.Dispose()"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


# ── アラートメール送信 ────────────────────────────────────────
def _send_alert_email(subject: str, body: str) -> None:
    """停止アラートをメールで送信する"""
    if not all([ALERT_EMAIL_TO, ALERT_EMAIL_FROM, ALERT_SMTP_HOST,
                ALERT_SMTP_USER, ALERT_SMTP_PASS]):
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart()
        msg["From"]    = ALERT_EMAIL_FROM
        msg["To"]      = ALERT_EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT) as s:
            s.starttls()
            s.login(ALERT_SMTP_USER, ALERT_SMTP_PASS)
            s.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO, msg.as_string())
        log.info(f"アラートメール送信: {subject}")
    except Exception as e:
        log.warning(f"メール送信エラー: {e}")


# ── 停止アラートチェック ──────────────────────────────────────
def _check_stoppage_alert() -> None:
    """当日の停止時間が閾値を超えていればメール通知"""
    if not ALERT_EMAIL_TO:
        return
    try:
        sys.path.insert(0, str(BASE))
        from utils.data_store import get_stoppages
        today_str = datetime.now().strftime("%Y-%m-%d")
        df = get_stoppages("", today_str, today_str)
        if df.empty:
            return
        total_h = df["duration_minutes"].sum() / 60
        if total_h >= ALERT_THRESHOLD_HOURS:
            _send_alert_email(
                f"【ALKアラート】本日の停止時間 {total_h:.1f}h が閾値を超えました",
                f"本日（{today_str}）の停止時間合計: {total_h:.1f} 時間\n"
                f"閾値: {ALERT_THRESHOLD_HOURS} 時間\n"
                f"停止件数: {len(df)} 件\n\n"
                f"システム: ALK 工場管理システム",
            )
    except Exception as e:
        log.warning(f"停止アラートチェックエラー: {e}")


# ── ステータスファイル更新 ────────────────────────────────────
def _save_status(last_check: str, last_import: str, today_count: int,
                 last_file: str = "", last_error: str = "") -> None:
    try:
        STATUS_FILE.parent.mkdir(exist_ok=True)
        STATUS_FILE.write_text(
            json.dumps({
                "last_check":  last_check,
                "last_import": last_import,
                "today_count": today_count,
                "last_file":   last_file,
                "last_error":  last_error,
                "running":     True,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


# ── Outlook から未読メールの添付ファイルをダウンロード ──────────
def _check_outlook() -> list[Path]:
    """未読メールの XLSX 添付を WATCH_DIR に保存。保存したパスのリストを返す"""
    downloaded: list[Path] = []
    try:
        import win32com.client
    except ImportError:
        log.warning("pywin32 がインストールされていません。Outlook監視をスキップします。")
        log.warning("  インストール: pip install pywin32")
        return downloaded

    try:
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
    except Exception as e:
        log.warning(f"Outlook接続エラー（Outlookが起動していない可能性）: {e}")
        return downloaded

    WATCH_DIR.mkdir(parents=True, exist_ok=True)

    # 監視フォルダを探す（"1c" ルートフォルダ → なければ受信トレイ）
    target_folder = None
    try:
        for store in ns.Stores:
            root = store.GetRootFolder()
            for f in root.Folders:
                if f.Name == "1c":
                    target_folder = f
                    break
            if target_folder:
                break
    except Exception as e:
        log.warning(f"フォルダ探索エラー: {e}")

    if target_folder is None:
        try:
            target_folder = ns.GetDefaultFolder(6)  # 受信トレイにフォールバック
            log.info("「1c」フォルダが見つからないため受信トレイを監視します")
        except Exception as e:
            log.warning(f"受信トレイ取得エラー: {e}")
            return downloaded

    try:
        # 未読メールだけ取得（Restrict で絞り込み）
        unread_items = target_folder.Items.Restrict("[Unread] = True")
    except Exception:
        unread_items = target_folder.Items

    for item in unread_items:
        try:
            if item.Class != 43:  # 43 = olMail
                continue

            sender = ""
            try:
                sender = item.SenderEmailAddress or ""
            except Exception:
                pass
            if TARGET_SENDER.lower() not in sender.lower():
                continue

            if item.Attachments.Count == 0:
                continue

            try:
                date_str = item.ReceivedTime.strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now().strftime("%Y-%m-%d")

            for j in range(1, item.Attachments.Count + 1):
                try:
                    att  = item.Attachments.Item(j)
                    fname = att.FileName
                    if not fname.lower().endswith(".xlsx"):
                        continue

                    stem = Path(fname).stem
                    new_name = _clean(f"{date_str}_{stem}.xlsx")
                    dest = WATCH_DIR / new_name

                    if dest.exists():
                        log.debug(f"  スキップ（既存）: {new_name}")
                        continue

                    att.SaveAsFile(str(dest))
                    log.info(f"  メール受信 → 保存: {new_name}  (件名: {item.Subject})")
                    downloaded.append(dest)
                except Exception as e:
                    log.warning(f"  添付保存エラー: {e}")

            # 既読にする
            item.UnRead = False

        except Exception:
            continue

    return downloaded


# ── ファイルが完全に書き込まれているか確認 ──────────────────────
def _is_stable(path: Path, wait: float = 2.0) -> bool:
    try:
        size1 = path.stat().st_size
        time.sleep(wait)
        size2 = path.stat().st_size
        return size1 == size2 and size2 > 0
    except Exception:
        return False


_MONTH_JP = {
    1:"1月", 2:"2月", 3:"3月", 4:"4月", 5:"5月", 6:"6月",
    7:"7月", 8:"8月", 9:"9月", 10:"10月", 11:"11月", 12:"12月",
}

# ── ファイルを年/月フォルダへ移動 ────────────────────────────────
def _archive_file(path: Path) -> None:
    """ファイル名の YYYY-MM-DD プレフィックスから年/月を判定して移動する"""
    import re, shutil
    m = re.match(r"(\d{4})-(\d{2})-\d{2}", path.name)
    if m:
        year  = int(m.group(1))
        month = int(m.group(2))
    else:
        year  = datetime.now().year
        month = datetime.now().month

    month_label = f"{month:02d}_{_MONTH_JP[month]}"
    dest_dir = WATCH_DIR / str(year) / month_label
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / path.name
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{path.stem}_{counter}{path.suffix}"
        counter += 1

    shutil.move(str(path), str(dest))
    log.info(f"  整理完了: {path.name} → {year}/{month_label}/")


# ── 1ファイルを解析・取込 ────────────────────────────────────
def _process_file(path: Path) -> tuple[int, int]:
    try:
        buf = io.BytesIO(path.read_bytes())
        buf.seek(0)
        if not is_operative_format(buf):
            log.info(f"  スキップ（1C日報フォーマット外）: {path.name}")
            return 0, 0

        buf.seek(0)
        records, detected_date, errors = parse_operative_file(buf)
        for e in errors:
            log.warning(f"  [{path.name}] {e}")

        if not records:
            log.warning(f"  [{path.name}] 指標データを抽出できませんでした")
            return 0, 0

        added, skipped = add_operative(records)
        log.info(
            f"  [{path.name}] 取込完了: {added}件追加 / {skipped}件スキップ"
            f" (日付={detected_date})"
        )
        return added, skipped
    except Exception as e:
        log.error(f"  [{path.name}] 取込エラー: {e}", exc_info=True)
        return 0, 0


# ── フォルダスキャン → 未処理ファイルを取込 ─────────────────────
def _scan_folder(processed: set, today_count: int,
                 last_import: str, last_file: str) -> tuple[int, str, str]:
    for xlsx in sorted(WATCH_DIR.glob("*.xlsx")):
        key = f"{xlsx.name}|{xlsx.stat().st_size}"
        if key in processed:
            continue

        log.info(f"新ファイル検出: {xlsx.name}")

        if not _is_stable(xlsx):
            log.info(f"  書き込み中のためスキップ（次回再試行）: {xlsx.name}")
            continue

        processed.add(key)
        added, _ = _process_file(xlsx)

        # 取込結果に関わらずアーカイブフォルダへ移動
        try:
            _archive_file(xlsx)
        except Exception as e:
            log.warning(f"  整理エラー: {e}")

        if added > 0:
            today_count += added
            last_import  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            last_file    = xlsx.name
            _notify(
                "ALK インポート完了",
                f"{xlsx.name}  —  {added}件の生産指標を取り込みました",
            )

    return today_count, last_import, last_file


# ── メインループ ─────────────────────────────────────────────
def main() -> None:
    log.info("=" * 55)
    log.info("ALK 自動インポート 起動")
    log.info(f"  Outlook監視 : {TARGET_SENDER}")
    log.info(f"  フォルダ監視: {WATCH_DIR}")
    log.info(f"  チェック間隔: {POLL_SECONDS}秒")
    log.info("=" * 55)

    if not WATCH_DIR.exists():
        WATCH_DIR.mkdir(parents=True, exist_ok=True)
        log.info(f"監視フォルダを作成しました: {WATCH_DIR}")

    processed: set = set()
    today_count: int = 0
    last_import: str = ""
    last_file:   str = ""

    # 起動時: ルートに残っている既存ファイルを年/月フォルダへ整理
    existing = list(WATCH_DIR.glob("*.xlsx"))
    if existing:
        log.info(f"既存ファイル {len(existing)} 件を年/月フォルダへ整理中...")
        for xlsx in existing:
            try:
                _archive_file(xlsx)
            except Exception as e:
                log.warning(f"  整理スキップ: {xlsx.name} ({e})")
            processed.add(f"{xlsx.name}|0")  # 移動済みなのでサイズ0でマーク
        log.info("既存ファイルの整理完了")
    else:
        log.info("ルートに整理対象ファイルなし")

    log.info("監視開始...")

    cycle = 0
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_error = ""
        cycle += 1
        try:
            # 1) Outlook から未読メールの添付を取得
            new_files = _check_outlook()

            # 2) フォルダをスキャンして新ファイルを取込
            today_count, last_import, last_file = _scan_folder(
                processed, today_count, last_import, last_file
            )
            _save_status(now, last_import, today_count, last_file)

            # 3) 停止アラートチェック（10サイクルに1回 ≒ 10分ごと）
            if cycle % 10 == 0:
                _check_stoppage_alert()

            # 10サイクルに1回（約10分）は生存確認ログを出力
            if cycle % 10 == 0 or new_files:
                log.info(f"稼働中 #{cycle} | 本日取込: {today_count}件 | 最終取込: {last_import or '未'}")

        except Exception as e:
            last_error = str(e)
            log.error(f"エラー: {e}", exc_info=True)
            _save_status(now, last_import, today_count, last_file, last_error=last_error)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
