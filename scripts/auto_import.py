"""
ALK 工場停止管理システム - 自動インポートデーモン

メール監視の優先順位:
  1. IMAP（新旧どちらのOutlookでも動作・Outlook不要）
  2. COM（旧Outlookが起動中の場合のみ・pywin32が必要）

起動方法: scripts/start.bat をダブルクリック
"""

import sys
import time
import json
import logging
import io
import re
import subprocess
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from utils.operative_parser import is_operative_format, parse_operative_file
from utils.shift_report_parser import is_shift_report_format, parse_shift_report
from utils.data_store import add_operative, add_stoppages

# ═══════════════════════════════════════════════════════════
#  設定（secrets.toml から読み込み）
# ═══════════════════════════════════════════════════════════
import tomllib

_secrets_path = BASE / ".streamlit" / "secrets.toml"
with open(_secrets_path, "rb") as _f:
    _secrets = tomllib.load(_f)

_email_cfg    = _secrets.get("email", {})
IMAP_HOST     = _email_cfg.get("imap_host", "outlook.office365.com")
IMAP_PORT     = int(_email_cfg.get("imap_port", 993))
EMAIL_ADDRESS = _email_cfg.get("address", "")
EMAIL_PASS    = _email_cfg.get("password", "")
TARGET_SENDER = _email_cfg.get("target_sender", "1c_alk@rfpgroup.ru")
# M365はIMAP基本認証が廃止済みのため、O365アカウントではfalseにしてCOM経由を使う
USE_IMAP      = bool(_email_cfg.get("use_imap", True))

WATCH_DIR        = Path(r"C:\Users\r-akiyama\Desktop\１C生産データ")
UNIMPORTED_DIR   = WATCH_DIR / "未取込みデータ"   # ダウンロード直後の一時置き場
STATUS_FILE      = BASE / "data" / "auto_import_status.json"
LOG_FILE         = BASE / "logs" / "auto_import.log"
POLL_SECONDS     = 60

# ── アラートメール設定（空欄なら送信しない） ──────────────────
ALERT_EMAIL_TO        = ""
ALERT_EMAIL_FROM      = ""
ALERT_SMTP_HOST       = ""
ALERT_SMTP_PORT       = 587
ALERT_SMTP_USER       = ""
ALERT_SMTP_PASS       = ""
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


