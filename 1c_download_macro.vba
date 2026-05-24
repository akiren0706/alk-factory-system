Sub Download1CAttachments()
    Dim ns As NameSpace
    Dim savePath As String
    Dim saved As Long, skipped As Long, errors As Long

    Const TARGET_SENDER = "1c_alk@rfpgroup.ru"
    savePath = "C:\Users\r-akiyama\Desktop\１C生産データ\"

    On Error Resume Next
    MkDir savePath
    On Error GoTo 0

    Set ns = Application.GetNamespace("MAPI")

    Dim store As Store
    For Each store In ns.Stores
        Call ScanFolder(store.GetRootFolder(), TARGET_SENDER, savePath, saved, skipped, errors)
    Next store

    MsgBox "完了!" & vbCrLf & _
           "保存: " & saved & " 件" & vbCrLf & _
           "エラー: " & errors & " 件" & vbCrLf & _
           "保存先: " & savePath
End Sub

Sub ScanFolder(folder As MAPIFolder, targetSender As String, savePath As String, _
               saved As Long, skipped As Long, errors As Long)
    On Error Resume Next

    Dim i As Long
    For i = 1 To folder.Items.Count
        Dim mail As Object
        Set mail = folder.Items.Item(i)
        If TypeName(mail) = "MailItem" Then
            Dim sender As String
            sender = mail.SenderEmailAddress
            If InStr(LCase(sender), LCase(targetSender)) > 0 Then
                Dim dateStr As String
                dateStr = Format(mail.ReceivedTime, "yyyy-mm-dd")
                Dim j As Integer
                For j = 1 To mail.Attachments.Count
                    Dim att As Attachment
                    Set att = mail.Attachments.Item(j)

                    Dim baseName As String
                    Dim ext As String
                    Dim origName As String
                    origName = CleanName(att.FileName)
                    ext = "." & Split(origName, ".")(UBound(Split(origName, ".")))
                    baseName = Left(origName, Len(origName) - Len(ext))

                    ' 日付プレフィックスを付けたファイル名を生成
                    ' 同名が既存の場合は _2, _3 と連番を付ける
                    Dim dest As String
                    dest = savePath & dateStr & "_" & baseName & ext
                    Dim counter As Integer
                    counter = 2
                    Do While Dir(dest) <> ""
                        dest = savePath & dateStr & "_" & baseName & "_" & counter & ext
                        counter = counter + 1
                    Loop

                    Err.Clear
                    att.SaveAsFile dest
                    If Err.Number = 0 Then
                        saved = saved + 1
                    Else
                        errors = errors + 1
                    End If
                Next j
            End If
        End If
    Next i

    Dim sub_ As MAPIFolder
    For Each sub_ In folder.Folders
        Call ScanFolder(sub_, targetSender, savePath, saved, skipped, errors)
    Next sub_
End Sub

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
