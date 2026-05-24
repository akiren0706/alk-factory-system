# Outlook から 1c_alk@rfpgroup.ru の添付ファイルをすべてダウンロードするスクリプト
import re
import traceback
from pathlib import Path

TARGET_SENDER = "1c_alk@rfpgroup.ru"
TARGET_FOLDER = Path(r"C:\Users\r-akiyama\Desktop\１C生産データ")


def clean(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def collect_mails(ns, target_sender: str):
    """全フォルダを再帰的に検索してターゲット送信者のメールを収集する"""
    results = []

    def _scan(folder, path=""):
        folder_path = f"{path}/{folder.Name}" if path else folder.Name
        try:
            items = folder.Items
            count = items.Count
            if count > 0:
                matched = 0
                for i in range(1, count + 1):
                    try:
                        mail = items.Item(i)
                        sender = ""
                        try:
                            sender = mail.SenderEmailAddress or ""
                        except Exception:
                            pass
                        if not sender:
                            try:
                                sender = mail.SenderName or ""
                            except Exception:
                                pass
                        if target_sender.lower() in sender.lower():
                            results.append((mail, folder_path))
                            matched += 1
                    except Exception:
                        pass
                if matched > 0:
                    print(f"  [{folder_path}] {count}通中 {matched}通 該当")
        except Exception:
            pass

        try:
            for sub in folder.Folders:
                _scan(sub, folder_path)
        except Exception:
            pass

    for store in ns.Stores:
        try:
            _scan(store.GetRootFolder())
        except Exception:
            pass

    return results


def download():
    print("Step 1: win32com をインポート中...")
    try:
        import win32com.client
        print("  OK")
    except ImportError as e:
        print(f"  エラー: pywin32 がインストールされていません - {e}")
        return 0

    print("Step 2: Outlookに接続中...")
    try:
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
            print("  既存のOutlookプロセスに接続しました")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")
            print("  Outlookを新規起動しました")
        ns = outlook.GetNamespace("MAPI")
        print("  OK")
    except Exception as e:
        print(f"  エラー: Outlookへの接続失敗 - {e}")
        print("  ※ Outlookが起動していることを確認してください")
        return 0

    print(f"Step 3: 全フォルダから '{TARGET_SENDER}' のメールを検索中...")
    print("  (フォルダ数によっては時間がかかります)")
    mails = collect_mails(ns, TARGET_SENDER)
    print(f"  合計 {len(mails)} 通見つかりました")

    if not mails:
        print()
        print("  メールが見つかりません。以下を試してください:")
        print("  - Outlookで「送受信」→「すべてのフォルダーを送受信」を実行後、再度起動")
        return 0

    TARGET_FOLDER.mkdir(parents=True, exist_ok=True)

    print(f"\nStep 4: 添付ファイルを保存中...")
    saved = skipped = errors = 0

    for mail, folder_path in mails:
        try:
            att_count = mail.Attachments.Count
            if att_count == 0:
                continue

            try:
                date_str = mail.ReceivedTime.strftime("%Y-%m-%d")
            except Exception:
                date_str = "0000-00-00"

            subject = (mail.Subject or "")[:60]
            print(f"\n  [{date_str}] {subject}")

            for j in range(1, att_count + 1):
                try:
                    att      = mail.Attachments.Item(j)
                    orig     = att.FileName
                    stem     = Path(orig).stem
                    ext      = Path(orig).suffix
                    new_name = clean(f"{date_str}_{stem}{ext}")
                    dest     = TARGET_FOLDER / new_name

                    if dest.exists():
                        print(f"    スキップ（既存）: {new_name}")
                        skipped += 1
                        continue

                    att.SaveAsFile(str(dest))
                    print(f"    保存: {new_name}")
                    saved += 1
                except Exception as e:
                    print(f"    添付ファイルエラー: {e}")
                    errors += 1

        except Exception as e:
            errors += 1

    print()
    print(f"対象メール: {len(mails)} 通")
    print(f"保存: {saved} 件 / スキップ: {skipped} 件 / エラー: {errors} 件")
    print(f"保存先: {TARGET_FOLDER}")
    return saved


if __name__ == "__main__":
    print("=" * 50)
    print("1C 生産データ ダウンロードツール")
    print("=" * 50)
    print()
    try:
        n = download()
        print()
        if n > 0:
            print(f"完了: {n} ファイルをダウンロードしました。")
        else:
            print("新しいファイルはありませんでした。")
    except Exception as e:
        print()
        print("予期しないエラーが発生しました:")
        traceback.print_exc()
    print()
    input("Enterキーで閉じる...")
