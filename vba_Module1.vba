' ==============================================
' Module1 に貼り付けるコード
' ==============================================

Const SAVE_PATH     = "C:\Users\r-akiyama\Desktop\１C生産データ\"
Const TARGET_SENDER = "1c_alk@rfpgroup.ru"

' -----------------------------------------------
' 【通常用】未読メールの添付ファイルだけを取得する
'   → 毎日手動で実行する場合はこちら
'   → ThisOutlookSession の自動トリガーと組み合わせて使う
' -----------------------------------------------
Sub Download1CUnreadAttachments()
    On Error Resume Next
    MkDir SAVE_PATH
    On Error GoTo 0

    Dim ns As NameSpace
    Set ns = Application.GetNamespace("MAPI")

    Dim saved As Long, skipped As Long
    Dim inbox As MAPIFolder
    Set inbox = ns.GetDefaultFolder(olFolderInbox)

    Dim i As Long
    For i = inbox.Items.Count To 1 Step -1   ' 新しい順に処理
        Dim mail As Object
        Set mail = inbox.Items.Item(i)

        If TypeName(mail) = "MailItem" Then
            ' 未読 かつ 対象送信者のみ
            If mail.UnRead = True Then
                If InStr(LCase(mail.SenderEmailAddress), LCase(TARGET_SENDER)) > 0 Then
                    If mail.Attachments.Count > 0 Then
                        Call SaveAttachments(mail)
                        saved = saved + mail.Attachments.Count
                        mail.UnRead = False   ' 取得後に既読にする
                    End If
                End If
            End If
        End If
    Next i

    MsgBox "完了!" & vbCrLf & _
           "取得ファイル数: " & saved & " 件" & vbCrLf & _
           "保存先: " & SAVE_PATH
End Sub

' -----------------------------------------------
' 【初回のみ】過去メールをすべて一括ダウンロード
'   → 初回セットアップ時に1回だけ実行する
' -----------------------------------------------
Sub Download1CAllAttachments()
    On Error Resume Next
    MkDir SAVE_PATH
    On Error GoTo 0

    Dim ns As NameSpace
    Set ns = Application.GetNamespace("MAPI")

    Dim saved As Long, errors As Long
    Dim store As Store
    For Each store In ns.Stores
        Call ScanAllFolders(store.GetRootFolder(), saved, errors)
    Next store

    MsgBox "完了!" & vbCrLf & _
           "保存: " & saved & " 件" & vbCrLf & _
           "エラー: " & errors & " 件" & vbCrLf & _
           "保存先: " & SAVE_PATH
End Sub

' -----------------------------------------------
' 添付ファイルを保存する共通関数
' （ThisOutlookSession からも呼び出される）
' -----------------------------------------------
Sub SaveAttachments(mail As Object)
    On Error Resume Next
    MkDir SAVE_PATH
    On Error GoTo 0

    Dim dateStr As String
    dateStr = Format(mail.ReceivedTime, "yyyy-mm-dd")

    Dim j As Integer
    For j = 1 To mail.Attachments.Count
        Dim att As Attachment
        Set att = mail.Attachments.Item(j)

        If LCase(Right(att.FileName, 5)) <> ".xlsx" Then GoTo NextAtt

        Dim origName As String
        origName = CleanName(att.FileName)

        Dim ext As String
        ext = "." & Split(origName, ".")(UBound(Split(origName, ".")))
        Dim baseName As String
        baseName = Left(origName, Len(origName) - Len(ext))

        Dim dest As String
        dest = SAVE_PATH & dateStr & "_" & baseName & ext
        Dim counter As Integer
        counter = 2
        Do While Dir(dest) <> ""
            dest = SAVE_PATH & dateStr & "_" & baseName & "_" & counter & ext
            counter = counter + 1
        Loop

        att.SaveAsFile dest
NextAtt:
    Next j
End Sub

' -----------------------------------------------
' 全フォルダを再帰スキャン（Download1CAllAttachments 用）
' -----------------------------------------------
Sub ScanAllFolders(folder As MAPIFolder, saved As Long, errors As Long)
    On Error Resume Next

    Dim i As Long
    For i = 1 To folder.Items.Count
        Dim mail As Object
        Set mail = folder.Items.Item(i)
        If TypeName(mail) = "MailItem" Then
            If InStr(LCase(mail.SenderEmailAddress), LCase(TARGET_SENDER)) > 0 Then
                If mail.Attachments.Count > 0 Then
                    Call SaveAttachments(mail)
                    If Err.Number = 0 Then
                        saved = saved + mail.Attachments.Count
                    Else
                        errors = errors + 1
                        Err.Clear
                    End If
                End If
            End If
        End If
    Next i

    Dim sub_ As MAPIFolder
    For Each sub_ In folder.Folders
        Call ScanAllFolders(sub_, saved, errors)
    Next sub_
End Sub

' -----------------------------------------------
' ファイル名の使用不可文字を除去
' -----------------------------------------------
Function CleanName(name As String) As String
    Dim s As String
    s = name
    s = Replace(s, "<", "_") : s = Replace(s, ">", "_")
    s = Replace(s, ":", "_") : s = Replace(s, """", "_")
    s = Replace(s, "/", "_") : s = Replace(s, "\", "_")
    s = Replace(s, "|", "_") : s = Replace(s, "?", "_")
    s = Replace(s, "*", "_")
    CleanName = s
End Function