def _clean(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


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


def _send_alert_email(subject: str, body: str) -> None:
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


def _check_stoppage_alert() -> None:
    if not ALERT_EMAIL_TO:
        return
    try:
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


# ══════════════════════════════════════════════════════════
#  方法1: IMAP（新旧どちらのOutlookでも動作）
# ══════════════════════════════════════════════════════════
def _check_imap() -> list[Path]:
    """IMAPで未読メールのXLSX添付をWATCH_DIRに保存"""
    downloaded: list[Path] = []
    if not USE_IMAP:
        return downloaded
    if not EMAIL_ADDRESS or not EMAIL_PASS:
        log.warning("IMAP設定がありません（secrets.tomlのemailセクションを確認）")
        return downloaded

    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(EMAIL_ADDRESS, EMAIL_PASS)
    except imaplib.IMAP4.error as e:
        log.warning(f"IMAPログインエラー: {e}")
        return downloaded
    except Exception as e:
        log.warning(f"IMAP接続エラー: {e}")
        return downloaded

    try:
        # 「1c」フォルダを探す → なければ受信トレイ
        status, folders = mail.list()
        target_folder = "INBOX"
        if status == "OK":
            for f in folders:
                fname = f.decode() if isinstance(f, bytes) else f
                if '"1c"' in fname or "'1c'" in fname or fname.strip().endswith("1c"):
                    target_folder = "1c"
                    break

        mail.select(target_folder)
        log.debug(f"IMAPフォルダ: {target_folder}")

        # 未読メールを検索
        _, msg_ids = mail.search(None, "UNSEEN")
        ids = msg_ids[0].split()

        WATCH_DIR.mkdir(parents=True, exist_ok=True)

        for mid in ids:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            # 送信者チェック
            sender = msg.get("From", "")
            if TARGET_SENDER.lower() not in sender.lower():
                continue

            # 日付取得
            date_str = datetime.now().strftime("%Y-%m-%d")
            try:
                from email.utils import parsedate_to_datetime
                date_str = parsedate_to_datetime(msg.get("Date", "")).strftime("%Y-%m-%d")
            except Exception:
                pass

            # 添付ファイルを保存
            saved = False
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is None:
                    continue
                fname = part.get_filename()
                if not fname:
                    continue
                # ファイル名デコード
                decoded = decode_header(fname)
                fname = "".join(
                    t.decode(enc or "utf-8") if isinstance(t, bytes) else t
                    for t, enc in decoded
                )
                if not fname.lower().endswith(".xlsx"):
                    continue

                stem = Path(fname).stem
                new_name = _clean(f"未取込み_{date_str}_{stem}.xlsx")
                UNIMPORTED_DIR.mkdir(parents=True, exist_ok=True)
                dest = UNIMPORTED_DIR / new_name
                if dest.exists():
                    log.debug(f"  スキップ（既存）: {new_name}")
                    continue

                dest.write_bytes(part.get_payload(decode=True))
                log.info(f"  IMAP受信 → 未取込みフォルダへ保存: {new_name}  (件名: {msg.get('Subject', '')})")
                downloaded.append(dest)
                saved = True

            # 既読にする
            if saved:
                mail.store(mid, "+FLAGS", "\\Seen")

    except Exception as e:
        log.warning(f"IMAPエラー: {e}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return downloaded


# ══════════════════════════════════════════════════════════
#  方法2: COM（旧Outlookが起動中の場合のみ）
# ══════════════════════════════════════════════════════════
def _check_outlook_com() -> list[Path]:
    """旧OutlookのCOM経由で未読メールの添付を取得"""
    downloaded: list[Path] = []
    try:
        import win32com.client
    except ImportError:
        return downloaded  # pywin32 未インストール時はスキップ

    try:
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")
        ns = outlook.GetNamespace("MAPI")
    except Exception as e:
        log.debug(f"COM接続不可（新Outlookまたは未起動）: {e}")
        return downloaded

    WATCH_DIR.mkdir(parents=True, exist_ok=True)

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
    except Exception:
        pass

    if target_folder is None:
        try:
            target_folder = ns.GetDefaultFolder(6)
        except Exception:
            return downloaded

    try:
        unread_items = target_folder.Items.Restrict("[Unread] = True")
    except Exception:
        unread_items = target_folder.Items

    for item in unread_items:
        try:
            if item.Class != 43:
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
                    att = item.Attachments.Item(j)
                    fname = att.FileName
                    if not fname.lower().endswith(".xlsx"):
                        continue
                    stem = Path(fname).stem
                    new_name = _clean(f"未取込み_{date_str}_{stem}.xlsx")
                    UNIMPORTED_DIR.mkdir(parents=True, exist_ok=True)
                    dest = UNIMPORTED_DIR / new_name
                    if dest.exists():
                        continue
                    att.SaveAsFile(str(dest))
                    log.info(f"  COM受信 → 未取込みフォルダへ保存: {new_name}")
                    downloaded.append(dest)
                except Exception as e:
                    log.warning(f"  添付保存エラー: {e}")
            item.UnRead = False
        except Exception:
            continue

    return downloaded


# ══════════════════════════════════════════════════════════
#  共通処理
# ══════════════════════════════════════════════════════════
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


def _archive_file(path: Path) -> None:
    import shutil
    # 「未取込み_YYYY-MM-DD_...」→「取込済み_YYYY-MM-DD_...」にリネーム
    new_stem = re.sub(r"^未取込み_", "取込済み_", path.stem)
    new_name = new_stem + path.suffix

    # 年月フォルダを決定（ファイル名中の日付を使用）
    m = re.search(r"(\d{4})-(\d{2})-\d{2}", path.name)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    else:
        year, month = datetime.now().year, datetime.now().month
    month_label = f"{month:02d}_{_MONTH_JP[month]}"
    dest_dir = WATCH_DIR / str(year) / month_label
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / new_name
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{new_stem}_{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(dest))
    log.info(f"  整理完了: {path.name} → {year}/{month_label}/{dest.name}")


# Оп.сводки の補助バリアント（同日でmainより古いデータ）は取り込まない
_OPERATIVE_SKIP_PATTERNS = [
    'Оперативные сводки _2',
    'Оперативные сводки _3',
    'Оперативные сводки _2_2',
    'Оперативные сводки ЕДС_2',
]


def _is_operative_variant(path: Path) -> bool:
    name = path.stem
    return any(p in name for p in _OPERATIVE_SKIP_PATTERNS)


def _process_file(path: Path) -> tuple[int, int]:
    try:
        buf = io.BytesIO(path.read_bytes())

        # ── Оп.сводки _2 系はスキップ（main ファイルが正式版）──
        if _is_operative_variant(path):
            log.info(f"  スキップ（補助バリアント）: {path.name}")
            return -1, 0  # -1 = スキップ済み（アーカイブは行う）

        # ── Сменный рапорт（製材工場シフトレポート）──
        buf.seek(0)
        if is_shift_report_format(buf):
            buf.seek(0)
            records, detected_date, errors = parse_shift_report(buf)
            for e in errors:
                log.warning(f"  [{path.name}] {e}")
            if not records:
                log.info(f"  [{path.name}] 停止データなし (日付={detected_date})")
                return -1, 0  # 停止なし = スキップ扱い（アーカイブする）
            added, skipped = add_stoppages(records)
            log.info(f"  [{path.name}] 停止データ取込: {added}件追加 / {skipped}件スキップ (日付={detected_date})")
            return added, skipped

        # ── Оп.сводки（日次生産指標）──
        buf.seek(0)
        if not is_operative_format(buf):
            log.info(f"  スキップ（未対応フォーマット）: {path.name}")
            return 0, 0
        buf.seek(0)
        records, detected_date, errors = parse_operative_file(buf)
        for e in errors:
            log.warning(f"  [{path.name}] {e}")
        if not records:
            log.warning(f"  [{path.name}] 指標データを抽出できませんでした")
            return 0, 0
        added, skipped = add_operative(records)
        log.info(f"  [{path.name}] 取込完了: {added}件追加 / {skipped}件スキップ (日付={detected_date})")
        return added, skipped

    except Exception as e:
        log.error(f"  [{path.name}] 取込エラー: {e}", exc_info=True)
        return 0, 0


def _scan_folder(processed: set, today_count: int,
                 last_import: str, last_file: str) -> tuple[int, str, str]:
    UNIMPORTED_DIR.mkdir(parents=True, exist_ok=True)
    for xlsx in sorted(UNIMPORTED_DIR.glob("未取込み_*.xlsx")):
        key = f"{xlsx.name}|{xlsx.stat().st_size}"
        if key in processed:
            continue
        log.info(f"未取込みファイル検出: {xlsx.name}")
        if not _is_stable(xlsx):
            log.info(f"  書き込み中のためスキップ: {xlsx.name}")
            continue
        processed.add(key)
        added, _ = _process_file(xlsx)
        if added > 0:
            today_count += added
            last_import = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            last_file   = xlsx.name
            try:
                _archive_file(xlsx)
            except Exception as e:
                log.warning(f"  整理エラー: {e}")
            _notify("ALK インポート完了", f"{xlsx.name}  —  {added}件取り込みました")
        elif added == -1:
            # スキップ扱い（バリアントファイル or 停止なし）→ アーカイブだけ行う
            try:
                _archive_file(xlsx)
            except Exception as e:
                log.warning(f"  整理エラー: {e}")
        else:
            log.warning(f"  インポート失敗 → 未取込みフォルダに残します: {xlsx.name}")
    return today_count, last_import, last_file


# ══════════════════════════════════════════════════════════
#  メインループ
# ══════════════════════════════════════════════════════════
def main() -> None:
    log.info("=" * 55)
    log.info("ALK 自動インポート 起動")
    if USE_IMAP:
        log.info(f"  IMAP監視  : {EMAIL_ADDRESS} ({IMAP_HOST}:{IMAP_PORT})")
    else:
        log.info("  IMAP監視  : 無効（secrets.toml: use_imap=false / COM経由で取込）")
    log.info(f"  COM監視   : 旧Outlook起動中なら自動で使用")
    log.info(f"  対象送信者: {TARGET_SENDER}")
    log.info(f"  フォルダ  : {WATCH_DIR}")
    log.info(f"  間隔      : {POLL_SECONDS}秒")
    log.info("=" * 55)

    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    UNIMPORTED_DIR.mkdir(parents=True, exist_ok=True)

    processed: set  = set()
    today_count: int = 0
    last_import: str = ""
    last_file:   str = ""

    # 起動時: 未取込みフォルダの既存ファイルを処理
    existing = list(UNIMPORTED_DIR.glob("未取込み_*.xlsx"))
    if existing:
        log.info(f"未取込みフォルダに既存ファイル {len(existing)} 件 → インポート開始...")
        for xlsx in existing:
            log.info(f"  起動時処理: {xlsx.name}")
            added, _ = _process_file(xlsx)
            if added > 0:
                today_count += added
                last_import = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                last_file   = xlsx.name
                try:
                    _archive_file(xlsx)
                except Exception as e:
                    log.warning(f"  整理スキップ: {xlsx.name} ({e})")
                _notify("ALK インポート完了", f"{xlsx.name}  —  {added}件取り込みました")
            elif added == -1:
                try:
                    _archive_file(xlsx)
                except Exception as e:
                    log.warning(f"  整理スキップ: {xlsx.name} ({e})")
            else:
                log.warning(f"  インポート失敗 → 未取込みフォルダに残します: {xlsx.name}")
            processed.add(f"{xlsx.name}|0")

    log.info("監視開始...")
    cycle = 0

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_error = ""
        cycle += 1
        try:
            # 1) IMAP（優先）
            new_imap = _check_imap()

            # 2) COM（旧Outlook起動中なら追加で取得）
            new_com = _check_outlook_com()

            new_files = new_imap + new_com

            # 3) フォルダスキャン
            today_count, last_import, last_file = _scan_folder(
                processed, today_count, last_import, last_file
            )
            _save_status(now, last_import, today_count, last_file)

            # 4) 停止アラート（10サイクルに1回）
            if cycle % 10 == 0:
                _check_stoppage_alert()

            if cycle % 10 == 0 or new_files:
                log.info(f"稼働中 #{cycle} | 本日取込: {today_count}件 | 最終取込: {last_import or '未'}")

        except Exception as e:
            last_error = str(e)
            log.error(f"エラー: {e}", exc_info=True)
            _save_status(now, last_import, today_count, last_file, last_error=last_error)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
